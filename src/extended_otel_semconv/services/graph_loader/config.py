"""Configuration models for the graph loader service."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

GraphLoaderInput = Literal["stdin-observations", "stdin-otlp-json-logs", "stdin-otlp-json-metrics", "kafka-otlp-json-metrics"]
KafkaAutoOffsetReset = Literal["earliest", "latest"]

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_UPSTREAM_MODEL = REPO_ROOT / "upstream" / "otel-semconv" / "v1.43.0" / "model"
DEFAULT_EXTENSION_MODEL = REPO_ROOT / "model" / "extensions"


class ModelRegistryConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    upstream_model: Path = DEFAULT_UPSTREAM_MODEL
    extension_model: Path = DEFAULT_EXTENSION_MODEL


class PostgresConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str = "postgresql+psycopg://entity_graph:entity_graph@postgres:5432/entity_graph"


class KafkaConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    bootstrap_servers: str = "kafka:9092"
    topic: str = "otel.servicegraph.metrics"
    group_id: str = "entity-graph-loader"
    auto_offset_reset: KafkaAutoOffsetReset = "earliest"
    batch_size: PositiveInt = 1000
    max_messages: PositiveInt | None = None


class GraphLoaderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    input: GraphLoaderInput = "kafka-otlp-json-metrics"
    registry: ModelRegistryConfig = Field(default_factory=ModelRegistryConfig)
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    kafka: KafkaConfig = Field(default_factory=KafkaConfig)


def graph_loader_config_from_env() -> GraphLoaderConfig:
    max_messages = _positive_int_or_none(os.getenv("GRAPH_KAFKA_MAX_MESSAGES"))
    return GraphLoaderConfig(
        input=_graph_loader_input(os.getenv("GRAPH_LOADER_INPUT", "kafka-otlp-json-metrics")),
        postgres=PostgresConfig(
            url=os.getenv("GRAPH_POSTGRES_URL", "postgresql+psycopg://entity_graph:entity_graph@postgres:5432/entity_graph")
        ),
        kafka=KafkaConfig(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
            topic=os.getenv("GRAPH_KAFKA_TOPIC", "otel.servicegraph.metrics"),
            group_id=os.getenv("GRAPH_KAFKA_GROUP_ID", "entity-graph-loader"),
            auto_offset_reset=_kafka_auto_offset_reset(os.getenv("GRAPH_KAFKA_AUTO_OFFSET_RESET", "earliest")),
            batch_size=int(os.getenv("GRAPH_KAFKA_BATCH_SIZE", "1000")),
            max_messages=max_messages,
        ),
    )


def _graph_loader_input(value: str) -> GraphLoaderInput:
    if value not in {"stdin-observations", "stdin-otlp-json-logs", "stdin-otlp-json-metrics", "kafka-otlp-json-metrics"}:
        raise ValueError(f"unsupported graph loader input mode: {value}")
    return cast(GraphLoaderInput, value)


def _kafka_auto_offset_reset(value: str) -> KafkaAutoOffsetReset:
    if value not in {"earliest", "latest"}:
        raise ValueError(f"unsupported Kafka auto offset reset value: {value}")
    return cast(KafkaAutoOffsetReset, value)


def _positive_int_or_none(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("expected a positive integer")
    return parsed
