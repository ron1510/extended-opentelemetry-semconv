from __future__ import annotations

from extended_otel_semconv import entities_from_attributes
from extended_otel_semconv.relationships import RelationshipDefinition
from otel_servicegraph_diff.engine.relationships import relationship_allows, relationship_edges


def test_relationship_edges_are_derived_from_observed_entity_types() -> None:
    relationships = (
        RelationshipDefinition(
            id="relationship.service_exposes_endpoint",
            type="relationship",
            name="exposes",
            source_entity="service",
            target_entity="app.endpoint",
            source_signals=("service_graph",),
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

    edges = relationship_edges(entities, relationships)

    assert edges == (
        (
            "service:checkout-api",
            "app.endpoint:checkout-api:payments:POST:%2Fcheckout%2F%7Bcart_id%7D",
            "exposes",
        ),
    )


def test_relationship_allows_dependency_edges() -> None:
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

    assert relationship_allows(relationships, "service", "service", "calls")
