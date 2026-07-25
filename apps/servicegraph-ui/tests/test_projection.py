from __future__ import annotations

import json
from pathlib import Path

from servicegraph_ui.models import PROJECTION_EVENT_ADAPTER, ProjectionDeleteEvent, ProjectionUpsertEvent
from servicegraph_ui.repository import ProjectionRepository

from extended_otel_semconv.graph.interaction import (
    InteractionEntityRef,
    InteractionPayload,
)


def test_projection_changes_only_for_flink_upsert_and_delete(tmp_path: Path) -> None:
    repository = ProjectionRepository(tmp_path / "projection.db", recent_event_limit=10)
    repository.initialize()
    upsert = _upsert("interaction-a", "checkout-api", "inventory-api", emitted_at=100)

    assert repository.apply_event("events", 0, 0, upsert)
    assert repository.counts() == (1, 2, 1)
    assert not repository.apply_event("events", 0, 0, upsert)
    assert repository.counts() == (1, 2, 1)

    # There is deliberately no repository clock or expiry operation.
    assert repository.interaction("interaction-a") is not None

    delete = ProjectionDeleteEvent(
        schema_version="1.1",
        event_id="delete-a",
        event_type="interaction_state_changed",
        interaction_id="interaction-a",
        observed_at_unix_nano=2,
        emitted_at_unix_ms=200,
        operation="delete",
    )
    assert repository.apply_event("events", 0, 1, delete)
    assert repository.counts() == (0, 0, 0)
    assert [event.operation for event in repository.events(10)] == ["delete", "upsert"]


def test_shared_service_node_remains_until_every_contributing_interaction_is_deleted(tmp_path: Path) -> None:
    repository = ProjectionRepository(tmp_path / "projection.db", recent_event_limit=10)
    repository.initialize()
    repository.apply_event("events", 0, 0, _upsert("a", "frontend", "checkout", emitted_at=100))
    repository.apply_event("events", 0, 1, _upsert("b", "frontend", "payments", emitted_at=101))

    assert repository.counts() == (2, 3, 2)
    repository.apply_event("events", 0, 2, _delete("a", emitted_at=200))

    graph = repository.graph(None, None, None)
    assert {node.id for node in graph.nodes} == {"service:frontend", "service:payments"}


def test_schema_1_0_event_replays_as_service_graph(tmp_path: Path) -> None:
    repository = ProjectionRepository(tmp_path / "projection.db", recent_event_limit=10)
    repository.initialize()
    legacy = PROJECTION_EVENT_ADAPTER.validate_json(
        json.dumps(
            {
                "schema_version": "1.0",
                "event_id": "legacy-upsert",
                "event_type": "interaction_state_changed",
                "interaction_id": "legacy",
                "observed_at_unix_nano": 1,
                "emitted_at_unix_ms": 100,
                "operation": "upsert",
                "payload_hash": "hash",
                "interaction": {
                    "client": "frontend",
                    "server": "checkout",
                    "connection_type": "calls",
                    "entities": [{"id": "service:frontend", "type": "service"}],
                },
            }
        )
    )

    repository.apply_event("events", 0, 0, legacy)

    graph = repository.graph(None, None, None)
    assert {node.id for node in graph.nodes} == {"service:frontend", "service:checkout"}
    assert [(edge.source, edge.target, edge.type) for edge in graph.edges] == [
        ("service:frontend", "service:checkout", "calls")
    ]


def _upsert(
    interaction_id: str,
    client: str,
    server: str,
    *,
    emitted_at: int,
) -> ProjectionUpsertEvent:
    return ProjectionUpsertEvent(
        schema_version="1.1",
        event_id=f"upsert-{interaction_id}",
        event_type="interaction_state_changed",
        interaction_id=interaction_id,
        observed_at_unix_nano=1,
        emitted_at_unix_ms=emitted_at,
        operation="upsert",
        payload_hash=f"hash-{interaction_id}",
        interaction=InteractionPayload(
            client=client,
            server=server,
            connection_type="calls",
            entities=(
                InteractionEntityRef(id=f"service:{client}", type="service"),
                InteractionEntityRef(id=f"service:{server}", type="service"),
            ),
        ),
    )


def _delete(interaction_id: str, *, emitted_at: int) -> ProjectionDeleteEvent:
    return ProjectionDeleteEvent(
        schema_version="1.1",
        event_id=f"delete-{interaction_id}",
        event_type="interaction_state_changed",
        interaction_id=interaction_id,
        observed_at_unix_nano=2,
        emitted_at_unix_ms=emitted_at,
        operation="delete",
    )
