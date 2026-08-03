"""Validated Kafka and HTTP models for the graph-element projection."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from extended_otel_semconv.graph.elements import (
    FrozenModel,
    GraphEdge,
    GraphElementDeleteEvent,
    GraphElementEvent,
    GraphElementUpsertEvent,
    GraphNode,
)

ProjectionEvent = GraphElementEvent
ProjectionUpsertEvent = GraphElementUpsertEvent
ProjectionDeleteEvent = GraphElementDeleteEvent
PROJECTION_EVENT_ADAPTER: TypeAdapter[ProjectionEvent] = TypeAdapter(ProjectionEvent)


class GraphNodeView(GraphNode):
    pass


class GraphEdgeView(FrozenModel):
    kind: Literal["edge"] = "edge"
    id: str
    type: str
    source: str
    target: str
    attributes: dict[str, object] = Field(default_factory=dict)
    metrics: dict[str, int | float] = Field(default_factory=dict)


class GraphView(FrozenModel):
    nodes: tuple[GraphNodeView, ...]
    edges: tuple[GraphEdgeView, ...]
    total_nodes: int = Field(ge=0)
    total_edges: int = Field(ge=0)
    truncated: bool


type ElementView = Annotated[GraphNode | GraphEdge, Field(discriminator="kind")]


class EventView(FrozenModel):
    event_id: str
    operation: Literal["upsert", "delete"]
    element_id: str
    schema_version: Literal["2.0"]
    observed_at_unix_nano: int
    emitted_at_unix_ms: int
    partition: int
    offset: int


class StatusView(FrozenModel):
    consumer_running: bool
    consumer_error: str | None
    topic: str
    elements: int = Field(ge=0)
    nodes: int = Field(ge=0)
    edges: int = Field(ge=0)
    last_event_at_unix_ms: int | None
