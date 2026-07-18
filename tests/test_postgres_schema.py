from __future__ import annotations

from pathlib import Path

from sqlalchemy.dialects import postgresql

from extended_otel_semconv.graph.observation import EntityObservation, ObservedEntity
from extended_otel_semconv.graph.postgres_loader import (
    observation_error_insert_statement,
    observation_row_values,
    observation_seen_insert_statement,
    observation_target_table,
    observation_upsert_statement,
)
from extended_otel_semconv.graph.postgres_schema import build_graph_schema, entity_table_name, render_graph_schema
from extended_otel_semconv.registry.validation import load_model_registry

ROOT = Path(__file__).resolve().parents[1]


def test_entity_table_names_are_generated_from_entity_types() -> None:
    assert entity_table_name("k8s.deployment") == "k8s_deployment_entities"
    assert entity_table_name("service.instance") == "service_instance_entities"


def test_graph_schema_contains_per_entity_tables() -> None:
    registry = _merged_registry()
    schema = render_graph_schema(registry)

    assert "CREATE TABLE IF NOT EXISTS service_entities" in schema
    assert "CREATE TABLE IF NOT EXISTS k8s_pod_entities" in schema
    assert "CREATE TABLE IF NOT EXISTS graph_edges" in schema


def test_graph_schema_exposes_sqlalchemy_tables_by_entity_type() -> None:
    schema = build_graph_schema(_merged_registry())

    assert schema.entity_tables["service"].name == "service_entities"
    assert "service_name" in schema.entity_tables["service"].c
    assert schema.edges.name == "graph_edges"


def test_entity_observation_maps_to_sqlalchemy_table_and_row_values() -> None:
    schema = build_graph_schema(_merged_registry())
    observation = EntityObservation(
        observation_id="obs-1",
        observed_at_unix_nano=1_784_215_260_000_000_000,
        source_signal="service_graph",
        entity=ObservedEntity(
            id="service:checkout",
            type="service",
            attributes={"service.name": "checkout", "service.namespace": "payments"},
        ),
    )
    table = observation_target_table(schema, observation)
    row = observation_row_values(table, observation)

    assert table.name == "service_entities"
    assert row["entity_id"] == "service:checkout"
    assert row["service_name"] == "checkout"
    assert row["sources"] == {"service_graph": 1}


def test_entity_observation_upsert_is_built_by_sqlalchemy() -> None:
    schema = build_graph_schema(_merged_registry())
    observation = EntityObservation(
        observation_id="obs-1",
        observed_at_unix_nano=1_784_215_260_000_000_000,
        source_signal="service_graph",
        entity=ObservedEntity(
            id="service:checkout",
            type="service",
            attributes={"service.name": "checkout"},
        ),
    )

    compiled = str(observation_upsert_statement(schema, observation).compile(dialect=postgresql.dialect()))

    assert "INSERT INTO service_entities" in compiled
    assert "ON CONFLICT (entity_id) DO UPDATE" in compiled
    assert "jsonb_build_object" in compiled
    assert "graph_edges" not in compiled


def test_observation_seen_insert_is_idempotent() -> None:
    schema = build_graph_schema(_merged_registry())
    observation = EntityObservation(
        observation_id="obs-1",
        observed_at_unix_nano=1_784_215_260_000_000_000,
        source_signal="service_graph",
        entity=ObservedEntity(
            id="service:checkout",
            type="service",
            attributes={"service.name": "checkout"},
        ),
    )

    compiled = str(observation_seen_insert_statement(schema, observation).compile(dialect=postgresql.dialect()))

    assert "INSERT INTO graph_observations_seen" in compiled
    assert "ON CONFLICT (observation_id) DO NOTHING" in compiled


def test_observation_error_insert_targets_error_table() -> None:
    schema = build_graph_schema(_merged_registry())

    compiled = str(
        observation_error_insert_statement(
            schema,
            reason="ValueError",
            payload={"payload": "not-json"},
        ).compile(dialect=postgresql.dialect())
    )

    assert "INSERT INTO graph_observation_errors" in compiled


def _merged_registry():
    upstream = load_model_registry(ROOT / "upstream" / "otel-semconv" / "v1.43.0" / "model")
    extension = load_model_registry(ROOT / "model" / "extensions")
    return upstream.model_copy(update={"groups": (*upstream.groups, *extension.groups)})
