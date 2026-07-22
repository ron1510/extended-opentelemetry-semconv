from __future__ import annotations

from pathlib import Path

import pytest

from scripts.runtime_dependencies import runtime_dependencies


def test_runtime_dependencies_are_read_from_both_packages() -> None:
    root = Path(__file__).resolve().parents[1]

    dependencies = runtime_dependencies(
        (
            root / "packages" / "extended-opentelemetry-semconv" / "pyproject.toml",
            root / "apps" / "otel-servicegraph-diff" / "pyproject.toml",
        ),
        excluded={"extended-opentelemetry-semconv"},
    )

    assert dependencies == (
        "apache-flink==2.2.1",
        "opentelemetry-proto==1.44.0",
        "pydantic==2.13.4",
        "pydantic-settings==2.14.2",
        "PyYAML==6.0.3",
    )


def test_conflicting_runtime_dependencies_are_rejected(tmp_path: Path) -> None:
    first = tmp_path / "first.toml"
    second = tmp_path / "second.toml"
    first.write_text('[project]\ndependencies = ["example==1"]\n', encoding="utf-8")
    second.write_text('[project]\ndependencies = ["example==2"]\n', encoding="utf-8")

    with pytest.raises(ValueError, match="conflicting requirements"):
        runtime_dependencies((first, second), excluded=set())
