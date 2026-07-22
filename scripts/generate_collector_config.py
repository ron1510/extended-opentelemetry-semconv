"""Generate the single local/prod-shaped Collector config from the merged registry."""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "extended-opentelemetry-semconv" / "src"))

from extended_otel_semconv.graph.dimensions import service_graph_dimensions  # noqa: E402
from extended_otel_semconv.registry.validation import load_model_registry, validate_extension_model  # noqa: E402

UPSTREAM_MODEL = ROOT / "upstream" / "otel-semconv" / "v1.43.0" / "model"
EXTENSION_MODEL = ROOT / "model" / "extensions"
COLLECTOR_CONFIG = ROOT / "deploy" / "local" / "otelcol.yaml"
OPENSHIFT_COLLECTOR_CONFIG = ROOT / "deploy" / "openshift" / "otelcol.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the local Collector config from the entity registry.")
    parser.add_argument("--check", action="store_true", help="Fail if the Collector config is not up to date.")
    args = parser.parse_args()

    outputs = {
        COLLECTOR_CONFIG: render_collector_config(),
        OPENSHIFT_COLLECTOR_CONFIG: render_openshift_collector_config(),
    }
    if args.check:
        return max(_check_file(path, content) for path, content in outputs.items())
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return 0


def render_collector_config() -> str:
    dimensions = _service_graph_dimensions()
    config = _base_collector_config(dimensions)
    config["exporters"] = {
        "kafka/servicegraph_metrics": {
            "brokers": ["kafka:9092"],
            "metrics": {
                "topic": "otel.servicegraph.metrics",
                "encoding": "otlp_json",
            },
            "producer": {
                "compression": "gzip",
            },
            "sending_queue": {
                "enabled": True,
                "sizer": "items",
                "queue_size": 100000,
            },
            "retry_on_failure": {
                "enabled": True,
                "max_elapsed_time": "0s",
            },
        },
    }
    config["service"]["extensions"] = ["health_check"]
    return yaml.safe_dump(config, sort_keys=False, default_flow_style=False)


def render_openshift_collector_config() -> str:
    dimensions = _service_graph_dimensions()
    config = _base_collector_config(dimensions)
    config["extensions"]["file_storage/queue"] = {
        "directory": "/var/lib/otelcol/queue",
        "create_directory": True,
        "timeout": "10s",
        "compaction": {
            "on_start": True,
            "on_rebound": False,
        },
    }
    config["exporters"] = {
        "kafka/servicegraph_metrics": {
            "brokers": ["${env:KAFKA_BOOTSTRAP_SERVERS}"],
            "metrics": {
                "topic": "${env:INTERACTION_DIFF_INPUT_TOPIC}",
                "encoding": "otlp_json",
            },
            "tls": {
                "insecure": False,
                "insecure_skip_verify": False,
                "ca_file": "/etc/kafka/tls/ca.crt",
            },
            "auth": {
                "sasl": {
                    "username": "${env:KAFKA_SASL_USERNAME}",
                    "password": "${env:KAFKA_SASL_PASSWORD}",
                    "mechanism": "SCRAM-SHA-256",
                },
            },
            "producer": {
                "compression": "gzip",
                "required_acks": -1,
                "allow_auto_topic_creation": False,
            },
            "sending_queue": {
                "enabled": True,
                "storage": "file_storage/queue",
                "sizer": "items",
                "num_consumers": 4,
                "queue_size": 10000,
            },
            "retry_on_failure": {
                "enabled": True,
                "initial_interval": "1s",
                "max_interval": "30s",
                "max_elapsed_time": "0s",
            },
        },
    }
    config["service"]["extensions"] = ["health_check", "file_storage/queue"]
    return yaml.safe_dump(config, sort_keys=False, default_flow_style=False)


def _service_graph_dimensions() -> list[str]:
    validate_extension_model(UPSTREAM_MODEL, EXTENSION_MODEL)
    upstream = load_model_registry(UPSTREAM_MODEL)
    extension = load_model_registry(EXTENSION_MODEL)
    registry = upstream.model_copy(update={"groups": (*upstream.groups, *extension.groups)})
    return service_graph_dimensions(registry)


def _base_collector_config(dimensions: list[str]) -> dict[str, Any]:
    config: dict[str, Any] = {
        "extensions": {
            "health_check": {
                "endpoint": "localhost:13133",
            },
        },
        "receivers": {
            "otlp": {
                "protocols": {
                    "grpc": {"endpoint": "0.0.0.0:4317"},
                    "http": {"endpoint": "0.0.0.0:4318"},
                },
            },
        },
        "processors": {
            "memory_limiter": {
                "check_interval": "1s",
                "limit_percentage": 80,
                "spike_limit_percentage": 20,
            },
            "batch/traces": {
                "timeout": "1s",
                "send_batch_size": 256,
            },
            "batch/servicegraph_metrics": {
                "timeout": "1s",
                "send_batch_size": 1,
                "send_batch_max_size": 1,
            },
        },
        "connectors": {
            "service_graph": {
                "dimensions": dimensions,
                "virtual_node_peer_attributes": [],
                "database_name_attributes": ["db.namespace", "db.name"],
                "store": {
                    "ttl": "10s",
                    "max_items": 10000,
                },
                "metrics_flush_interval": "1s",
            },
        },
        "exporters": {},
        "service": {
            "extensions": [],
            "pipelines": {
                "traces": {
                    "receivers": ["otlp"],
                    "processors": ["memory_limiter", "batch/traces"],
                    "exporters": ["service_graph"],
                },
                "metrics/servicegraph": {
                    "receivers": ["service_graph"],
                    "processors": ["memory_limiter", "batch/servicegraph_metrics"],
                    "exporters": ["kafka/servicegraph_metrics"],
                },
            },
        },
    }
    return config


def _check_file(path: Path, expected: str) -> int:
    actual = path.read_text(encoding="utf-8") if path.exists() else ""
    if actual == expected:
        return 0
    print(f"{path} is not up to date")
    for line in difflib.unified_diff(
        actual.splitlines(),
        expected.splitlines(),
        fromfile=f"{path} (actual)",
        tofile=f"{path} (expected)",
        lineterm="",
    ):
        print(line)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
