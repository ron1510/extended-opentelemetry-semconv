from __future__ import annotations

from extended_otel_semconv import entities_from_attributes
from extended_otel_semconv.graph.relationships import relationship_allows, relationship_edges
from extended_otel_semconv.registry.model import RelationshipDefinition


def test_relationship_edges_are_derived_from_observed_entity_types() -> None:
    relationships = (
        RelationshipDefinition(
            id="relationship.service_exposes_endpoint",
            type="relationship",
            name="exposes",
            source_entity="service",
            target_entity="app.endpoint",
            source_signals=("trace",),
        ),
    )
    entities = entities_from_attributes(
        {
            "service.name": "checkout-api",
            "service.namespace": "payments",
            "http.request.method": "POST",
            "http.route": "/checkout/{cart_id}",
        }
    )

    edges = relationship_edges(entities, relationships, "trace")

    assert edges == (
        (
            "service:checkout-api",
            "app.endpoint:checkout-api:payments:POST:%2Fcheckout%2F%7Bcart_id%7D",
            "exposes",
        ),
    )


def test_relationship_edges_ignore_unmatched_source_signals() -> None:
    relationships = (
        RelationshipDefinition(
            id="relationship.service_calls_service",
            type="relationship",
            name="calls",
            source_entity="service",
            target_entity="service",
            source_signals=("service_graph",),
        ),
    )
    entities = entities_from_attributes({"service.name": "checkout-api"})

    assert relationship_edges(entities, relationships, "trace") == ()


def test_relationship_allows_dependency_edges_from_service_graph_only() -> None:
    relationships = (
        RelationshipDefinition(
            id="relationship.service_calls_service",
            type="relationship",
            name="calls",
            source_entity="service",
            target_entity="service",
            source_signals=("service_graph",),
        ),
    )

    assert relationship_allows(relationships, "service", "service", "calls", "service_graph")
    assert not relationship_allows(relationships, "service", "service", "calls", "trace")
