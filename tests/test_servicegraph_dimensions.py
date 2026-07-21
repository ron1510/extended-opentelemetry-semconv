from __future__ import annotations

from pathlib import Path

from extended_otel_semconv.graph.dimensions import service_graph_dimensions
from extended_otel_semconv.registry.validation import load_model_registry

ROOT = Path(__file__).resolve().parents[1]


def test_servicegraph_dimensions_come_from_participating_entity_refs() -> None:
    upstream = load_model_registry(ROOT / "upstream" / "otel-semconv" / "v1.43.0" / "model")
    extension = load_model_registry(ROOT / "model" / "extensions")
    registry = upstream.model_copy(update={"groups": (*upstream.groups, *extension.groups)})

    dimensions = service_graph_dimensions(registry)

    assert "service.name" in dimensions
    assert "service.namespace" in dimensions
    assert "k8s.pod.uid" in dimensions
    assert "http.route" in dimensions
    assert "k8s.pod.label" not in dimensions
    assert "k8s.pod.annotation" not in dimensions
