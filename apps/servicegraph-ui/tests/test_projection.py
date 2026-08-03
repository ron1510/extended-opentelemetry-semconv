from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from fastapi import FastAPI
from fastapi.routing import APIRoute
from servicegraph_ui.api import create_app
from servicegraph_ui.config import VisualizationConfig
from servicegraph_ui.models import ElementView, GraphView, StatusView
from servicegraph_ui.repository import ProjectionRepository

from extended_otel_semconv.graph.elements import (
    GraphEdge,
    GraphElementDeleteEvent,
    GraphElementUpsertEvent,
    GraphNode,
    payload_hash,
)


def test_projection_applies_complete_upserts_deletes_and_offsets(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    first = _upsert(GraphNode(id="service:a", type="service", attributes={"version": "1"}), "event-1")

    assert repository.apply_event("events", 0, 0, first)
    assert repository.counts() == (1, 1, 0)
    assert not repository.apply_event("events", 0, 0, first)

    replacement = _upsert(
        GraphNode(id="service:a", type="service", attributes={"zone": "eu-1"}),
        "event-2",
    )
    assert repository.apply_event("events", 0, 1, replacement)
    element = repository.elements(None, "node", None, 10, 0)[0]
    assert element.attributes == {"zone": "eu-1"}

    assert repository.apply_event("events", 0, 2, _delete("service:a", "event-3"))
    assert repository.counts() == (0, 0, 0)
    assert repository.next_offset("events", 0) == 3
    assert [event.operation for event in repository.events(10)] == ["delete", "upsert", "upsert"]


def test_orphan_edge_is_stored_but_hidden_until_both_nodes_exist(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    edge = GraphEdge(
        id="edge:ab",
        type="calls",
        source_id="service:a",
        target_id="service:b",
        metrics={"traces_service_graph_request_total": 4},
    )
    repository.apply_event("events", 0, 0, _upsert(edge, "edge-upsert"))

    assert repository.counts() == (1, 0, 1)
    assert len(repository.elements(None, "edge", None, 10, 0)) == 1
    assert repository.graph(None, None, None).edges == ()

    repository.apply_event("events", 0, 1, _upsert(GraphNode(id="service:a", type="service"), "node-a"))
    assert repository.graph(None, None, None).edges == ()
    repository.apply_event("events", 0, 2, _upsert(GraphNode(id="service:b", type="service"), "node-b"))

    graph = repository.graph(None, None, None)
    assert [(item.source, item.target, item.type) for item in graph.edges] == [
        ("service:a", "service:b", "calls")
    ]
    assert graph.edges[0].metrics == {"traces_service_graph_request_total": 4}


def test_element_filters_and_graph_filters_are_projection_only(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.apply_event(
        "events",
        0,
        0,
        _upsert(GraphNode(id="service:frontend", type="service", attributes={"zone": "eu"}), "a"),
    )
    repository.apply_event(
        "events",
        0,
        1,
        _upsert(GraphNode(id="k8s.pod:checkout", type="k8s.pod", attributes={"name": "checkout"}), "b"),
    )
    edge = GraphEdge(
        id="edge:owns",
        type="runs_on",
        source_id="service:frontend",
        target_id="k8s.pod:checkout",
    )
    repository.apply_event("events", 0, 2, _upsert(edge, "c"))

    assert [item.id for item in repository.elements("checkout", None, None, 10, 0)] == [
        "k8s.pod:checkout"
    ]
    assert [item.id for item in repository.elements(None, "node", "service", 10, 0)] == [
        "service:frontend"
    ]
    assert repository.graph(None, None, "runs_on").total_edges == 1
    assert repository.graph(None, "service", None).total_nodes == 2


def test_http_api_exposes_elements_and_removes_interaction_contract(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.apply_event(
        "events",
        0,
        0,
        _upsert(GraphNode(id="service:frontend", type="service"), "node-event"),
    )
    config = VisualizationConfig.model_construct(
        database_path=tmp_path / "projection.db",
        static_dir=tmp_path / "missing-static",
        recent_event_limit=10,
    )
    app = create_app(config, repository, start_consumer=False)

    status = cast(StatusView, _endpoint(app, "/api/v1/status")())
    elements = cast(
        tuple[ElementView, ...],
        _endpoint(app, "/api/v1/elements")(
            q=None,
            kind="node",
            element_type="service",
            limit=100,
            offset=0,
        ),
    )
    graph = cast(
        GraphView,
        _endpoint(app, "/api/v1/graph")(q=None, entity_type=None, edge_type=None),
    )

    assert status.elements == 1
    assert [item.id for item in elements] == ["service:frontend"]
    assert graph.total_nodes == 1
    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    assert "/api/v1/interactions" not in paths
    assert "/api/v1/entities" not in paths


def _repository(tmp_path: Path) -> ProjectionRepository:
    repository = ProjectionRepository(tmp_path / "projection.db", recent_event_limit=10)
    repository.initialize()
    return repository


def _endpoint(app: FastAPI, path: str) -> Callable[..., object]:
    route = next(route for route in app.routes if isinstance(route, APIRoute) and route.path == path)
    return cast(Callable[..., object], route.endpoint)


def _upsert(element: GraphNode | GraphEdge, event_id: str) -> GraphElementUpsertEvent:
    return GraphElementUpsertEvent(
        event_id=event_id,
        element_id=element.id,
        observed_at_unix_nano=1,
        emitted_at_unix_ms=100,
        payload_hash=payload_hash(element),
        element=element,
    )


def _delete(element_id: str, event_id: str) -> GraphElementDeleteEvent:
    return GraphElementDeleteEvent(
        event_id=event_id,
        element_id=element_id,
        observed_at_unix_nano=2,
        emitted_at_unix_ms=200,
    )
