"""Architectural tests for the independently publishable semantic library."""

from __future__ import annotations

import ast
from pathlib import Path

SEMANTIC_PACKAGE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "extended_otel_semconv"
)
FORBIDDEN_IMPORT_ROOTS = {
    "confluent_kafka",
    "otel_servicegraph_diff",
    "pydantic_settings",
    "pyflink",
}


def test_semantic_library_has_no_runtime_application_imports() -> None:
    violations: list[str] = []
    for source_file in SEMANTIC_PACKAGE.rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            imported_roots = _imported_roots(node)
            forbidden = imported_roots & FORBIDDEN_IMPORT_ROOTS
            if forbidden:
                relative_path = source_file.relative_to(SEMANTIC_PACKAGE)
                violations.append(f"{relative_path}: {', '.join(sorted(forbidden))}")

    assert not violations, "Semantic library crossed its application boundary:\n" + "\n".join(violations)


def _imported_roots(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name.partition(".")[0] for alias in node.names}
    if isinstance(node, ast.ImportFrom) and node.module:
        return {node.module.partition(".")[0]}
    return set()
