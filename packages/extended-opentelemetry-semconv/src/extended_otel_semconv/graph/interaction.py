"""Typed interaction state and deterministic diffing for servicegraph metrics."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from time import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from extended_otel_semconv.entities import SemanticEntity
from extended_otel_semconv.graph.metrics import MetricPoint, MetricTemporality
from extended_otel_semconv.graph.service_graph import entities_from_service_graph_side, service_graph_edge_type

SCHEMA_VERSION = "1.0"
INTERACTION_EVENT_TYPE = "interaction_state_changed"
DEFAULT_INTERACTION_TTL_SECONDS = 300
DEFAULT_ALLOWED_LATENESS_SECONDS = 60

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
UnixNano = Annotated[int, Field(gt=0)]
UnixMilli = Annotated[int, Field(ge=0)]
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

    @property
    def metric_value(self) -> MetricValue:
        return self.metric.value


class InteractionPayload(FrozenModel):
    client: NonEmptyString
    server: NonEmptyString
    connection_type: NonEmptyString
    dimensions: DimensionMap = Field(default_factory=dict)
    metrics: dict[str, MetricValue] = Field(default_factory=dict)
    entities: tuple[InteractionEntityRef, ...] = ()


class InteractionState(FrozenModel):
    interaction_id: NonEmptyString
    client: NonEmptyString
    server: NonEmptyString
    connection_type: NonEmptyString
    dimensions: DimensionMap = Field(default_factory=dict)
    entities: tuple[InteractionEntityRef, ...] = ()
    metrics_by_name: dict[str, InteractionMetric] = Field(default_factory=dict)
    first_seen_unix_nano: UnixNano
    last_seen_unix_nano: UnixNano
    last_payload_hash: NonEmptyString
    expires_at_unix_nano: UnixNano

class InteractionEventBase(FrozenModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    event_id: NonEmptyString
    event_type: Literal["interaction_state_changed"] = INTERACTION_EVENT_TYPE
    interaction_id: NonEmptyString
    observed_at_unix_nano: UnixNano
    emitted_at_unix_ms: UnixMilli


class InteractionUpsertEvent(InteractionEventBase):
    operation: Literal["upsert"] = "upsert"
    payload_hash: NonEmptyString
    interaction: InteractionPayload


class InteractionDeleteEvent(InteractionEventBase):
    operation: Literal["delete"] = "delete"
    payload_hash: None = None
    interaction: None = None


type InteractionEvent = Annotated[
    InteractionUpsertEvent | InteractionDeleteEvent,
    Field(discriminator="operation"),
]


class InteractionDiffResult(FrozenModel):
    state: InteractionState
    event: InteractionEvent | None = None


class InteractionDlqEvent(FrozenModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    event_type: Literal["interaction_record_rejected"] = "interaction_record_rejected"
    reason: NonEmptyString
    payload: str
    detail: str | None = None


def observation_from_metric_point(point: MetricPoint) -> InteractionObservation | None:
    return observation_from_servicegraph_datapoint(
        metric_name=point.name,
        attributes=point.attributes,
        value=point.value,
        observed_at_unix_nano=point.observed_at_unix_nano,
        temporality=point.temporality,
        start_time_unix_nano=point.start_time_unix_nano,
    )


def observation_from_servicegraph_datapoint(
    metric_name: str,
    attributes: Mapping[str, TelemetryScalar],
    value: MetricValue,
    observed_at_unix_nano: int | None,
    *,
    temporality: MetricTemporality = "cumulative",
    start_time_unix_nano: int | None = None,
) -> InteractionObservation | None:
    client_name = _string_attribute(attributes, "client")
    server_name = _string_attribute(attributes, "server")
    if client_name is None or server_name is None or observed_at_unix_nano is None:
        return None
    dimensions: DimensionMap = {
        key: attribute_value
        for key, attribute_value in attributes.items()
        if key not in {"client", "server", "connection_type"}
    }
    client_entities = _entity_refs(entities_from_service_graph_side(attributes, "client", client_name))
    server_entities = _entity_refs(entities_from_service_graph_side(attributes, "server", server_name))
    connection_type = service_graph_edge_type(attributes)
    interaction_id = build_interaction_id(client_name, server_name, connection_type, dimensions)
    return InteractionObservation(
        interaction_id=interaction_id,
        metric_name=metric_name,
        metric=InteractionMetric(
            value=value,
            temporality=temporality,
            start_time_unix_nano=start_time_unix_nano,
        ),
        observed_at_unix_nano=observed_at_unix_nano,
        client=InteractionEndpoint(service=client_name, entities=client_entities),
        server=InteractionEndpoint(service=server_name, entities=server_entities),
        connection_type=connection_type,
        dimensions=dimensions,
    )


def apply_observation(
    previous: InteractionState | None,
    observation: InteractionObservation,
    *,
    ttl_seconds: int = DEFAULT_INTERACTION_TTL_SECONDS,
    expiry_base_unix_nano: int | None = None,
    emitted_at_unix_ms: int | None = None,
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
    emitted_at = emitted_at_unix_ms if emitted_at_unix_ms is not None else int(time() * 1000)
    return InteractionDiffResult(
        state=state,
        event=upsert_event(state, observation.observed_at_unix_nano, emitted_at),
    )


def metric_has_advanced(previous: InteractionMetric | None, current: InteractionMetric) -> bool:
    if previous is None:
        return True
    if current.temporality == "delta":
        return current.value != 0
    if current.start_time_unix_nano != previous.start_time_unix_nano:
        return True
    return current.value != previous.value


def expire_state(
    state: InteractionState,
    timer_unix_nano: int,
    *,
    emitted_at_unix_ms: int | None = None,
) -> InteractionDeleteEvent | None:
    if timer_unix_nano < state.expires_at_unix_nano:
        return None
    emitted_at = emitted_at_unix_ms if emitted_at_unix_ms is not None else int(time() * 1000)
    return delete_event(state, state.expires_at_unix_nano, emitted_at)


def upsert_event(
    state: InteractionState,
    observed_at_unix_nano: int,
    emitted_at_unix_ms: int,
) -> InteractionUpsertEvent:
    return InteractionUpsertEvent(
        event_id=event_id("upsert", state.interaction_id, observed_at_unix_nano, state.last_payload_hash),
        interaction_id=state.interaction_id,
        observed_at_unix_nano=observed_at_unix_nano,
        emitted_at_unix_ms=emitted_at_unix_ms,
        payload_hash=state.last_payload_hash,
        interaction=interaction_payload(state),
    )


def delete_event(
    state: InteractionState,
    observed_at_unix_nano: int,
    emitted_at_unix_ms: int,
) -> InteractionDeleteEvent:
    return InteractionDeleteEvent(
        event_id=event_id("delete", state.interaction_id, observed_at_unix_nano, None),
        interaction_id=state.interaction_id,
        observed_at_unix_nano=observed_at_unix_nano,
        emitted_at_unix_ms=emitted_at_unix_ms,
    )


def interaction_payload(state: InteractionState) -> InteractionPayload:
    return InteractionPayload(
        client=state.client,
        server=state.server,
        connection_type=state.connection_type,
        dimensions=dict(sorted(state.dimensions.items())),
        metrics={name: metric.value for name, metric in sorted(state.metrics_by_name.items())},
        entities=state.entities,
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


def payload_hash(state: InteractionState) -> str:
    payload = interaction_payload(state).model_dump(mode="json")
    return digest(payload)


def event_id(
    operation: Literal["upsert", "delete"],
    interaction_id: str,
    observed_at_unix_nano: int,
    payload: str | None,
) -> str:
    return digest(
        {
            "operation": operation,
            "interaction_id": interaction_id,
            "observed_at_unix_nano": observed_at_unix_nano,
            "payload_hash": payload,
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
    provisional = InteractionState(
        interaction_id=observation.interaction_id,
        client=observation.client.service,
        server=observation.server.service,
        connection_type=observation.connection_type,
        dimensions=observation.dimensions,
        entities=entities,
        metrics_by_name=metrics_by_name,
        first_seen_unix_nano=first_seen_unix_nano,
        last_seen_unix_nano=observation.observed_at_unix_nano,
        last_payload_hash="pending",
        expires_at_unix_nano=expiry_base_unix_nano + ttl_seconds * 1_000_000_000,
    )
    return provisional.model_copy(update={"last_payload_hash": payload_hash(provisional)})


def _entity_refs(entities: list[SemanticEntity]) -> tuple[InteractionEntityRef, ...]:
    return tuple(InteractionEntityRef(id=entity.entity_id, type=entity.entity_type) for entity in entities)


def _canonical_json(value: JsonValue) -> str:
    return json.dumps(canonicalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _string_attribute(attributes: Mapping[str, TelemetryScalar], key: str) -> str | None:
    value = attributes.get(key)
    return value if isinstance(value, str) and value else None
