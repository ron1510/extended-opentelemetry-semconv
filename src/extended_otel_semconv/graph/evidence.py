from __future__ import annotations

from extended_otel_semconv.entities import SemanticEntity
from extended_otel_semconv.graph.model import GraphEdge, GraphNode, SourceSignal


def graph_node_from_entity(entity: SemanticEntity, seen_at: float, source_signal: SourceSignal) -> GraphNode:
    return GraphNode(
        id=entity.entity_id,
        type=entity.entity_type,
        first_seen=seen_at,
        last_seen=seen_at,
        sources={source_signal: 1},
        attributes=entity_attributes(entity),
    )


def reinforce_graph_node(node: GraphNode, entity: SemanticEntity, seen_at: float, source_signal: SourceSignal) -> GraphNode:
    return node.model_copy(
        update={
            "last_seen": seen_at,
            "observations": node.observations + 1,
            "sources": increment_source(node.sources, source_signal),
            "attributes": {**node.attributes, **entity_attributes(entity)},
        }
    )


def graph_edge(
    source: str,
    target: str,
    edge_type: str,
    seen_at: float,
    source_signal: SourceSignal,
    attributes: dict[str, object] | None = None,
) -> GraphEdge:
    return GraphEdge(
        source=source,
        target=target,
        type=edge_type,
        first_seen=seen_at,
        last_seen=seen_at,
        sources={source_signal: 1},
        attributes=attributes or {},
    )


def reinforce_graph_edge(edge: GraphEdge, observation: GraphEdge, seen_at: float) -> GraphEdge:
    return edge.model_copy(
        update={
            "last_seen": seen_at,
            "observations": edge.observations + 1,
            "sources": merge_sources(edge.sources, observation.sources),
            "attributes": {**edge.attributes, **observation.attributes},
        }
    )


def entity_attributes(entity: SemanticEntity) -> dict[str, object]:
    return entity.model_dump(mode="json", by_alias=True, exclude={"entity_id"}, exclude_none=True)


def increment_source(sources: dict[str, int], source_signal: SourceSignal) -> dict[str, int]:
    return sources | {source_signal: sources.get(source_signal, 0) + 1}


def merge_sources(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    merged = dict(left)
    for source_signal, count in right.items():
        merged[source_signal] = merged.get(source_signal, 0) + count
    return merged
