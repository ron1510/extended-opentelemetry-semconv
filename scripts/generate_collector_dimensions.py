"""Generate the Collector service-graph dimensions used by the Helm chart."""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "extended-opentelemetry-semconv" / "src"))

from extended_otel_semconv.graph.dimensions import service_graph_dimensions  # noqa: E402
from extended_otel_semconv.registry.validation import load_model_registry, validate_extension_model  # noqa: E402

UPSTREAM_MODEL = ROOT / "upstream" / "otel-semconv" / "v1.43.0" / "model"
EXTENSION_MODEL = ROOT / "model" / "extensions"
OUTPUT = ROOT / "deploy" / "helm" / "servicegraph-collector" / "files" / "dimensions.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Collector Helm chart dimensions.")
    parser.add_argument("--check", action="store_true", help="Fail if the generated dimensions are stale.")
    args = parser.parse_args()

    expected = render_dimensions()
    if args.check:
        return _check_file(OUTPUT, expected)
    OUTPUT.write_text(expected, encoding="utf-8")
    return 0


def render_dimensions() -> str:
    validate_extension_model(UPSTREAM_MODEL, EXTENSION_MODEL)
    upstream = load_model_registry(UPSTREAM_MODEL)
    extension = load_model_registry(EXTENSION_MODEL)
    registry = upstream.model_copy(update={"groups": (*upstream.groups, *extension.groups)})
    return yaml.safe_dump(
        {"dimensions": service_graph_dimensions(registry)},
        sort_keys=False,
        default_flow_style=False,
    )


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
