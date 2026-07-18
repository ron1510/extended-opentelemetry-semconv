"""SQLAlchemy schema for registry-backed graph persistence."""
from __future__ import annotations

import re
from types import MappingProxyType
from typing import Any, NamedTuple

from sqlalchemy import BigInteger, Column, MetaData, Table, Text, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.schema import CreateTable

from extended_otel_semconv.registry.model import EntityDefinition, RegistryDocument


class GraphSchema(NamedTuple):
    metadata: MetaData
    entity_tables: MappingProxyType[str, Table]
    edges: Table
    observations_seen: Table
    observation_errors: Table


def build_graph_schema(registry: RegistryDocument) -> GraphSchema:
    metadata = MetaData()
    entity_tables = {
        entity.name: _entity_table(metadata, entity)
        for entity in sorted(registry.entities_by_name.values(), key=lambda entity: entity.name)
        if _has_identifying_ref(entity)
    }
    return GraphSchema(
        metadata=metadata,
        entity_tables=MappingProxyType(entity_tables),
        edges=_edges_table(metadata),
        observations_seen=_observations_seen_table(metadata),
        observation_errors=_observation_errors_table(metadata),
    )


def render_graph_schema(registry: RegistryDocument) -> str:
    schema = build_graph_schema(registry)
    tables = (
        *schema.entity_tables.values(),
        schema.edges,
        schema.observations_seen,
        schema.observation_errors,
    )
    return "\n\n".join(_compile_create_table(table) for table in tables).rstrip() + "\n"


def entity_table_name(entity_type: str) -> str:
    return f"{sql_identifier(entity_type)}_entities"


def entity_type_from_table_name(table_name: str) -> str | None:
    if not table_name.endswith("_entities"):
        return None
    return table_name.removesuffix("_entities").replace("_", ".")


def attribute_column_name(attribute_id: str) -> str:
    return sql_identifier(attribute_id)


def sql_identifier(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", value).strip("_").lower()


def _entity_table(metadata: MetaData, entity: EntityDefinition) -> Table:
    return Table(
        entity_table_name(entity.name),
        metadata,
        *_base_observed_columns(),
        *tuple(_typed_identifying_columns(entity)),
    )


def _base_observed_columns() -> tuple[Column[Any], ...]:
    return (
        Column("entity_id", Text, primary_key=True),
        Column("first_seen", TIMESTAMP(timezone=True), nullable=False),
        Column("last_seen", TIMESTAMP(timezone=True), nullable=False),
        Column("observations", BigInteger, nullable=False, server_default=text("1")),
        Column("sources", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("attributes", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )


def _typed_identifying_columns(entity: EntityDefinition) -> tuple[Column[Any], ...]:
    seen: set[str] = set()
    columns: list[Column[Any]] = []
    for ref in entity.attributes:
        if getattr(ref, "role", None) != "identifying":
            continue
        column_name = attribute_column_name(ref.ref)
        if column_name in seen:
            continue
        seen.add(column_name)
        columns.append(Column(column_name, Text))
    return tuple(columns)


def _edges_table(metadata: MetaData) -> Table:
    return Table(
        "graph_edges",
        metadata,
        Column("edge_id", Text, primary_key=True),
        Column("source_entity_id", Text, nullable=False),
        Column("target_entity_id", Text, nullable=False),
        Column("edge_type", Text, nullable=False),
        Column("first_seen", TIMESTAMP(timezone=True), nullable=False),
        Column("last_seen", TIMESTAMP(timezone=True), nullable=False),
        Column("observations", BigInteger, nullable=False, server_default=text("1")),
        Column("sources", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("attributes", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )


def _observations_seen_table(metadata: MetaData) -> Table:
    return Table(
        "graph_observations_seen",
        metadata,
        Column("observation_id", Text, primary_key=True),
        Column("observed_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
    )


def _observation_errors_table(metadata: MetaData) -> Table:
    return Table(
        "graph_observation_errors",
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("observed_at", TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")),
        Column("reason", Text, nullable=False),
        Column("payload", JSONB, nullable=False),
    )


def _has_identifying_ref(entity: EntityDefinition) -> bool:
    return any(getattr(ref, "role", None) == "identifying" for ref in entity.attributes)


def _compile_create_table(table: Table) -> str:
    compiled = CreateTable(table, if_not_exists=True).compile(dialect=postgresql.dialect())
    return f"{str(compiled).rstrip()};"
