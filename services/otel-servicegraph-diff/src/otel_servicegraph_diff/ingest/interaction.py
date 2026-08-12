"""Convert normalized Collector datapoints into engine observations."""

from __future__ import annotations

from collections.abc import Mapping

from extended_otel_semconv.entities import SemanticEntity
from extended_otel_semconv.relationships import service_graph_relationships
from otel_servicegraph_diff.engine.interaction import (
    DimensionMap,
    InteractionEndpoint,
    InteractionEntityRef,
    InteractionGraph,
    InteractionMetric,
    InteractionObservation,
    MetricValue,
    TelemetryScalar,
    build_interaction_id,
)
from otel_servicegraph_diff.engine.metrics import MetricPoint, MetricTemporality
from otel_servicegraph_diff.engine.observation import EdgeObservation, EntityObservation
from otel_servicegraph_diff.ingest.service_graph import (
    entities_from_service_graph_side,
    observations_from_service_graph_datapoint,
    service_graph_edge_type,
)


def observation_from_metric_point(point: MetricPoint) -> InteractionObservation | None:
    return observation_from_servicegraph_datapoint(
        metric_name=point.name,
        attributes=point.attributes,
        value=point.value,
        observed_at_unix_nano=point.observed_at_unix_nano,
        temporality=point.temporality,
        start_time_unix_nano=point.start_time_unix_nano,
    )


def observation_from_servicegraph_datapoint(
    metric_name: str,
    attributes: Mapping[str, TelemetryScalar],
    value: MetricValue,
    observed_at_unix_nano: int | None,
    *,
    temporality: MetricTemporality = "cumulative",
    start_time_unix_nano: int | None = None,
) -> InteractionObservation | None:
    client_name = _string_attribute(attributes, "client")
    server_name = _string_attribute(attributes, "server")
    if client_name is None or server_name is None or observed_at_unix_nano is None:
        return None
    dimensions: DimensionMap = {
        key: attribute_value
        for key, attribute_value in attributes.items()
        if key not in {"client", "server", "connection_type"}
    }
    client_entities = _entity_refs(entities_from_service_graph_side(attributes, "client", client_name))
    server_entities = _entity_refs(entities_from_service_graph_side(attributes, "server", server_name))
    connection_type = service_graph_edge_type(attributes)
    graph_observations = observations_from_service_graph_datapoint(
        metric_name=metric_name,
        attributes=dict(attributes),
        value=value,
        observed_at_unix_nano=observed_at_unix_nano,
        relationships=service_graph_relationships(),
    )
    return InteractionObservation(
        interaction_id=build_interaction_id(client_name, server_name, connection_type, dimensions),
        metric_name=metric_name,
        metric=InteractionMetric(
            value=value,
            temporality=temporality,
            start_time_unix_nano=start_time_unix_nano,
        ),
        observed_at_unix_nano=observed_at_unix_nano,
        client=InteractionEndpoint(service=client_name, entities=client_entities),
        server=InteractionEndpoint(service=server_name, entities=server_entities),
        connection_type=connection_type,
        dimensions=dimensions,
        graph=InteractionGraph(
            nodes=tuple(
                observation.entity
                for observation in graph_observations
                if isinstance(observation, EntityObservation)
            ),
            edges=tuple(
                observation.edge
                for observation in graph_observations
                if isinstance(observation, EdgeObservation)
            ),
        ),
    )


def _entity_refs(entities: list[SemanticEntity]) -> tuple[InteractionEntityRef, ...]:
    return tuple(InteractionEntityRef(id=entity.entity_id, type=entity.entity_type) for entity in entities)


def _string_attribute(attributes: Mapping[str, TelemetryScalar], key: str) -> str | None:
    value = attributes.get(key)
    return value if isinstance(value, str) and value else None
