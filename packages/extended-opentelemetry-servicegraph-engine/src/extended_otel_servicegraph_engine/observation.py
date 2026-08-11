"""Normalized graph observations emitted after Collector datapoint pagination."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from extended_otel_servicegraph_engine.model import SourceSignal


class ObservedEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    type: str
    attributes: dict[str, object] = Field(default_factory=dict)


class ObservedEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    type: str
    attributes: dict[str, object] = Field(default_factory=dict)


class EntityObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["entity_observed"] = "entity_observed"
    observation_id: str
    observed_at_unix_nano: int | None = None
    source_signal: SourceSignal
    entity: ObservedEntity


class EdgeObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["edge_observed"] = "edge_observed"
    observation_id: str
    observed_at_unix_nano: int | None = None
    source_signal: SourceSignal
    edge: ObservedEdge


GraphObservation = EntityObservation | EdgeObservation
