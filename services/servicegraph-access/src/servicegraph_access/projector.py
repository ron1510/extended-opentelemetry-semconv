"""Project Flink graph-element lifecycle events into Elasticsearch."""

# kafka-python-ng exposes dynamic consumer and record types at this adapter boundary.
# pyright: reportUnknownMemberType=false, reportMissingModuleSource=false

from __future__ import annotations

import json
import logging
import signal
from collections.abc import Mapping, Sequence
from enum import StrEnum
from threading import Event
from types import FrameType
from typing import Protocol, cast

from elasticsearch import Elasticsearch
from kafka import KafkaConsumer
from kafka.structs import OffsetAndMetadata, TopicPartition
from pydantic import Field, SecretStr, model_validator

from servicegraph_access.index import AccessSettings, ElasticsearchClient, initialize

LOGGER = logging.getLogger(__name__)
MAX_POLL_RECORDS = 500
POLL_TIMEOUT_MS = 1_000


class ProjectionError(RuntimeError):
    """Raised when a Kafka batch cannot be committed safely."""


class KafkaSecurityProtocol(StrEnum):
    PLAINTEXT = "PLAINTEXT"
    SASL_PLAINTEXT = "SASL_PLAINTEXT"
    SASL_SSL = "SASL_SSL"


class ProjectorSettings(AccessSettings):
    kafka_bootstrap_servers: str = Field(default="kafka:9092", min_length=1)
    kafka_security_protocol: KafkaSecurityProtocol = KafkaSecurityProtocol.PLAINTEXT
    kafka_sasl_mechanism: str | None = None
    kafka_sasl_username: str | None = Field(default=None, min_length=1)
    kafka_sasl_password: SecretStr | None = None
    input_topic: str = Field(default="graph.elements.events", min_length=1, pattern=r"^[A-Za-z0-9._-]+$")
    consumer_group_id: str = Field(
        default="servicegraph-elasticsearch-projector",
        min_length=1,
        pattern=r"^[A-Za-z0-9._-]+$",
    )

    @model_validator(mode="after")
    def validate_kafka_security(self) -> ProjectorSettings:
        security_values = (
            self.kafka_sasl_mechanism,
            self.kafka_sasl_username,
            self.kafka_sasl_password,
        )
        if self.kafka_security_protocol is not KafkaSecurityProtocol.PLAINTEXT:
            if self.kafka_sasl_mechanism != "SCRAM-SHA-256":
                raise ValueError("Kafka SASL authentication requires SCRAM-SHA-256")
            if self.kafka_sasl_username is None or self.kafka_sasl_password is None:
                raise ValueError("Kafka username and password are required for SASL authentication")
        elif any(value is not None for value in security_values):
            raise ValueError("Kafka authentication fields require SASL_PLAINTEXT or SASL_SSL")
        return self


class BulkClient(Protocol):
    def bulk(
        self,
        *,
        operations: Sequence[Mapping[str, object]],
        refresh: bool,
    ) -> Mapping[str, object]: ...

    def close(self) -> None: ...


class ProjectorClient(BulkClient, ElasticsearchClient, Protocol):
    pass


class KafkaRecord(Protocol):
    offset: int
    value: bytes | str


def create_elasticsearch_client(settings: ProjectorSettings) -> ProjectorClient:
    basic_auth: tuple[str, str] | None = None
    if settings.elasticsearch_username is not None and settings.elasticsearch_password is not None:
        basic_auth = (
            settings.elasticsearch_username,
            settings.elasticsearch_password.get_secret_value(),
        )
    if settings.elasticsearch_ca_file is None:
        client = Elasticsearch(
            settings.urls,
            request_timeout=10,
            max_retries=3,
            retry_on_status=(429, 502, 503, 504),
            retry_on_timeout=True,
            basic_auth=basic_auth,
        )
    else:
        client = Elasticsearch(
            settings.urls,
            request_timeout=10,
            max_retries=3,
            retry_on_status=(429, 502, 503, 504),
            retry_on_timeout=True,
            basic_auth=basic_auth,
            ca_certs=str(settings.elasticsearch_ca_file),
        )
    return cast(ProjectorClient, client)


def create_consumer(settings: ProjectorSettings) -> KafkaConsumer:
    if settings.kafka_security_protocol is KafkaSecurityProtocol.PLAINTEXT:
        return KafkaConsumer(
            settings.input_topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.consumer_group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=None,
            security_protocol="PLAINTEXT",
        )
    password = settings.kafka_sasl_password
    if password is None:
        raise RuntimeError("validated Kafka SASL settings are incomplete")
    return KafkaConsumer(
        settings.input_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.consumer_group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=None,
        security_protocol=settings.kafka_security_protocol.value,
        sasl_mechanism="SCRAM-SHA-256",
        sasl_plain_username=settings.kafka_sasl_username,
        sasl_plain_password=password.get_secret_value(),
    )


