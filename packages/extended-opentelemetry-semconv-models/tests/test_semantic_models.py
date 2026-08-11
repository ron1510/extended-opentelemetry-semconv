from __future__ import annotations

import pytest

from extended_otel_semconv import Service, ServiceCallsServiceEdge
from extended_otel_semconv.edges import edge_id, semantic_edge_from_data
from extended_otel_semconv.entities import entity_from_attributes
from extended_otel_semconv.errors import (
    SemanticIdentityMismatchError,
    SemanticModelValidationError,
    UnknownSemanticTypeError,
)
from extended_otel_semconv.generated import EDGE_MODELS, ENTITY_MODELS


def test_generated_registries_cover_entities_and_relationships() -> None:
    assert "service" in ENTITY_MODELS
    assert len(EDGE_MODELS) == 33
    assert EDGE_MODELS[("service", "calls", "service")] is ServiceCallsServiceEdge


def test_strict_entity_reconstruction_preserves_optional_fields_and_identity() -> None:
    entity = entity_from_attributes(
        "service",
        {"service.name": "checkout", "service.version": "1.4.0"},
        expected_id="service:checkout",
    )

    assert isinstance(entity, Service)
    assert entity.service_name == "checkout"
    assert entity.service_version == "1.4.0"


def test_strict_entity_reconstruction_rejects_unknown_missing_and_mismatched_data() -> None:
    with pytest.raises(UnknownSemanticTypeError, match="unknown"):
        entity_from_attributes("unknown", {})
    with pytest.raises(SemanticModelValidationError, match="identifying fields"):
        entity_from_attributes("service", {})
    with pytest.raises(SemanticIdentityMismatchError, match="does not match"):
        entity_from_attributes("service", {"service.name": "checkout"}, expected_id="service:other")


def test_concrete_edge_reconstruction_preserves_metrics_and_identity() -> None:
    expected_id = edge_id("service:storefront", "calls", "service:checkout")
    edge = semantic_edge_from_data(
        "calls",
        "service:storefront",
        "service:checkout",
        metrics={"service_graph.request.total": 12.0},
        expected_id=expected_id,
    )

    assert isinstance(edge, ServiceCallsServiceEdge)
    assert edge.metrics == {"service_graph.request.total": 12.0}
    assert edge.edge_id == expected_id


def test_edge_reconstruction_rejects_endpoints_relationships_and_identity_mismatches() -> None:
    with pytest.raises(UnknownSemanticTypeError, match="no generated semantic edge"):
        semantic_edge_from_data("calls", "k8s.pod:one", "service:checkout")
    with pytest.raises(SemanticModelValidationError, match="invalid semantic entity ID"):
        semantic_edge_from_data("calls", "invalid", "service:checkout")
    with pytest.raises(SemanticIdentityMismatchError, match="does not match"):
        semantic_edge_from_data(
            "calls",
            "service:storefront",
            "service:checkout",
            expected_id="edge:not-the-real-id",
        )
    with pytest.raises(ValueError, match="source_id must identify"):
        ServiceCallsServiceEdge(source_id="k8s.pod:one", target_id="service:checkout")
