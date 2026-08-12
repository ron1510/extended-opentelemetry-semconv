"""Typed interaction state and deterministic diffing for servicegraph metrics."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from otel_servicegraph_diff.engine.elements import (
    GRAPH_REQUEST_FAILED_TOTAL,
    GRAPH_REQUEST_TOTAL,
    GraphContribution,
    GraphContributionRetract,
    GraphContributionUpsert,
    GraphEdge,
    GraphElement,
    GraphNode,
    edge_id,
)
from otel_servicegraph_diff.engine.metrics import MetricTemporality
from otel_servicegraph_diff.engine.observation import ObservedEdge, ObservedEntity

SCHEMA_VERSION = "2.0"
DEFAULT_INTERACTION_TTL_SECONDS = 300
DEFAULT_ALLOWED_LATENESS_SECONDS = 60

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
UnixNano = Annotated[int, Field(gt=0)]
type MetricValue = int | float
type TelemetryScalar = str | bool | int | float
type JsonValue = None | str | bool | int | float | list[JsonValue] | dict[str, JsonValue]
type DimensionMap = dict[str, TelemetryScalar]


class FrozenModel(BaseModel):
    """Base contract for immutable internal and wire models."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class InteractionEntityRef(FrozenModel):
    id: NonEmptyString
    type: NonEmptyString


class InteractionGraph(FrozenModel):
    nodes: tuple[ObservedEntity, ...] = ()
    edges: tuple[ObservedEdge, ...] = ()


class InteractionEndpoint(FrozenModel):
    service: NonEmptyString
    entities: tuple[InteractionEntityRef, ...] = ()


class InteractionMetric(FrozenModel):
    value: MetricValue
    temporality: MetricTemporality
    start_time_unix_nano: UnixNano | None = None


class InteractionObservation(FrozenModel):
    interaction_id: NonEmptyString
    metric_name: NonEmptyString
    metric: InteractionMetric
    observed_at_unix_nano: UnixNano
    client: InteractionEndpoint
    server: InteractionEndpoint
    connection_type: NonEmptyString
    dimensions: DimensionMap = Field(default_factory=dict)
    graph: InteractionGraph = Field(default_factory=InteractionGraph)

    @property
    def metric_value(self) -> MetricValue:
        return self.metric.value


class InteractionState(FrozenModel):
    interaction_id: NonEmptyString
    client: NonEmptyString
    server: NonEmptyString
    connection_type: NonEmptyString
    dimensions: DimensionMap = Field(default_factory=dict)
    entities: tuple[InteractionEntityRef, ...] = ()
    graph: InteractionGraph = Field(default_factory=InteractionGraph)
    metrics_by_name: dict[str, InteractionMetric] = Field(default_factory=dict)
    first_seen_unix_nano: UnixNano
    last_seen_unix_nano: UnixNano
    expires_at_unix_nano: UnixNano
    active: bool = True


class InteractionDiffResult(FrozenModel):
    state: InteractionState
    changed: bool = False


class InteractionDlqEvent(FrozenModel):
    schema_version: Literal["2.0"] = SCHEMA_VERSION
    event_type: Literal["interaction_record_rejected"] = "interaction_record_rejected"
    reason: NonEmptyString
    payload: str
    detail: str | None = None


def apply_observation(
    previous: InteractionState | None,
    observation: InteractionObservation,
    *,
    ttl_seconds: int = DEFAULT_INTERACTION_TTL_SECONDS,
    expiry_base_unix_nano: int | None = None,
) -> InteractionDiffResult:
    if previous is not None and observation.observed_at_unix_nano < previous.last_seen_unix_nano:
        return InteractionDiffResult(state=previous)

    previous_metric = previous.metrics_by_name.get(observation.metric_name) if previous is not None else None
    if previous is not None and not metric_has_advanced(previous_metric, observation.metric):
        return InteractionDiffResult(state=previous)

    metrics = dict(previous.metrics_by_name) if previous is not None else {}
    metrics[observation.metric_name] = observation.metric
    first_seen = previous.first_seen_unix_nano if previous is not None else observation.observed_at_unix_nano
    expiry_base = max(observation.observed_at_unix_nano, expiry_base_unix_nano or 0)
    state = _state_from_observation(observation, metrics, first_seen, expiry_base, ttl_seconds)
    return InteractionDiffResult(state=state, changed=True)