def event_to_bulk_operations(payload: bytes | str, index_name: str) -> tuple[dict[str, object], ...]:
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise ProjectionError("graph-element event must be a JSON object")
    event = cast(dict[str, object], decoded)
    operation = event["operation"]
    element_id = event["element_id"]
    if not isinstance(element_id, str):
        raise ProjectionError("graph-element event element_id must be a string")

    if operation == "delete":
        return ({"delete": {"_index": index_name, "_id": element_id}},)
    if operation != "upsert":
        raise ProjectionError(f"unsupported graph-element operation: {operation!r}")

    element_value = event["element"]
    if not isinstance(element_value, Mapping):
        raise ProjectionError("upsert graph-element event must contain an element object")
    element = cast(Mapping[str, object], element_value)
    document: dict[str, object] = {
        "schema_version": event["schema_version"],
        "event_id": event["event_id"],
        "payload_hash": event["payload_hash"],
        "id": element["id"],
        "kind": element["kind"],
        "type": element["type"],
        "attributes": element["attributes"],
        "metrics": element.get("metrics", {}),
        "observed_at_unix_nano": event["observed_at_unix_nano"],
        "emitted_at_unix_ms": event["emitted_at_unix_ms"],
    }
    for field in ("source_id", "target_id"):
        if field in element:
            document[field] = element[field]
    return (
        {"index": {"_index": index_name, "_id": element_id}},
        document,
    )


def project_poll(
    records: Mapping[TopicPartition, Sequence[KafkaRecord]],
    consumer: KafkaConsumer,
    client: BulkClient,
    index_name: str,
) -> int:
    operations: list[Mapping[str, object]] = []
    expected_results: list[tuple[str, str]] = []
    offsets: dict[TopicPartition, OffsetAndMetadata] = {}

    for topic_partition, partition_records in records.items():
        if not partition_records:
            continue
        for record in partition_records:
            event_operations = event_to_bulk_operations(record.value, index_name)
            action = next(iter(event_operations[0]))
            action_metadata = cast(Mapping[str, object], event_operations[0][action])
            expected_results.append((action, cast(str, action_metadata["_id"])))
            operations.extend(event_operations)
        last_offset = partition_records[-1].offset
        offsets[topic_partition] = OffsetAndMetadata(last_offset + 1, "")  # pyright: ignore[reportCallIssue]

    if not operations:
        return 0

    response = client.bulk(operations=operations, refresh=False)
    _verify_bulk_response(response, expected_results)
    consumer.commit(offsets=offsets)
    return len(expected_results)


def run_projector(
    settings: ProjectorSettings,
    *,
    stop: Event | None = None,
    consumer: KafkaConsumer | None = None,
    client: ProjectorClient | None = None,
) -> None:
    stop_event = stop or Event()
    owned_client = client is None
    owned_consumer = consumer is None
    active_client = client or create_elasticsearch_client(settings)
    active_consumer: KafkaConsumer | None = None
    try:
        state = initialize(settings, active_client)
        LOGGER.info("Elasticsearch index %s is %s", settings.index_name, state)
        active_consumer = consumer or create_consumer(settings)
        LOGGER.info("Projecting %s with consumer group %s", settings.input_topic, settings.consumer_group_id)
        while not stop_event.is_set():
            records = active_consumer.poll(timeout_ms=POLL_TIMEOUT_MS, max_records=MAX_POLL_RECORDS)
            projected = project_poll(
                cast(Mapping[TopicPartition, Sequence[KafkaRecord]], records),
                active_consumer,
                active_client,
                settings.index_name,
            )
            if projected:
                LOGGER.info("Projected and committed %d graph-element events", projected)
    finally:
        if active_consumer is not None and owned_consumer:
            active_consumer.close(autocommit=False)
        if owned_client:
            active_client.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = Event()

    def request_stop(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        run_projector(ProjectorSettings(), stop=stop)
    except Exception:
        LOGGER.exception("Service graph projection failed")
        return 1
    return 0


def _verify_bulk_response(response: Mapping[str, object], expected: Sequence[tuple[str, str]]) -> None:
    items_value = response.get("items")
    if not isinstance(items_value, Sequence) or isinstance(items_value, (str, bytes)):
        raise ProjectionError("Elasticsearch bulk response has no items array")
    items = cast(Sequence[object], items_value)
    if len(items) != len(expected):
        raise ProjectionError(
            f"Elasticsearch bulk response returned {len(items)} items for {len(expected)} operations"
        )
    accepted = {"index": {200, 201}, "delete": {200, 404}}
    for item_value, (expected_action, element_id) in zip(items, expected, strict=True):
        if not isinstance(item_value, Mapping):
            raise ProjectionError(f"Elasticsearch bulk item for {element_id} is not an object")
        item = cast(Mapping[str, object], item_value)
        result_value = item.get(expected_action)
        if not isinstance(result_value, Mapping):
            raise ProjectionError(f"Elasticsearch bulk item for {element_id} has no {expected_action} result")
        result = cast(Mapping[str, object], result_value)
        status = result.get("status")
        if status not in accepted[expected_action]:
            error = result.get("error")
            raise ProjectionError(
                f"Elasticsearch bulk {expected_action} failed for {element_id}: status={status!r}, error={error!r}"
            )


if __name__ == "__main__":
    raise SystemExit(main())
