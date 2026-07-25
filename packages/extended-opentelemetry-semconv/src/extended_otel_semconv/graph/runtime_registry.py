"""Packaged relationship definitions used by runtime graph normalization."""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files

from pydantic import TypeAdapter

from extended_otel_semconv.registry.model import RelationshipDefinition


@cache
def service_graph_relationships() -> tuple[RelationshipDefinition, ...]:
    metadata = files("extended_otel_semconv").joinpath("metadata", "service-graph-relationships.json")
    document = json.loads(metadata.read_text(encoding="utf-8"))
    return TypeAdapter(tuple[RelationshipDefinition, ...]).validate_python(document)