def metric_has_advanced(previous: InteractionMetric | None, current: InteractionMetric) -> bool:
    if previous is None:
        return True
    if current.temporality == "delta":
        return current.value != 0
    if current.start_time_unix_nano != previous.start_time_unix_nano:
        return True
    return current.value != previous.value


def state_has_expired(state: InteractionState, timer_unix_nano: int) -> bool:
    return state.active and timer_unix_nano >= state.expires_at_unix_nano


def contributions_for_transition(
    previous: InteractionState | None,
    current: InteractionState,
    observation: InteractionObservation,
) -> tuple[GraphContribution, ...]:
    previous_elements = _graph_elements(previous.graph) if previous is not None and previous.active else {}
    current_elements = _graph_elements(current.graph)
    contributions: list[GraphContribution] = [
        GraphContributionRetract(
            element_id=element_id,
            contributor_id=current.interaction_id,
            observed_at_unix_nano=observation.observed_at_unix_nano,
        )
        for element_id in sorted(previous_elements.keys() - current_elements.keys())
    ]
    for element_id in sorted(current_elements):
        element, metric_deltas = current_elements[element_id]
        contributions.append(
            GraphContributionUpsert(
                element_id=element_id,
                contributor_id=current.interaction_id,
                observed_at_unix_nano=observation.observed_at_unix_nano,
                element=element,
                metric_deltas=metric_deltas,
            )
        )
    return tuple(contributions)


def retract_contributions(state: InteractionState) -> tuple[GraphContributionRetract, ...]:
    return tuple(
        GraphContributionRetract(
            element_id=element_id,
            contributor_id=state.interaction_id,
            observed_at_unix_nano=state.expires_at_unix_nano,
        )
        for element_id in sorted(_graph_elements(state.graph))
    )


def build_interaction_id(
    client: str,
    server: str,
    connection_type: str,
    dimensions: Mapping[str, TelemetryScalar],
) -> str:
    return digest(
        {
            "client": client,
            "server": server,
            "connection_type": connection_type,
            "dimensions": canonicalize(dict(dimensions)),
        }
    )


def digest(value: JsonValue) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def canonicalize(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


def _state_from_observation(
    observation: InteractionObservation,
    metrics_by_name: dict[str, InteractionMetric],
    first_seen_unix_nano: int,
    expiry_base_unix_nano: int,
    ttl_seconds: int,
) -> InteractionState:
    entities_by_key = {
        (entity.type, entity.id): entity
        for entity in (*observation.client.entities, *observation.server.entities)
    }
    entities = tuple(entities_by_key[key] for key in sorted(entities_by_key))
    return InteractionState(
        interaction_id=observation.interaction_id,
        client=observation.client.service,
        server=observation.server.service,
        connection_type=observation.connection_type,
        dimensions=observation.dimensions,
        entities=entities,
        graph=observation.graph,
        metrics_by_name=metrics_by_name,
        first_seen_unix_nano=first_seen_unix_nano,
        last_seen_unix_nano=observation.observed_at_unix_nano,
        expires_at_unix_nano=expiry_base_unix_nano + ttl_seconds * 1_000_000_000,
        active=True,
    )


def _graph_elements(graph: InteractionGraph) -> dict[str, tuple[GraphElement, dict[str, MetricValue]]]:
    elements: dict[str, tuple[GraphElement, dict[str, MetricValue]]] = {
        node.id: (GraphNode(id=node.id, type=node.type, attributes=node.attributes), {})
        for node in graph.nodes
    }
    metric_names = {GRAPH_REQUEST_TOTAL, GRAPH_REQUEST_FAILED_TOTAL}
    for observed in graph.edges:
        element_id = edge_id(observed.source, observed.type, observed.target)
        metric_deltas = {
            name: value
            for name, value in observed.attributes.items()
            if name in metric_names and isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        attributes = {name: value for name, value in observed.attributes.items() if name not in metric_names}
        elements[element_id] = (
            GraphEdge(
                id=element_id,
                type=observed.type,
                source_id=observed.source,
                target_id=observed.target,
                attributes=attributes,
            ),
            metric_deltas,
        )
    return elements


def _canonical_json(value: JsonValue) -> str:
    return json.dumps(canonicalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


