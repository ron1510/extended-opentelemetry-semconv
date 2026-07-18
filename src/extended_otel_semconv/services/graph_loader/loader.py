"""Graph loader service for Kafka and stdin observation ingestion."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Iterator
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from extended_otel_semconv.registry.model import RegistryDocument, RelationshipDefinition
from extended_otel_semconv.registry.validation import load_model_registry
from extended_otel_semconv.services.graph_loader.config import GraphLoaderConfig, ModelRegistryConfig
from extended_otel_semconv.graph.metrics import parse_metrics_json_document
from extended_otel_semconv.graph.observation import GraphObservation
from extended_otel_semconv.graph.otlp_json_logs import iter_service_graph_log_records
from extended_otel_semconv.graph.postgres_loader import persist_observations, record_observation_error
from extended_otel_semconv.graph.postgres_schema import build_graph_schema
from extended_otel_semconv.graph.service_graph import observations_from_service_graph_datapoint

OBSERVATION_ADAPTER: TypeAdapter[GraphObservation] = TypeAdapter(GraphObservation)


def run_graph_loader(config: GraphLoaderConfig) -> int:
    if config.input == "stdin-observations":
        return load_stdin_observations(config)
    if config.input == "stdin-otlp-json-logs":
        return load_stdin_otlp_json_logs(config)
    if config.input == "stdin-otlp-json-metrics":
        return load_stdin_otlp_json_metrics(config)
    return load_kafka_otlp_json_metrics(config)


def load_observations(
    engine: Engine,
    observations: Iterable[GraphObservation],
    registry_config: ModelRegistryConfig | None = None,
) -> int:
    schema = build_graph_schema(_merged_registry(registry_config or ModelRegistryConfig()))
    with engine.begin() as connection:
        count = persist_observations(connection, schema, list(observations))
    print(f"persisted_observations={count}", flush=True)
    return 0


def load_stdin_observations(config: GraphLoaderConfig) -> int:
    return load_observations(
        create_engine(config.postgres.url, pool_pre_ping=True),
        iter_stdin_observations(),
        config.registry,
    )


def load_stdin_otlp_json_logs(config: GraphLoaderConfig) -> int:
    relationships = _relationships(config.registry)
    return load_observations(
        create_engine(config.postgres.url, pool_pre_ping=True),
        iter_stdin_otlp_json_log_observations(relationships),
        config.registry,
    )


def load_stdin_otlp_json_metrics(config: GraphLoaderConfig) -> int:
    relationships = _relationships(config.registry)
    return load_observations(
        create_engine(config.postgres.url, pool_pre_ping=True),
        iter_stdin_otlp_json_metric_observations(relationships),
        config.registry,
    )


def load_kafka_otlp_json_metrics(config: GraphLoaderConfig) -> int:
    engine = create_engine(config.postgres.url, pool_pre_ping=True)
    return load_kafka_otlp_json(engine, config)


def load_kafka_otlp_json(
    engine: Engine,
    config: GraphLoaderConfig,
) -> int:
    from confluent_kafka import Consumer, KafkaError, KafkaException  # type: ignore[import-untyped]

    schema = build_graph_schema(_merged_registry(config.registry))
    relationships = _relationships(config.registry)
    consumer = Consumer(
        {
            "bootstrap.servers": config.kafka.bootstrap_servers,
            "group.id": config.kafka.group_id,
            "auto.offset.reset": config.kafka.auto_offset_reset,
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([config.kafka.topic])
    consumed = 0
    try:
        while True:
            if config.kafka.max_messages is not None and consumed >= config.kafka.max_messages:
                return 0
            messages = consumer.consume(num_messages=max(config.kafka.batch_size, 1), timeout=1.0)
            if not messages:
                continue
            observations: list[GraphObservation] = []
            errors: list[tuple[str, object]] = []
            commit_message = None
            for message in messages:
                if config.kafka.max_messages is not None and consumed >= config.kafka.max_messages:
                    break
                consumed += 1
                commit_message = message
                if message.error():
                    if message.error().code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                        continue
                    raise KafkaException(message.error())
                decoded_payload = decode_kafka_payload(message.value())
                try:
                    observations.extend(observations_from_otlp_json_metrics_document(json.loads(decoded_payload), relationships))
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    errors.append((type(exc).__name__, {"payload": decoded_payload}))
            with engine.begin() as connection:
                for reason, payload in errors:
                    record_observation_error(connection, schema, reason, payload)
                count = persist_observations(connection, schema, observations)
            if commit_message is not None:
                consumer.commit(message=commit_message, asynchronous=False)
            print(f"messages={len(messages)} persisted_observations={count} errors={len(errors)}", flush=True)
    finally:
        consumer.close()


def iter_stdin_observations() -> Iterator[GraphObservation]:
    for line in sys.stdin:
        line = line.strip()
        if line == "":
            continue
        yield OBSERVATION_ADAPTER.validate_python(json.loads(line))


def iter_stdin_otlp_json_log_observations(
    relationships: tuple[RelationshipDefinition, ...] | None = None,
) -> Iterator[GraphObservation]:
    for line in sys.stdin:
        line = line.strip()
        if line == "":
            continue
        yield from observations_from_otlp_json_log_document(json.loads(line), relationships)


def iter_stdin_otlp_json_metric_observations(
    relationships: tuple[RelationshipDefinition, ...] | None = None,
) -> Iterator[GraphObservation]:
    for line in sys.stdin:
        line = line.strip()
        if line == "":
            continue
        yield from observations_from_otlp_json_metrics_document(json.loads(line), relationships)


def observations_from_otlp_json_log_document(
    document: dict[str, Any],
    relationships: tuple[RelationshipDefinition, ...] | None = None,
) -> Iterator[GraphObservation]:
    if relationships is None:
        relationships = _relationships(ModelRegistryConfig())
    for metric_name, attributes, value, observed_at in iter_service_graph_log_records(document):
        yield from observations_from_service_graph_datapoint(
            metric_name=metric_name,
            attributes=attributes,
            value=value,
            observed_at_unix_nano=observed_at,
            relationships=relationships,
        )


def observations_from_otlp_json_metrics_document(
    document: dict[str, object],
    relationships: tuple[RelationshipDefinition, ...] | None = None,
) -> Iterator[GraphObservation]:
    if relationships is None:
        relationships = _relationships(ModelRegistryConfig())
    for point in parse_metrics_json_document(document):
        yield from observations_from_service_graph_datapoint(
            metric_name=point.name,
            attributes=point.attributes,
            value=point.value,
            observed_at_unix_nano=point.observed_at_unix_nano,
            relationships=relationships,
        )


def decode_kafka_payload(payload: bytes | None) -> str:
    if payload is None:
        return ""
    return payload.decode("utf-8")


def _merged_registry(config: ModelRegistryConfig) -> RegistryDocument:
    upstream = load_model_registry(config.upstream_model)
    extension = load_model_registry(config.extension_model)
    return upstream.model_copy(update={"groups": (*upstream.groups, *extension.groups)})


def _relationships(config: ModelRegistryConfig) -> tuple[RelationshipDefinition, ...]:
    return tuple(load_model_registry(config.extension_model).relationships_by_id.values())
