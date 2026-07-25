"""Kafka consumer that applies Flink commands to the durable projection."""

# kafka-python-ng exposes dynamic record and callback types at this adapter
# boundary. Domain events and repository methods remain strictly typed.
# pyright: reportUnknownMemberType=false, reportMissingModuleSource=false

from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Thread

from kafka import KafkaConsumer
from kafka.consumer.subscription_state import ConsumerRebalanceListener
from kafka.structs import OffsetAndMetadata, TopicPartition

from servicegraph_ui.config import VisualizationConfig
from servicegraph_ui.models import PROJECTION_EVENT_ADAPTER
from servicegraph_ui.repository import ProjectionRepository


@dataclass
class ConsumerStatus:
    running: bool = False
    error: str | None = None
    last_event_at_unix_ms: int | None = None


class ProjectionConsumer:
    def __init__(self, config: VisualizationConfig, repository: ProjectionRepository) -> None:
        self._config = config
        self._repository = repository
        self.status = ConsumerStatus()
        self._stop = Event()
        self._thread: Thread | None = None
        self._consumer: KafkaConsumer | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = Thread(target=self._consume, name="servicegraph-projection-consumer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=15)
        self.status.running = False

    def _consume(self) -> None:
        consumer: KafkaConsumer | None = None
        try:
            consumer = _create_consumer(self._config)
            self._consumer = consumer
            consumer.subscribe(
                topics=(self._config.topic,),
                listener=_ProjectionRebalanceListener(consumer, self._config.topic, self._repository),
            )
            self.status.running = True
            self.status.error = None
            while not self._stop.is_set():
                records = consumer.poll(timeout_ms=1_000, max_records=100)
                offsets: dict[TopicPartition, OffsetAndMetadata] = {}
                for topic_partition, partition_records in records.items():
                    events = tuple(
                        (record.offset, PROJECTION_EVENT_ADAPTER.validate_json(record.value))
                        for record in partition_records
                    )
                    if not events:
                        continue
                    self._repository.apply_events(
                        topic_partition.topic,
                        topic_partition.partition,
                        events,
                    )
                    last_offset, last_event = events[-1]
                    offsets[topic_partition] = OffsetAndMetadata(  # pyright: ignore[reportCallIssue]
                        last_offset + 1,
                        "",
                    )
                    self.status.last_event_at_unix_ms = last_event.emitted_at_unix_ms
                if offsets:
                    consumer.commit(offsets=offsets)
        except Exception as exc:
            if not self._stop.is_set():
                self.status.error = f"{type(exc).__name__}: {exc}"
        finally:
            self.status.running = False
            if consumer is not None:
                consumer.close(autocommit=False)
            self._consumer = None


class _ProjectionRebalanceListener(ConsumerRebalanceListener):
    def __init__(
        self,
        consumer: KafkaConsumer,
        topic: str,
        repository: ProjectionRepository,
    ) -> None:
        self._consumer = consumer
        self._topic = topic
        self._repository = repository

    def on_partitions_revoked(self, revoked: list[TopicPartition]) -> None:
        del revoked

    def on_partitions_assigned(self, assigned: list[TopicPartition]) -> None:
        for topic_partition in assigned:
            next_offset = self._repository.next_offset(self._topic, topic_partition.partition)
            if next_offset is None:
                self._consumer.seek_to_beginning(topic_partition)
            else:
                self._consumer.seek(topic_partition, next_offset)


def _create_consumer(config: VisualizationConfig) -> KafkaConsumer:
    if config.kafka_security_protocol.value == "PLAINTEXT":
        return KafkaConsumer(
            bootstrap_servers=config.kafka_bootstrap_servers,
            group_id=config.group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=None,
            security_protocol="PLAINTEXT",
        )
    password = config.kafka_sasl_password
    ca_file = config.kafka_ssl_ca_file
    if password is None or ca_file is None:
        raise RuntimeError("validated SASL_SSL settings are incomplete")
    return KafkaConsumer(
        bootstrap_servers=config.kafka_bootstrap_servers,
        group_id=config.group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=None,
        security_protocol="SASL_SSL",
        sasl_mechanism="SCRAM-SHA-256",
        sasl_plain_username=config.kafka_sasl_username,
        sasl_plain_password=password.get_secret_value(),
        ssl_cafile=ca_file.as_posix(),
        ssl_check_hostname=True,
    )
