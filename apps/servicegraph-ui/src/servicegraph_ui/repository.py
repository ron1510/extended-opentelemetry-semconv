"""SQLite command projection driven exclusively by Flink events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from extended_otel_semconv.entities import quoted_entity_id
from extended_otel_semconv.graph.interaction import InteractionEntityRef, InteractionGraph
from extended_otel_semconv.graph.observation import ObservedEdge, ObservedEntity
from servicegraph_ui.models import (
    EntityView,
    EventView,
    GraphEdgeView,
    GraphNodeView,
    GraphView,
    InteractionView,
    ProjectionEvent,
    ProjectionUpsertEvent,
)

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS interactions (
    interaction_id TEXT PRIMARY KEY,
    client TEXT NOT NULL,
    server TEXT NOT NULL,
    connection_type TEXT NOT NULL,
    dimensions_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    entities_json TEXT NOT NULL,
    observed_at_unix_nano INTEGER NOT NULL,
    emitted_at_unix_ms INTEGER NOT NULL,
    payload_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interaction_nodes (
    interaction_id TEXT NOT NULL REFERENCES interactions(interaction_id) ON DELETE CASCADE,
    node_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    PRIMARY KEY (interaction_id, node_id)
);
CREATE TABLE IF NOT EXISTS interaction_edges (
    interaction_id TEXT NOT NULL REFERENCES interactions(interaction_id) ON DELETE CASCADE,
    edge_id TEXT NOT NULL,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    PRIMARY KEY (interaction_id, edge_id)
);
CREATE TABLE IF NOT EXISTS recent_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    operation TEXT NOT NULL,
    interaction_id TEXT NOT NULL,
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
CREATE INDEX IF NOT EXISTS ix_nodes_id ON interaction_nodes(node_id);
CREATE INDEX IF NOT EXISTS ix_edges_key ON interaction_edges(source, target, edge_type);
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
            current_offset = connection.execute(
                "SELECT next_offset FROM consumer_offsets WHERE topic = ? AND partition_id = ?",
                (topic, partition),
            ).fetchone()
            next_offset = int(current_offset["next_offset"]) if current_offset is not None else None
            for offset, event in events:
                if next_offset is not None and offset < next_offset:
                    continue

                if isinstance(event, ProjectionUpsertEvent):
                    self._apply_upsert(connection, event)
                else:
                    connection.execute(
                        "DELETE FROM interactions WHERE interaction_id = ?",
                        (event.interaction_id,),
                    )

                connection.execute(
                    """
                    INSERT OR IGNORE INTO recent_events (
                        event_id, operation, interaction_id, schema_version,
                        observed_at_unix_nano, emitted_at_unix_ms, topic, partition_id, offset_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.operation,
                        event.interaction_id,
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
                WHERE sequence <= (
                    SELECT COALESCE(MAX(sequence) - ?, 0) FROM recent_events
                )
                """,
                (self._recent_event_limit,),
            )
            connection.commit()
        return applied

    def graph(self, query: str | None, entity_type: str | None, edge_type: str | None) -> GraphView:
        node_contributions, edge_contributions = self._graph_contributions()
        nodes = _aggregate_nodes(node_contributions)
        edges = _aggregate_edges(edge_contributions)
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
            connected_ids = {endpoint for edge in edges for endpoint in (edge.source, edge.target)}
            nodes = tuple(node for node in nodes if node.id in matching_ids | connected_ids)
        if entity_type:
            allowed_ids = {node.id for node in nodes if node.type == entity_type}
            edges = tuple(edge for edge in edges if edge.source in allowed_ids or edge.target in allowed_ids)
            connected_ids = {endpoint for edge in edges for endpoint in (edge.source, edge.target)}
            nodes = tuple(node for node in nodes if node.id in allowed_ids | connected_ids)
        if edge_type:
            edges = tuple(edge for edge in edges if edge.type == edge_type)
            connected_ids = {endpoint for edge in edges for endpoint in (edge.source, edge.target)}
            nodes = tuple(node for node in nodes if node.id in connected_ids)

        total_nodes = len(nodes)
        total_edges = len(edges)
        nodes = nodes[:2_000]
        allowed = {node.id for node in nodes}
        edges = tuple(edge for edge in edges if edge.source in allowed and edge.target in allowed)[:5_000]
        return GraphView(
            nodes=nodes,
            edges=edges,
            total_nodes=total_nodes,
            total_edges=total_edges,
            truncated=len(nodes) < total_nodes or len(edges) < total_edges,
        )

    def entities(self, query: str | None, entity_type: str | None, limit: int, offset: int) -> tuple[EntityView, ...]:
        node_contributions, _ = self._graph_contributions()
        interactions_by_node: dict[str, set[str]] = defaultdict(set)
        for interaction_id, node in node_contributions:
            interactions_by_node[node.id].add(interaction_id)
        nodes = _aggregate_nodes(node_contributions)
        if query:
            normalized = query.casefold()
            nodes = tuple(
                node
                for node in nodes
                if normalized in node.id.casefold() or normalized in _json(node.attributes).casefold()
            )
        if entity_type:
            nodes = tuple(node for node in nodes if node.type == entity_type)
        return tuple(
            EntityView(
                **node.model_dump(),
                interaction_ids=tuple(sorted(interactions_by_node[node.id])),
            )
            for node in nodes[offset : offset + limit]
        )

    def interactions(self, limit: int, offset: int) -> tuple[InteractionView, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM interactions
                ORDER BY emitted_at_unix_ms DESC, interaction_id
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return tuple(_interaction_view(row) for row in rows)

    def interaction(self, interaction_id: str) -> InteractionView | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM interactions WHERE interaction_id = ?",
                (interaction_id,),
            ).fetchone()
        return _interaction_view(row) if row is not None else None

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
                interaction_id=str(row["interaction_id"]),
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
            interactions = int(connection.execute("SELECT COUNT(*) FROM interactions").fetchone()[0])
            entities = int(connection.execute("SELECT COUNT(DISTINCT node_id) FROM interaction_nodes").fetchone()[0])
            edges = int(
                connection.execute(
                    "SELECT COUNT(*) FROM (SELECT 1 FROM interaction_edges GROUP BY source, target, edge_type)"
                ).fetchone()[0]
            )
        return interactions, entities, edges

    def _apply_upsert(self, connection: sqlite3.Connection, event: ProjectionUpsertEvent) -> None:
        interaction = event.interaction
        graph = interaction.graph
        if not graph.nodes:
            graph = _legacy_graph(
                interaction.client,
                interaction.server,
                interaction.connection_type,
                interaction.entities,
            )
        connection.execute(
            """
            INSERT INTO interactions (
                interaction_id, client, server, connection_type, dimensions_json,
                metrics_json, entities_json, observed_at_unix_nano,
                emitted_at_unix_ms, payload_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(interaction_id) DO UPDATE SET
                client = excluded.client,
                server = excluded.server,
                connection_type = excluded.connection_type,
                dimensions_json = excluded.dimensions_json,
                metrics_json = excluded.metrics_json,
                entities_json = excluded.entities_json,
                observed_at_unix_nano = excluded.observed_at_unix_nano,
                emitted_at_unix_ms = excluded.emitted_at_unix_ms,
                payload_hash = excluded.payload_hash
            """,
            (
                event.interaction_id,
                interaction.client,
                interaction.server,
                interaction.connection_type,
                _json(interaction.dimensions),
                _json(interaction.metrics),
                _json([entity.model_dump(mode="json") for entity in interaction.entities]),
                event.observed_at_unix_nano,
                event.emitted_at_unix_ms,
                event.payload_hash,
            ),
        )
        connection.execute("DELETE FROM interaction_nodes WHERE interaction_id = ?", (event.interaction_id,))
        connection.execute("DELETE FROM interaction_edges WHERE interaction_id = ?", (event.interaction_id,))
        connection.executemany(
            """
            INSERT INTO interaction_nodes (interaction_id, node_id, node_type, attributes_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                (event.interaction_id, node.id, node.type, _json(node.attributes))
                for node in _deduplicate_nodes(graph.nodes)
            ),
        )
        connection.executemany(
            """
            INSERT INTO interaction_edges (
                interaction_id, edge_id, source, target, edge_type, attributes_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    event.interaction_id,
                    _edge_id(edge),
                    edge.source,
                    edge.target,
                    edge.type,
                    _json(edge.attributes),
                )
                for edge in _deduplicate_edges(graph.edges)
            ),
        )

    def _graph_contributions(
        self,
    ) -> tuple[list[tuple[str, ObservedEntity]], list[tuple[str, ObservedEdge]]]:
        with self._connect() as connection:
            node_rows = connection.execute(
                "SELECT interaction_id, node_id, node_type, attributes_json FROM interaction_nodes"
            ).fetchall()
            edge_rows = connection.execute(
                "SELECT interaction_id, source, target, edge_type, attributes_json FROM interaction_edges"
            ).fetchall()
        nodes = [
            (
                str(row["interaction_id"]),
                ObservedEntity(
                    id=str(row["node_id"]),
                    type=str(row["node_type"]),
                    attributes=json.loads(str(row["attributes_json"])),
                ),
            )
            for row in node_rows
        ]
        edges = [
            (
                str(row["interaction_id"]),
                ObservedEdge(
                    source=str(row["source"]),
                    target=str(row["target"]),
                    type=str(row["edge_type"]),
                    attributes=json.loads(str(row["attributes_json"])),
                ),
            )
            for row in edge_rows
        ]
        return nodes, edges

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection


def _legacy_graph(
    client: str,
    server: str,
    connection_type: str,
    entities: tuple[InteractionEntityRef, ...],
) -> InteractionGraph:
    nodes_by_id = {
        quoted_entity_id("service", client): ObservedEntity(id=quoted_entity_id("service", client), type="service"),
        quoted_entity_id("service", server): ObservedEntity(id=quoted_entity_id("service", server), type="service"),
    }
    for reference in entities:
        nodes_by_id[reference.id] = ObservedEntity(id=reference.id, type=reference.type)
    edge = ObservedEdge(
        source=quoted_entity_id("service", client),
        target=quoted_entity_id("service", server),
        type=connection_type,
    )
    return InteractionGraph(nodes=tuple(nodes_by_id.values()), edges=(edge,))


def _deduplicate_nodes(nodes: tuple[ObservedEntity, ...]) -> tuple[ObservedEntity, ...]:
    by_id = {node.id: node for node in nodes}
    return tuple(by_id[node_id] for node_id in sorted(by_id))


def _deduplicate_edges(edges: tuple[ObservedEdge, ...]) -> tuple[ObservedEdge, ...]:
    by_id = {_edge_id(edge): edge for edge in edges}
    return tuple(by_id[edge_id] for edge_id in sorted(by_id))


def _edge_id(edge: ObservedEdge) -> str:
    return hashlib.sha256(
        _json(
            {
                "source": edge.source,
                "target": edge.target,
                "type": edge.type,
                "attributes": edge.attributes,
            }
        ).encode("utf-8")
    ).hexdigest()


def _aggregate_nodes(contributions: list[tuple[str, ObservedEntity]]) -> tuple[GraphNodeView, ...]:
    by_id: dict[str, tuple[ObservedEntity, set[str]]] = {}
    for interaction_id, node in contributions:
        existing = by_id.get(node.id)
        if existing is None:
            by_id[node.id] = (node, {interaction_id})
        else:
            merged = {**existing[0].attributes, **node.attributes}
            by_id[node.id] = (node.model_copy(update={"attributes": merged}), existing[1] | {interaction_id})
    return tuple(
        GraphNodeView(
            id=node.id,
            type=node.type,
            attributes=node.attributes,
            interaction_count=len(interaction_ids),
        )
        for node, interaction_ids in (by_id[node_id] for node_id in sorted(by_id))
    )


def _aggregate_edges(contributions: list[tuple[str, ObservedEdge]]) -> tuple[GraphEdgeView, ...]:
    grouped: dict[tuple[str, str, str], tuple[ObservedEdge, set[str]]] = {}
    for interaction_id, edge in contributions:
        key = (edge.source, edge.target, edge.type)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = (edge, {interaction_id})
        else:
            merged = {**existing[0].attributes, **edge.attributes}
            grouped[key] = (edge.model_copy(update={"attributes": merged}), existing[1] | {interaction_id})
    return tuple(
        GraphEdgeView(
            id=hashlib.sha256("|".join(key).encode("utf-8")).hexdigest(),
            source=edge.source,
            target=edge.target,
            type=edge.type,
            attributes=edge.attributes,
            interaction_ids=tuple(sorted(interaction_ids)),
            interaction_count=len(interaction_ids),
        )
        for key, (edge, interaction_ids) in sorted(grouped.items())
    )


def _interaction_view(row: sqlite3.Row) -> InteractionView:
    return InteractionView(
        interaction_id=str(row["interaction_id"]),
        client=str(row["client"]),
        server=str(row["server"]),
        connection_type=str(row["connection_type"]),
        dimensions=json.loads(str(row["dimensions_json"])),
        metrics=json.loads(str(row["metrics_json"])),
        entities=tuple(json.loads(str(row["entities_json"]))),
        observed_at_unix_nano=int(row["observed_at_unix_nano"]),
        emitted_at_unix_ms=int(row["emitted_at_unix_ms"]),
        payload_hash=str(row["payload_hash"]),
    )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
