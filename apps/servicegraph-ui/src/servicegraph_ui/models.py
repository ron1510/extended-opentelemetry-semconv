"""Validated Kafka and HTTP models for the visualization projection."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from extended_otel_semconv.graph.interaction import InteractionPayload


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectionEventBase(FrozenModel):
    schema_version: Literal["1.0", "1.1"]
    event_id: str = Field(min_length=1)
    event_type: Literal["interaction_state_changed"]
    interaction_id: str = Field(min_length=1)
    observed_at_unix_nano: int = Field(gt=0)
    emitted_at_unix_ms: int = Field(ge=0)


class ProjectionUpsertEvent(ProjectionEventBase):
    operation: Literal["upsert"]
    payload_hash: str = Field(min_length=1)
    interaction: InteractionPayload


class ProjectionDeleteEvent(ProjectionEventBase):
    operation: Literal["delete"]
    payload_hash: None = None
    interaction: None = None


ProjectionEvent = Annotated[
    ProjectionUpsertEvent | ProjectionDeleteEvent,
    Field(discriminator="operation"),
]
PROJECTION_EVENT_ADAPTER: TypeAdapter[ProjectionEvent] = TypeAdapter(ProjectionEvent)


class GraphNodeView(FrozenModel):
    id: str
    type: str
    attributes: dict[str, object] = Field(default_factory=dict)
    interaction_count: int = Field(ge=1)


class GraphEdgeView(FrozenModel):
    id: str
    source: str
    target: str
    type: str
    attributes: dict[str, object] = Field(default_factory=dict)
    interaction_ids: tuple[str, ...]
    interaction_count: int = Field(ge=1)


class GraphView(FrozenModel):
    nodes: tuple[GraphNodeView, ...]
    edges: tuple[GraphEdgeView, ...]
    total_nodes: int = Field(ge=0)
    total_edges: int = Field(ge=0)
    truncated: bool


class EntityView(GraphNodeView):
    interaction_ids: tuple[str, ...]


class InteractionView(FrozenModel):
    interaction_id: str
    client: str
    server: str
    connection_type: str
    dimensions: dict[str, object]
    metrics: dict[str, int | float]
    entities: tuple[dict[str, str], ...]
    observed_at_unix_nano: int
    emitted_at_unix_ms: int
    payload_hash: str


class EventView(FrozenModel):
    event_id: str
    operation: Literal["upsert", "delete"]
    interaction_id: str
    schema_version: Literal["1.0", "1.1"]
    observed_at_unix_nano: int
    emitted_at_unix_ms: int
    partition: int
    offset: int


class StatusView(FrozenModel):
    consumer_running: bool
    consumer_error: str | None
    topic: str
    interactions: int = Field(ge=0)
    entities: int = Field(ge=0)
    edges: int = Field(ge=0)
    last_event_at_unix_ms: int | None
