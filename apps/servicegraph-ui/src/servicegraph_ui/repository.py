"""SQLite projection of authoritative graph-element lifecycle events."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from extended_otel_semconv.graph.elements import GraphEdge, GraphNode
from servicegraph_ui.models import (
    ElementView,
    EventView,
    GraphEdgeView,
    GraphNodeView,
    GraphView,
    ProjectionEvent,
    ProjectionUpsertEvent,
)

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS graph_elements (
    element_id TEXT PRIMARY KEY,
    element_kind TEXT NOT NULL CHECK (element_kind IN ('node', 'edge')),
    element_type TEXT NOT NULL,
    source_id TEXT,
    target_id TEXT,
    attributes_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    observed_at_unix_nano INTEGER NOT NULL,
    emitted_at_unix_ms INTEGER NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recent_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    operation TEXT NOT NULL,
    element_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    observed_at_unix_nano INTEGER NOT NULL,
    emitted_at_unix_ms INTEGER NOT NULL,
    topic TEXT NOT NULL,
    partition_id INTEGER NOT NULL,
    offset_id INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS consumer_offsets (
    topic TEXT NOT NULL,
    partition_id INTEGER NOT NULL,
    next_offset INTEGER NOT NULL,
    PRIMARY KEY (topic, partition_id)
);
CREATE INDEX IF NOT EXISTS ix_graph_elements_kind_type
ON graph_elements(element_kind, element_type);
CREATE INDEX IF NOT EXISTS ix_graph_edges_endpoints
ON graph_elements(source_id, target_id) WHERE element_kind = 'edge';
"""


