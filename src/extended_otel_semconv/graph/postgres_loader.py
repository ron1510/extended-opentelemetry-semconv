"""SQLAlchemy statements for idempotent graph observation persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BigInteger, Table, cast, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection
from sqlalchemy.sql.dml import Insert

from extended_otel_semconv.graph.observation import EdgeObservation, EntityObservation, GraphObservation
from extended_otel_semconv.graph.postgres_schema import GraphSchema, attribute_column_name, entity_table_name


def observation_target_table(schema: GraphSchema, observation: GraphObservation) -> Table:
    if isinstance(observation, EntityObservation):
        return schema.entity_tables[observation.entity.type]
    return schema.edges


def observation_target_table_name(observation: GraphObservation) -> str:
    if isinstance(observation, EntityObservation):
        return entity_table_name(observation.entity.type)
    return "graph_edges"


def observation_upsert_statement(schema: GraphSchema, observation: GraphObservation) -> Insert:
    if isinstance(observation, EntityObservation):
        table = observation_target_table(schema, observation)
        return _entity_upsert_statement(table, observation)
    return _edge_upsert_statement(schema.edges, observation)


def observation_seen_insert_statement(schema: GraphSchema, observation: GraphObservation) -> Insert:
    stmt = insert(schema.observations_seen).values({"observation_id": observation.observation_id})
    return stmt.on_conflict_do_nothing(index_elements=[schema.observations_seen.c.observation_id])


def observation_error_insert_statement(schema: GraphSchema, reason: str, payload: object) -> Insert:
    return insert(schema.observation_errors).values(
        {
            "reason": reason[:1000],
            "payload": _json_safe_payload(payload),
        }
    )


def persist_observation(connection: Connection, schema: GraphSchema, observation: GraphObservation) -> bool:
    seen_result = connection.execute(observation_seen_insert_statement(schema, observation))
    if seen_result.rowcount == 0:
        return False
    connection.execute(observation_upsert_statement(schema, observation))
    return True


def persist_observations(connection: Connection, schema: GraphSchema, observations: list[GraphObservation]) -> int:
    persisted = 0
    for observation in observations:
        if persist_observation(connection, schema, observation):
            persisted += 1
    return persisted


def record_observation_error(connection: Connection, schema: GraphSchema, reason: str, payload: object) -> None:
    connection.execute(observation_error_insert_statement(schema, reason, payload))


def observation_row_values(table: Table, observation: GraphObservation) -> dict[str, object]:
    if isinstance(observation, EntityObservation):
        return _entity_row_values(table, observation)
    return _edge_row_values(observation)


def _entity_upsert_statement(table: Table, observation: EntityObservation) -> Insert:
    stmt = insert(table).values(_entity_row_values(table, observation))
    return stmt.on_conflict_do_update(
        index_elements=[table.c.entity_id],
        set_={
            "last_seen": func.greatest(table.c.last_seen, stmt.excluded.last_seen),
            "observations": table.c.observations + 1,
            "sources": _increment_source_count(table, observation.source_signal),
            "attributes": table.c.attributes.op("||")(stmt.excluded.attributes),
        },
    )


def _edge_upsert_statement(table: Table, observation: EdgeObservation) -> Insert:
    stmt = insert(table).values(_edge_row_values(observation))
    return stmt.on_conflict_do_update(
        index_elements=[table.c.edge_id],
        set_={
            "last_seen": func.greatest(table.c.last_seen, stmt.excluded.last_seen),
            "observations": table.c.observations + 1,
            "sources": _increment_source_count(table, observation.source_signal),
            "attributes": table.c.attributes.op("||")(stmt.excluded.attributes),
        },
    )


def _entity_row_values(table: Table, observation: EntityObservation) -> dict[str, object]:
    values: dict[str, object] = {
        "entity_id": observation.entity.id,
        "first_seen": _observed_at(observation.observed_at_unix_nano),
        "last_seen": _observed_at(observation.observed_at_unix_nano),
        "observations": 1,
        "sources": {observation.source_signal: 1},
        "attributes": observation.entity.attributes,
    }
    for attribute_id, value in observation.entity.attributes.items():
        column_name = attribute_column_name(attribute_id)
        if column_name in table.c:
            values[column_name] = _typed_column_value(value)
    return values


def _edge_row_values(observation: EdgeObservation) -> dict[str, object]:
    edge_id = f"{observation.edge.source}|{observation.edge.type}|{observation.edge.target}"
    return {
        "edge_id": edge_id,
        "source_entity_id": observation.edge.source,
        "target_entity_id": observation.edge.target,
        "edge_type": observation.edge.type,
        "first_seen": _observed_at(observation.observed_at_unix_nano),
        "last_seen": _observed_at(observation.observed_at_unix_nano),
        "observations": 1,
        "sources": {observation.source_signal: 1},
        "attributes": observation.edge.attributes,
    }


def _increment_source_count(table: Table, source_signal: str):
    current_count = cast(table.c.sources[source_signal].astext, BigInteger)
    next_count = func.coalesce(current_count, 0) + 1
    return table.c.sources.op("||")(func.jsonb_build_object(source_signal, next_count))


def _observed_at(unix_nano: int | None) -> datetime:
    if unix_nano is None:
        return datetime.now(UTC)
    return datetime.fromtimestamp(unix_nano / 1_000_000_000, tz=UTC)


def _typed_column_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)


def _json_safe_payload(payload: object) -> object:
    if isinstance(payload, dict | list | str | int | float | bool) or payload is None:
        return payload
    return {"repr": repr(payload)}
