"""Typed payload parsing boundary used by the Flink interaction diff job."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Literal, cast

from pydantic import Field, RootModel, ValidationError

from extended_otel_semconv.graph.interaction import (
    FrozenModel,
    InteractionDlqEvent,
    InteractionObservation,
    JsonValue,
    digest,
    observation_from_metric_point,
)
from extended_otel_semconv.graph.metrics import (
    contains_only_ignored_service_graph_metrics,
    parse_metrics_json_document_with_names,
)


class ParsedObservation(FrozenModel):
    kind: Literal["observation"] = "observation"
    observation: InteractionObservation


class RejectedRecord(FrozenModel):
    kind: Literal["rejected"] = "rejected"
    rejection: InteractionDlqEvent


type ParsedPayload = Annotated[ParsedObservation | RejectedRecord, Field(discriminator="kind")]


class KafkaOutputRecord(FrozenModel):
    key: str = Field(min_length=1)
    value: str


class JsonDocument(RootModel[dict[str, JsonValue]]):
    pass


def observations_from_otlp_json_metrics_payload(payload: str) -> tuple[InteractionObservation, ...]:
    document = JsonDocument.model_validate_json(payload).root
    parsed = parse_metrics_json_document_with_names(cast(dict[str, object], document))
    observations: list[InteractionObservation] = []
    for point in parsed.points:
        observation = observation_from_metric_point(point)
        if observation is not None:
            observations.append(observation)
    return tuple(observations)


def iter_parsed_payloads(payload: str) -> Iterator[ParsedPayload]:
    try:
        document = JsonDocument.model_validate_json(payload).root
        parsed = parse_metrics_json_document_with_names(cast(dict[str, object], document))
        observations = tuple(
            observation
            for point in parsed.points
            if (observation := observation_from_metric_point(point)) is not None
        )
        if not observations:
            if contains_only_ignored_service_graph_metrics(parsed.metric_names):
                return
            raise ValueError("payload contains no valid timestamped servicegraph datapoints")
        for observation in observations:
            yield ParsedObservation(observation=observation)
    except (TypeError, ValidationError, ValueError) as exc:
        yield RejectedRecord(
            rejection=InteractionDlqEvent(
                reason=type(exc).__name__,
                detail=str(exc),
                payload=payload,
            )
        )


def iter_observations_or_dlq(payload: str) -> Iterator[InteractionObservation | InteractionDlqEvent]:
    """Compatibility iterator retained for callers that consume domain objects."""
    for parsed in iter_parsed_payloads(payload):
        if isinstance(parsed, ParsedObservation):
            yield parsed.observation
        else:
            yield parsed.rejection


def event_record(event_json: str, interaction_id: str) -> KafkaOutputRecord:
    return KafkaOutputRecord(key=interaction_id, value=event_json)


def dlq_record(rejection: InteractionDlqEvent) -> KafkaOutputRecord:
    return KafkaOutputRecord(
        key=digest({"payload": rejection.payload}),
        value=rejection.model_dump_json(),
    )
