from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import RLock
from time import time

from extended_otel_semconv import AppEndpoint, entities_from_attributes
from extended_otel_semconv.entities import SemanticEntity
from extended_otel_semconv.entities import quoted_entity_id
from extended_otel_semconv.graph.evidence import (
    graph_edge,
    graph_node_from_entity,
    reinforce_graph_edge,
    reinforce_graph_node,
)
from extended_otel_semconv.graph.metrics import (
    SERVICE_GRAPH_REQUEST_FAILED_TOTAL,
    SERVICE_GRAPH_REQUEST_TOTAL,
    MetricPoint,
)
from extended_otel_semconv.graph.model import GraphEdge, GraphNode, GraphSnapshot, SourceSignal
from extended_otel_semconv.graph.otlp import SpanRecord
from extended_otel_semconv.graph.relationships import relationship_allows, relationship_edges
from extended_otel_semconv.registry.model import RelationshipDefinition
from extended_otel_semconv.registry.validation import load_model_registry

DEFAULT_TTL_SECONDS = 900.0
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RELATIONSHIPS = tuple(
    load_model_registry(ROOT / "model" / "extensions").relationships_by_id.values()
)


class EntityGraph:
    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time,
        relationships: tuple[RelationshipDefinition, ...] = DEFAULT_RELATIONSHIPS,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._relationships = relationships
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._lock = RLock()

    def ingest_spans(self, spans: list[SpanRecord]) -> None:
        with self._lock:
            now = self._clock()
            self.prune(now)
            for span in spans:
                self.ingest_span(span, now)

    def ingest_span(self, span: SpanRecord, now: float | None = None) -> None:
        with self._lock:
            seen_at = self._clock() if now is None else now
            entities = _entities_for_span(span)
            for entity in entities:
                self._upsert_node(entity, seen_at, "trace")
            self._apply_relationships(entities, "trace", seen_at)

    def ingest_metric_points(self, points: list[MetricPoint]) -> None:
        with self._lock:
            now = self._clock()
            self.prune(now)
            for point in points:
                self._ingest_service_graph_point(point, now)

    def snapshot(self) -> GraphSnapshot:
        with self._lock:
            now = self._clock()
            self.prune(now)
            return GraphSnapshot(
                entities=sorted(self._nodes.values(), key=lambda node: node.id),
                edges=sorted(self._edges.values(), key=lambda edge: edge.id),
            )

    def prune(self, now: float | None = None) -> None:
        with self._lock:
            cutoff = (self._clock() if now is None else now) - self._ttl_seconds
            self._nodes = {node_id: node for node_id, node in self._nodes.items() if node.last_seen >= cutoff}
            self._edges = {edge_id: edge for edge_id, edge in self._edges.items() if edge.last_seen >= cutoff}

    def _upsert_node(self, entity: SemanticEntity, seen_at: float, source_signal: SourceSignal) -> None:
        existing = self._nodes.get(entity.entity_id)
        if existing is None:
            self._nodes[entity.entity_id] = graph_node_from_entity(entity, seen_at, source_signal)
            return
        self._nodes[entity.entity_id] = reinforce_graph_node(existing, entity, seen_at, source_signal)

    def _apply_relationships(
        self,
        entities: list[SemanticEntity],
        source_signal: SourceSignal,
        seen_at: float,
    ) -> None:
        for edge in relationship_edges(entities, self._relationships, source_signal):
            self._upsert_edge(edge.source, edge.target, edge.type, seen_at, source_signal)

    def _upsert_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        seen_at: float,
        source_signal: SourceSignal,
        attributes: dict[str, object] | None = None,
    ) -> None:
        edge = graph_edge(source, target, edge_type, seen_at, source_signal, attributes)
        existing = self._edges.get(edge.id)
        if existing is None:
            self._edges[edge.id] = edge
            return
        self._edges[edge.id] = reinforce_graph_edge(existing, edge, seen_at)

    def _ingest_service_graph_point(self, point: MetricPoint, seen_at: float) -> None:
        if point.name not in {SERVICE_GRAPH_REQUEST_TOTAL, SERVICE_GRAPH_REQUEST_FAILED_TOTAL}:
            return
        client = _string_attribute(point.attributes, "client")
        server = _string_attribute(point.attributes, "server")
        if client is None or server is None:
            return
        client_entities = _entities_from_service_graph_side(point.attributes, "client", client)
        server_entities = _entities_from_service_graph_side(point.attributes, "server", server)
        for entity in [*client_entities, *server_entities]:
            self._upsert_node(entity, seen_at, "service_graph")
        self._apply_relationships(client_entities, "service_graph", seen_at)
        self._apply_relationships(server_entities, "service_graph", seen_at)

        source = quoted_entity_id("service", client)
        target = quoted_entity_id("service", server)
        if source not in self._nodes or target not in self._nodes or source == target:
            return
        edge_type = _service_graph_edge_type(point.attributes)
        if not relationship_allows(self._relationships, "service", "service", edge_type, "service_graph"):
            return

        attributes = {
            key: value
            for key, value in point.attributes.items()
            if key not in {"client", "server"}
        }
        if point.name == SERVICE_GRAPH_REQUEST_TOTAL:
            attributes["service_graph.request.total"] = point.value
        else:
            attributes["service_graph.request.failed.total"] = point.value
        target_endpoint_id = _target_endpoint_id(server, point.attributes)
        if target_endpoint_id is not None and target_endpoint_id in self._nodes:
            attributes["target_endpoint.id"] = target_endpoint_id
        self._upsert_edge(source, target, edge_type, seen_at, "service_graph", attributes)


def _entities_for_span(span: SpanRecord) -> list[SemanticEntity]:
    return _entities_for_attributes(span.attributes, is_server=span.is_server)


def _service_graph_edge_type(attributes: dict[str, object]) -> str:
    connection_type = _string_attribute(attributes, "connection_type")
    if connection_type == "messaging_system":
        return "publishes_to"
    if connection_type == "database":
        return "queries"
    return "calls"


def _target_endpoint_id(server: str, attributes: dict[str, object]) -> str | None:
    namespace = _string_attribute(attributes, "server_service.namespace")
    method = _string_attribute(attributes, "server_http.request.method")
    route = _string_attribute(attributes, "server_http.route")
    if namespace is None or method is None or route is None:
        return None
    return quoted_entity_id("app.endpoint", server, namespace, method, route)


def _entities_from_service_graph_side(
    attributes: dict[str, object],
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


def _entities_for_attributes(attributes: dict[str, object], is_server: bool) -> list[SemanticEntity]:
    entities = entities_from_attributes(attributes)
    if is_server:
        return entities
    return [entity for entity in entities if not isinstance(entity, AppEndpoint)]


def _string_attribute(attributes: dict[str, object], key: str) -> str | None:
    value = attributes.get(key)
    if isinstance(value, str) and value != "":
        return value
    return None
