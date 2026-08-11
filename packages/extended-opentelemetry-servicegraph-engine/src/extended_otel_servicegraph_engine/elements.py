"""Authoritative graph elements and contributor-aware lifecycle aggregation."""

from __future__ import annotations

import hashlib
import json
from time import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from extended_otel_semconv.edges import MetricValue
from extended_otel_semconv.edges import edge_id as edge_id

SCHEMA_VERSION = "2.0"
GRAPH_ELEMENT_EVENT_TYPE = "graph_element_state_changed"
GRAPH_REQUEST_TOTAL = "service_graph.request.total"
GRAPH_REQUEST_FAILED_TOTAL = "service_graph.request.failed.total"

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
UnixNano = Annotated[int, Field(gt=0)]
UnixMilli = Annotated[int, Field(ge=0)]


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GraphNode(FrozenModel):
    kind: Literal["node"] = "node"
    id: NonEmptyString
    type: NonEmptyString
    attributes: dict[str, object] = Field(default_factory=dict)


class GraphEdge(FrozenModel):
    kind: Literal["edge"] = "edge"
    id: NonEmptyString
    type: NonEmptyString
    source_id: NonEmptyString
    target_id: NonEmptyString
    attributes: dict[str, object] = Field(default_factory=dict)
    metrics: dict[str, MetricValue] = Field(default_factory=dict)


type GraphElement = Annotated[GraphNode | GraphEdge, Field(discriminator="kind")]


class GraphElementEventBase(FrozenModel):
    schema_version: Literal["2.0"] = SCHEMA_VERSION
    event_id: NonEmptyString
    event_type: Literal["graph_element_state_changed"] = GRAPH_ELEMENT_EVENT_TYPE
    element_id: NonEmptyString
    observed_at_unix_nano: UnixNano
    emitted_at_unix_ms: UnixMilli


class GraphElementUpsertEvent(GraphElementEventBase):
    operation: Literal["upsert"] = "upsert"
    payload_hash: NonEmptyString
    element: GraphElement


class GraphElementDeleteEvent(GraphElementEventBase):
    operation: Literal["delete"] = "delete"
    payload_hash: None = None
    element: None = None


type GraphElementEvent = Annotated[
    GraphElementUpsertEvent | GraphElementDeleteEvent,
    Field(discriminator="operation"),
]


class GraphContributionSnapshot(FrozenModel):
    observed_at_unix_nano: UnixNano
    element: GraphElement


class GraphContributionUpsert(FrozenModel):
    operation: Literal["upsert"] = "upsert"
    element_id: NonEmptyString
    contributor_id: NonEmptyString
    observed_at_unix_nano: UnixNano
    element: GraphElement
    metric_deltas: dict[str, MetricValue] = Field(default_factory=dict)


class GraphContributionRetract(FrozenModel):
    operation: Literal["retract"] = "retract"
    element_id: NonEmptyString
    contributor_id: NonEmptyString
    observed_at_unix_nano: UnixNano


type GraphContribution = Annotated[
    GraphContributionUpsert | GraphContributionRetract,
    Field(discriminator="operation"),
]


class GraphElementAggregateState(FrozenModel):
    element_id: NonEmptyString
    contributors: dict[str, GraphContributionSnapshot]
    metrics: dict[str, MetricValue] = Field(default_factory=dict)
    last_payload_hash: NonEmptyString


class GraphElementAggregationResult(FrozenModel):
    state: GraphElementAggregateState | None
    event: GraphElementEvent | None = None


def apply_contribution(
    previous: GraphElementAggregateState | None,
    contribution: GraphContribution,
    *,
    emitted_at_unix_ms: int | None = None,
) -> GraphElementAggregationResult:
    emitted_at = emitted_at_unix_ms if emitted_at_unix_ms is not None else int(time() * 1000)
    contributors = dict(previous.contributors) if previous is not None else {}
    metrics = dict(previous.metrics) if previous is not None else {}

    if isinstance(contribution, GraphContributionRetract):
        if contribution.contributor_id not in contributors:
            return GraphElementAggregationResult(state=previous)
        del contributors[contribution.contributor_id]
        if not contributors:
            return GraphElementAggregationResult(
                state=None,
                event=_delete_event(contribution.element_id, contribution.observed_at_unix_nano, emitted_at),
            )
    else:
        contributors[contribution.contributor_id] = GraphContributionSnapshot(
            observed_at_unix_nano=contribution.observed_at_unix_nano,
            element=contribution.element,
        )
        for name, delta in contribution.metric_deltas.items():
            metrics[name] = metrics.get(name, 0) + delta

    element = _merge_element(contribution.element_id, contributors, metrics)
    current_hash = payload_hash(element)
    state = GraphElementAggregateState(
        element_id=contribution.element_id,
        contributors=contributors,
        metrics=metrics,
        last_payload_hash=current_hash,
    )
    if previous is not None and previous.last_payload_hash == current_hash:
        return GraphElementAggregationResult(state=state)
    return GraphElementAggregationResult(
        state=state,
        event=_upsert_event(element, contribution.observed_at_unix_nano, emitted_at, current_hash),
    )


def payload_hash(element: GraphElement) -> str:
    return _digest(element.model_dump(mode="json"))


def _merge_element(
    element_id: str,
    contributors: dict[str, GraphContributionSnapshot],
    metrics: dict[str, MetricValue],
) -> GraphElement:
    ordered = sorted(
        contributors.items(),
        key=lambda item: (-item[1].observed_at_unix_nano, item[0]),
    )
    winner = ordered[0][1].element
    attributes: dict[str, object] = {}
    for _, snapshot in ordered:
        for name, value in snapshot.element.attributes.items():
            attributes.setdefault(name, value)
    if isinstance(winner, GraphNode):
        return GraphNode(id=element_id, type=winner.type, attributes=attributes)
    return GraphEdge(
        id=element_id,
        type=winner.type,
        source_id=winner.source_id,
        target_id=winner.target_id,
        attributes=attributes,
        metrics=dict(sorted(metrics.items())),
    )


def _upsert_event(
    element: GraphElement,
    observed_at_unix_nano: int,
    emitted_at_unix_ms: int,
    current_hash: str,
) -> GraphElementUpsertEvent:
    return GraphElementUpsertEvent(
        event_id=_event_id("upsert", element.id, observed_at_unix_nano, current_hash),
        element_id=element.id,
        observed_at_unix_nano=observed_at_unix_nano,
        emitted_at_unix_ms=emitted_at_unix_ms,
        payload_hash=current_hash,
        element=element,
    )


def _delete_event(
    element_id: str,
    observed_at_unix_nano: int,
    emitted_at_unix_ms: int,
) -> GraphElementDeleteEvent:
    return GraphElementDeleteEvent(
        event_id=_event_id("delete", element_id, observed_at_unix_nano, None),
        element_id=element_id,
        observed_at_unix_nano=observed_at_unix_nano,
        emitted_at_unix_ms=emitted_at_unix_ms,
    )


def _event_id(operation: str, element_id: str, observed_at_unix_nano: int, current_hash: str | None) -> str:
    return _digest(
        {
            "operation": operation,
            "element_id": element_id,
            "observed_at_unix_nano": observed_at_unix_nano,
            "payload_hash": current_hash,
        }
    )


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
