from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from extended_otel_semconv.registry.validation import load_model_registry, validate_extension_model  # noqa: E402

UPSTREAM_MODEL = ROOT / "upstream" / "otel-semconv" / "v1.43.0" / "model"
EXTENSION_MODEL = ROOT / "model" / "extensions"
COLLECTOR_CONFIG = ROOT / "deploy" / "local" / "otelcol.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the local Collector config from the entity registry.")
    parser.add_argument("--check", action="store_true", help="Fail if the Collector config is not up to date.")
    args = parser.parse_args()

    content = render_collector_config()
    if args.check:
        return _check_file(COLLECTOR_CONFIG, content)
    COLLECTOR_CONFIG.write_text(content, encoding="utf-8")
    return 0


def render_collector_config() -> str:
    validate_extension_model(UPSTREAM_MODEL, EXTENSION_MODEL)
    upstream = load_model_registry(UPSTREAM_MODEL)
    extension = load_model_registry(EXTENSION_MODEL)
    dimensions = sorted({*upstream.attributes_by_id, *extension.attributes_by_id})
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
            "batch": {
                "timeout": "1s",
                "send_batch_size": 256,
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
        "exporters": {
            "otlp_http/entitygraph": {
                "endpoint": "http://graph:8000",
            },
        },
        "service": {
            "extensions": ["health_check"],
            "pipelines": {
                "traces": {
                    "receivers": ["otlp"],
                    "processors": ["memory_limiter", "batch"],
                    "exporters": ["otlp_http/entitygraph", "service_graph"],
                },
                "metrics/servicegraph": {
                    "receivers": ["service_graph"],
                    "processors": ["memory_limiter", "batch"],
                    "exporters": ["otlp_http/entitygraph"],
                },
            },
        },
    }
    return yaml.safe_dump(config, sort_keys=False, default_flow_style=False)


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
