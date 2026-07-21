"""Service graph datapoint normalization into graph observations."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

from extended_otel_semconv import AppEndpoint, entities_from_attributes
from extended_otel_semconv.entities import SemanticEntity, quoted_entity_id
from extended_otel_semconv.graph.metrics import SERVICE_GRAPH_REQUEST_FAILED_TOTAL
from extended_otel_semconv.graph.observation import (
    EdgeObservation,
    EntityObservation,
    GraphObservation,
    ObservedEdge,
    ObservedEntity,
)
from extended_otel_semconv.graph.relationships import relationship_allows, relationship_edges
from extended_otel_semconv.registry.model import RelationshipDefinition


def observations_from_service_graph_datapoint(
    metric_name: str,
    attributes: dict[str, object],
    value: int | float,
    observed_at_unix_nano: int | None,
    relationships: Sequence[RelationshipDefinition],
) -> tuple[GraphObservation, ...]:
    client = _string_attribute(attributes, "client")
    server = _string_attribute(attributes, "server")
    if client is None or server is None:
        return ()

    client_entities = entities_from_service_graph_side(attributes, "client", client)
    server_entities = entities_from_service_graph_side(attributes, "server", server)
    observations: list[GraphObservation] = []
    for entity in [*client_entities, *server_entities]:
        observations.append(_entity_observation(entity, observed_at_unix_nano))
    for edge in relationship_edges(client_entities, relationships, "service_graph"):
        observations.append(_structural_edge_observation(edge.source, edge.target, edge.type, observed_at_unix_nano))
    for edge in relationship_edges(server_entities, relationships, "service_graph"):
        observations.append(_structural_edge_observation(edge.source, edge.target, edge.type, observed_at_unix_nano))

    source = quoted_entity_id("service", client)
    target = quoted_entity_id("service", server)
    edge_type = service_graph_edge_type(attributes)
    if source != target and relationship_allows(relationships, "service", "service", edge_type, "service_graph"):
        observations.append(
            _dependency_edge_observation(
                source=source,
                target=target,
                edge_type=edge_type,
                metric_name=metric_name,
                metric_value=value,
                attributes=attributes,
                observed_at_unix_nano=observed_at_unix_nano,
            )
        )
    return tuple(observations)


def entities_from_service_graph_side(
    attributes: Mapping[str, object],
    side: str,
    service_name: str,
) -> list[SemanticEntity]:
    side_prefix = f"{side}_"
    side_attributes = {
        key.removeprefix(side_prefix): value
        for key, value in attributes.items()
        if key.startswith(side_prefix)
    }
    side_attributes.setdefault("service.name", service_name)
    return _entities_for_attributes(side_attributes, is_server=side == "server")


def service_graph_edge_type(attributes: Mapping[str, object]) -> str:
    connection_type = _string_attribute(attributes, "connection_type")
    if connection_type == "messaging_system":
        return "publishes_to"
    if connection_type == "database":
        return "queries"
    return "calls"


def _entities_for_attributes(attributes: dict[str, object], is_server: bool) -> list[SemanticEntity]:
    entities = entities_from_attributes(attributes)
    if is_server:
        return entities
    return [entity for entity in entities if not isinstance(entity, AppEndpoint)]


def _entity_observation(entity: SemanticEntity, observed_at_unix_nano: int | None) -> EntityObservation:
    return EntityObservation(
        observation_id=_observation_id("entity", entity.entity_id, observed_at_unix_nano),
        observed_at_unix_nano=observed_at_unix_nano,
        source_signal="service_graph",
        entity=ObservedEntity(
            id=entity.entity_id,
            type=entity.entity_type,
            attributes=entity.model_dump(mode="json", by_alias=True, exclude={"entity_id"}, exclude_none=True),
        ),
    )


def _structural_edge_observation(
    source: str,
    target: str,
    edge_type: str,
    observed_at_unix_nano: int | None,
) -> EdgeObservation:
    return EdgeObservation(
        observation_id=_observation_id("edge", source, edge_type, target, observed_at_unix_nano),
        observed_at_unix_nano=observed_at_unix_nano,
        source_signal="service_graph",
        edge=ObservedEdge(source=source, target=target, type=edge_type),
    )


def _dependency_edge_observation(
    source: str,
    target: str,
    edge_type: str,
    metric_name: str,
    metric_value: int | float,
    attributes: dict[str, object],
    observed_at_unix_nano: int | None,
) -> EdgeObservation:
    edge_attributes = {
        key: value
        for key, value in attributes.items()
        if key not in {"client", "server"}
    }
    if metric_name == SERVICE_GRAPH_REQUEST_FAILED_TOTAL:
        edge_attributes["service_graph.request.failed.total"] = metric_value
    else:
        edge_attributes["service_graph.request.total"] = metric_value
    return EdgeObservation(
        observation_id=_observation_id("edge", source, edge_type, target, observed_at_unix_nano, metric_name),
        observed_at_unix_nano=observed_at_unix_nano,
        source_signal="service_graph",
        edge=ObservedEdge(source=source, target=target, type=edge_type, attributes=edge_attributes),
    )


def _observation_id(*parts: object) -> str:
    canonical = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _string_attribute(attributes: Mapping[str, object], key: str) -> str | None:
    value = attributes.get(key)
    if isinstance(value, str) and value != "":
        return value
    return None
