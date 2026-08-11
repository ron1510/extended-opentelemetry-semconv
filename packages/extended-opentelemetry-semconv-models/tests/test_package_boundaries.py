"""Architectural dependency tests for independently publishable packages."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_RULES = {
    "extended-opentelemetry-semconv-models": {
        "extended_otel_semconv_codegen",
        "extended_otel_semconv_gremlin",
        "extended_otel_servicegraph_engine",
        "extended_otel_servicegraph_ingest",
        "gremlin_python",
        "opentelemetry",
        "yaml",
    },
    "extended-opentelemetry-semconv-codegen": {
        "extended_otel_semconv",
        "extended_otel_semconv_gremlin",
        "extended_otel_servicegraph_engine",
        "extended_otel_servicegraph_ingest",
        "gremlin_python",
        "opentelemetry",
    },
    "extended-opentelemetry-servicegraph-engine": {
        "extended_otel_semconv_codegen",
        "extended_otel_semconv_gremlin",
        "extended_otel_servicegraph_ingest",
        "gremlin_python",
        "opentelemetry",
        "yaml",
    },
    "extended-opentelemetry-servicegraph-ingest": {
        "extended_otel_semconv_codegen",
        "extended_otel_semconv_gremlin",
        "gremlin_python",
        "yaml",
    },
    "extended-opentelemetry-semconv-gremlin": {
        "extended_otel_semconv_codegen",
        "extended_otel_servicegraph_engine",
        "extended_otel_servicegraph_ingest",
        "opentelemetry",
        "yaml",
    },
}


@pytest.mark.parametrize(("package_name", "forbidden_roots"), PACKAGE_RULES.items())
def test_package_dependency_direction(package_name: str, forbidden_roots: set[str]) -> None:
    source_root = REPOSITORY_ROOT / "packages" / package_name / "src"
    violations: list[str] = []
    for source_file in source_root.rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            forbidden = _imported_roots(node) & forbidden_roots
            if forbidden:
                relative_path = source_file.relative_to(source_root)
                violations.append(f"{relative_path}: {', '.join(sorted(forbidden))}")

    assert not violations, f"{package_name} crossed its dependency boundary:\n" + "\n".join(violations)


def _imported_roots(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name.partition(".")[0] for alias in node.names}
    if isinstance(node, ast.ImportFrom) and node.module:
        return {node.module.partition(".")[0]}
    return set()
