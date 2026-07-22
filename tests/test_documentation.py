from __future__ import annotations

import re
from pathlib import Path

from extended_otel_semconv.graph.metrics import (
    SERVICE_GRAPH_REQUEST_FAILED_TOTAL,
    SERVICE_GRAPH_REQUEST_TOTAL,
)
from otel_servicegraph_diff.config import InteractionDiffConfig

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+\]\((?P<target>[^)]+)\)")
DOCUMENTATION_FILES = (
    ROOT / "README.md",
    ROOT / "deploy" / "helm" / "servicegraph-collector" / "README.md",
    ROOT / "deploy" / "openshift" / "README.md",
    *sorted(DOCS.glob("*.md")),
)


def test_repository_local_documentation_links_resolve() -> None:
    broken: list[str] = []
    for document in DOCUMENTATION_FILES:
        text = document.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(text):
            target = match.group("target").partition("#")[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                broken.append(f"{document.relative_to(ROOT)} -> {target}")

    assert broken == []


def test_runtime_environment_variables_are_documented() -> None:
    operations = (DOCS / "deployment-and-operations.md").read_text(encoding="utf-8")
    aliases = {
        field.validation_alias
        for field in InteractionDiffConfig.model_fields.values()
        if isinstance(field.validation_alias, str)
    }

    assert aliases
    assert all(f"`{alias}`" in operations for alias in aliases)


def test_topics_and_supported_metrics_are_documented_from_code_constants() -> None:
    architecture = (DOCS / "architecture.md").read_text(encoding="utf-8")
    operations = (DOCS / "deployment-and-operations.md").read_text(encoding="utf-8")
    config_fields = InteractionDiffConfig.model_fields
    topics = {
        str(config_fields["input_topic"].default),
        str(config_fields["output_topic"].default),
        str(config_fields["dlq_topic"].default),
    }

    assert all(topic in architecture and topic in operations for topic in topics)
    assert SERVICE_GRAPH_REQUEST_TOTAL in architecture
    assert SERVICE_GRAPH_REQUEST_FAILED_TOTAL in architecture


def test_sticky_collector_chart_and_legacy_baseline_are_distinguished() -> None:
    operations = (DOCS / "deployment-and-operations.md").read_text(encoding="utf-8")
    normalized = " ".join(operations.split())

    assert "### Legacy Raw Manifest" in operations
    assert "single-replica reference baseline" in normalized
    assert "### Implemented Scaled Collector Design" in operations
    assert "exactly two service-graph Collector replicas" in normalized
    assert "stable ordinal DNS" in normalized
    assert "implemented by the standalone Helm chart" in normalized