class ProjectionRepository:
    def __init__(self, path: Path, recent_event_limit: int) -> None:
        self._path = path
        self._recent_event_limit = recent_event_limit

    def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def next_offset(self, topic: str, partition: int) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT next_offset FROM consumer_offsets WHERE topic = ? AND partition_id = ?",
                (topic, partition),
            ).fetchone()
        return int(row["next_offset"]) if row is not None else None

    def apply_event(self, topic: str, partition: int, offset: int, event: ProjectionEvent) -> bool:
        return self.apply_events(topic, partition, ((offset, event),)) == 1

    def apply_events(
        self,
        topic: str,
        partition: int,
        events: Sequence[tuple[int, ProjectionEvent]],
    ) -> int:
        if not events:
            return 0
        applied = 0
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT next_offset FROM consumer_offsets WHERE topic = ? AND partition_id = ?",
                (topic, partition),
            ).fetchone()
            next_offset = int(row["next_offset"]) if row is not None else None
            for offset, event in events:
                if next_offset is not None and offset < next_offset:
                    continue
                if isinstance(event, ProjectionUpsertEvent):
                    self._apply_upsert(connection, event)
                else:
                    connection.execute("DELETE FROM graph_elements WHERE element_id = ?", (event.element_id,))
                connection.execute(
                    """
                    INSERT OR IGNORE INTO recent_events (
                        event_id, operation, element_id, schema_version,
                        observed_at_unix_nano, emitted_at_unix_ms, topic, partition_id, offset_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.operation,
                        event.element_id,
                        event.schema_version,
                        event.observed_at_unix_nano,
                        event.emitted_at_unix_ms,
                        topic,
                        partition,
                        offset,
                    ),
                )
                next_offset = offset + 1
                applied += 1
            if next_offset is not None:
                connection.execute(
                    """
                    INSERT INTO consumer_offsets (topic, partition_id, next_offset)
                    VALUES (?, ?, ?)
                    ON CONFLICT(topic, partition_id) DO UPDATE SET next_offset = excluded.next_offset
                    """,
                    (topic, partition, next_offset),
                )
            connection.execute(
                """
                DELETE FROM recent_events
                WHERE sequence <= (SELECT COALESCE(MAX(sequence) - ?, 0) FROM recent_events)
                """,
                (self._recent_event_limit,),
            )
            connection.commit()
        return applied

    def graph(self, query: str | None, entity_type: str | None, edge_type: str | None) -> GraphView:
        elements = self.elements(None, None, None, 10_000, 0)
        nodes = tuple(GraphNodeView(**element.model_dump()) for element in elements if isinstance(element, GraphNode))
        node_ids = {node.id for node in nodes}
        edges = tuple(
            _edge_view(element)
            for element in elements
            if isinstance(element, GraphEdge)
            and element.source_id in node_ids
            and element.target_id in node_ids
        )
        if query:
            normalized = query.casefold()
            matching_ids = {
                node.id
                for node in nodes
                if normalized in node.id.casefold()
                or normalized in node.type.casefold()
                or normalized in _json(node.attributes).casefold()
            }
            edges = tuple(edge for edge in edges if edge.source in matching_ids or edge.target in matching_ids)
            connected = {endpoint for edge in edges for endpoint in (edge.source, edge.target)}
            nodes = tuple(node for node in nodes if node.id in matching_ids | connected)
        if entity_type:
            allowed = {node.id for node in nodes if node.type == entity_type}
            edges = tuple(edge for edge in edges if edge.source in allowed or edge.target in allowed)
            connected = {endpoint for edge in edges for endpoint in (edge.source, edge.target)}
            nodes = tuple(node for node in nodes if node.id in allowed | connected)
        if edge_type:
            edges = tuple(edge for edge in edges if edge.type == edge_type)
            connected = {endpoint for edge in edges for endpoint in (edge.source, edge.target)}
            nodes = tuple(node for node in nodes if node.id in connected)
        total_nodes = len(nodes)
        total_edges = len(edges)
        nodes = nodes[:2_000]
        visible = {node.id for node in nodes}
        edges = tuple(edge for edge in edges if edge.source in visible and edge.target in visible)[:5_000]
        return GraphView(
            nodes=nodes,
            edges=edges,
            total_nodes=total_nodes,
            total_edges=total_edges,
            truncated=len(nodes) < total_nodes or len(edges) < total_edges,
        )

    def elements(
        self,
        query: str | None,
        kind: str | None,
        element_type: str | None,
        limit: int,
        offset: int,
    ) -> tuple[ElementView, ...]:
        clauses: list[str] = []
        parameters: list[object] = []
        if kind:
            clauses.append("element_kind = ?")
            parameters.append(kind)
        if element_type:
            clauses.append("element_type = ?")
            parameters.append(element_type)
        if query:
            clauses.append("(element_id LIKE ? OR attributes_json LIKE ?)")
            pattern = f"%{query}%"
            parameters.extend((pattern, pattern))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.extend((limit, offset))
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM graph_elements {where} ORDER BY element_kind DESC, element_id LIMIT ? OFFSET ?",
                parameters,
            ).fetchall()
        return tuple(_element(row) for row in rows)

    def events(self, limit: int) -> tuple[EventView, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM recent_events ORDER BY sequence DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(
            EventView(
                event_id=str(row["event_id"]),
                operation=str(row["operation"]),  # type: ignore[arg-type]
                element_id=str(row["element_id"]),
                schema_version=str(row["schema_version"]),  # type: ignore[arg-type]
                observed_at_unix_nano=int(row["observed_at_unix_nano"]),
                emitted_at_unix_ms=int(row["emitted_at_unix_ms"]),
                partition=int(row["partition_id"]),
                offset=int(row["offset_id"]),
            )
            for row in rows
        )

    def counts(self) -> tuple[int, int, int]:
        with self._connect() as connection:
            total = int(connection.execute("SELECT COUNT(*) FROM graph_elements").fetchone()[0])
            nodes = int(
                connection.execute("SELECT COUNT(*) FROM graph_elements WHERE element_kind = 'node'").fetchone()[0]
            )
            edges = total - nodes
        return total, nodes, edges

    def _apply_upsert(self, connection: sqlite3.Connection, event: ProjectionUpsertEvent) -> None:
        element = event.element
        source_id = element.source_id if isinstance(element, GraphEdge) else None
        target_id = element.target_id if isinstance(element, GraphEdge) else None
        metrics = element.metrics if isinstance(element, GraphEdge) else {}
        connection.execute(
            """
            INSERT INTO graph_elements (
                element_id, element_kind, element_type, source_id, target_id,
                attributes_json, metrics_json, observed_at_unix_nano,
                emitted_at_unix_ms, payload_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(element_id) DO UPDATE SET
                element_kind = excluded.element_kind,
                element_type = excluded.element_type,
                source_id = excluded.source_id,
                target_id = excluded.target_id,
                attributes_json = excluded.attributes_json,
                metrics_json = excluded.metrics_json,
                observed_at_unix_nano = excluded.observed_at_unix_nano,
                emitted_at_unix_ms = excluded.emitted_at_unix_ms,
                payload_hash = excluded.payload_hash
            """,
            (
                event.element_id,
                element.kind,
                element.type,
                source_id,
                target_id,
                _json(element.attributes),
                _json(metrics),
                event.observed_at_unix_nano,
                event.emitted_at_unix_ms,
                event.payload_hash,
            ),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        return connection


def _element(row: sqlite3.Row) -> ElementView:
    attributes = json.loads(str(row["attributes_json"]))
    if row["element_kind"] == "node":
        return GraphNode(id=str(row["element_id"]), type=str(row["element_type"]), attributes=attributes)
    return GraphEdge(
        id=str(row["element_id"]),
        type=str(row["element_type"]),
        source_id=str(row["source_id"]),
        target_id=str(row["target_id"]),
        attributes=attributes,
        metrics=json.loads(str(row["metrics_json"])),
    )


def _edge_view(edge: GraphEdge) -> GraphEdgeView:
    return GraphEdgeView(
        id=edge.id,
        type=edge.type,
        source=edge.source_id,
        target=edge.target_id,
        attributes=edge.attributes,
        metrics=edge.metrics,
    )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
