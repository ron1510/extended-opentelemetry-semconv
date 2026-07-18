"""CLI entrypoint for the graph loader service."""

from __future__ import annotations

import argparse
from typing import cast

from extended_otel_semconv.services.graph_loader.config import (
    GraphLoaderConfig,
    GraphLoaderInput,
    KafkaAutoOffsetReset,
    KafkaConfig,
    ModelRegistryConfig,
    PostgresConfig,
    graph_loader_config_from_env,
)
from extended_otel_semconv.services.graph_loader.loader import run_graph_loader


def main() -> int:
    env_config = graph_loader_config_from_env()
    parser = argparse.ArgumentParser(description="Persist graph observations into Postgres.")
    parser.add_argument(
        "--postgres-url",
        default=env_config.postgres.url,
        help="SQLAlchemy Postgres URL. Defaults to GRAPH_POSTGRES_URL or the local Compose database.",
    )
    parser.add_argument(
        "--input",
        choices=("stdin-observations", "stdin-otlp-json-logs", "stdin-otlp-json-metrics", "kafka-otlp-json-metrics"),
        default=env_config.input,
        help="Input mode. Kafka mode consumes Collector OTLP JSON metric records.",
    )
    parser.add_argument("--kafka-bootstrap", default=env_config.kafka.bootstrap_servers)
    parser.add_argument("--kafka-topic", default=env_config.kafka.topic)
    parser.add_argument("--kafka-group-id", default=env_config.kafka.group_id)
    parser.add_argument("--kafka-auto-offset-reset", choices=("earliest", "latest"), default=env_config.kafka.auto_offset_reset)
    parser.add_argument("--kafka-batch-size", type=int, default=env_config.kafka.batch_size)
    parser.add_argument("--max-messages", type=int, default=env_config.kafka.max_messages)
    parser.add_argument("--upstream-model", type=str, default=str(env_config.registry.upstream_model))
    parser.add_argument("--extension-model", type=str, default=str(env_config.registry.extension_model))
    args = parser.parse_args()

    config = GraphLoaderConfig(
        input=_graph_loader_input(args.input),
        registry=ModelRegistryConfig(upstream_model=args.upstream_model, extension_model=args.extension_model),
        postgres=PostgresConfig(url=args.postgres_url),
        kafka=KafkaConfig(
            bootstrap_servers=args.kafka_bootstrap,
            topic=args.kafka_topic,
            group_id=args.kafka_group_id,
            auto_offset_reset=_kafka_auto_offset_reset(args.kafka_auto_offset_reset),
            batch_size=args.kafka_batch_size,
            max_messages=args.max_messages,
        ),
    )
    return run_graph_loader(config)


def _graph_loader_input(value: str) -> GraphLoaderInput:
    if value not in {"stdin-observations", "stdin-otlp-json-logs", "stdin-otlp-json-metrics", "kafka-otlp-json-metrics"}:
        raise ValueError(f"unsupported graph loader input mode: {value}")
    return cast(GraphLoaderInput, value)


def _kafka_auto_offset_reset(value: str) -> KafkaAutoOffsetReset:
    if value not in {"earliest", "latest"}:
        raise ValueError(f"unsupported Kafka auto offset reset value: {value}")
    return cast(KafkaAutoOffsetReset, value)


if __name__ == "__main__":
    raise SystemExit(main())
