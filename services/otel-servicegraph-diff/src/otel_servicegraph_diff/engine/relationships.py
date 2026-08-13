"""Pure relationship expansion from registry definitions and observed entities."""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from extended_otel_semconv.entities import SemanticEntity
from extended_otel_semconv.relationships import RelationshipDefinition


class RelationshipEdge(NamedTuple):
    source: str
    target: str
    type: str


def relationship_edges(
    entities: Sequence[SemanticEntity],
    relationships: Sequence[RelationshipDefinition],
) -> tuple[RelationshipEdge, ...]:
    entities_by_type = group_entities_by_type(entities)
    edges: list[RelationshipEdge] = []
    for relationship in relationships:
        if relationship.source_entity == relationship.target_entity:
            continue
        edges.extend(edges_for_relationship(entities_by_type, relationship))
    return tuple(edges)


def relationship_allows(
    relationships: Sequence[RelationshipDefinition],
    source_entity: str,
    target_entity: str,
    relationship_name: str,
) -> bool:
    return any(
        relationship.source_entity == source_entity
        and relationship.target_entity == target_entity
        and relationship.name == relationship_name
        for relationship in relationships
    )


def group_entities_by_type(entities: Sequence[SemanticEntity]) -> dict[str, tuple[SemanticEntity, ...]]:
    grouped: dict[str, list[SemanticEntity]] = {}
    for entity in entities:
        grouped.setdefault(entity.entity_type, []).append(entity)
    return {entity_type: tuple(values) for entity_type, values in grouped.items()}


def edges_for_relationship(
    entities_by_type: dict[str, tuple[SemanticEntity, ...]],
    relationship: RelationshipDefinition,
) -> tuple[RelationshipEdge, ...]:
    return tuple(
        RelationshipEdge(source.entity_id, target.entity_id, relationship.name)
        for source in entities_by_type.get(relationship.source_entity, ())
        for target in entities_by_type.get(relationship.target_entity, ())
        if source.entity_id != target.entity_id
    )
