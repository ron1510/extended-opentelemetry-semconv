"""Runtime semantic relationship definitions."""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files

from pydantic import BaseModel, ConfigDict, TypeAdapter


class RelationshipDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    type: str
    name: str
    source_entity: str
    target_entity: str
    source_signals: tuple[str, ...]
    stability: str | None = None
    brief: str | None = None


@cache
def service_graph_relationships() -> tuple[RelationshipDefinition, ...]:
    metadata = files("extended_otel_semconv").joinpath("metadata", "service-graph-relationships.json")
    document = json.loads(metadata.read_text(encoding="utf-8"))
    return TypeAdapter(tuple[RelationshipDefinition, ...]).validate_python(document)
