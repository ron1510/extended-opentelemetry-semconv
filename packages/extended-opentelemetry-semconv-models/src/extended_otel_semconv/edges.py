"""Runtime primitives shared by generated semantic edge classes."""

from __future__ import annotations

import hashlib
import json
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, computed_field, model_validator

from extended_otel_semconv.errors import (
    SemanticIdentityMismatchError,
    SemanticModelValidationError,
    UnknownSemanticTypeError,
)

type MetricValue = int | float


def edge_id(source_id: str, relationship_type: str, target_id: str) -> str:
    value = {"source_id": source_id, "type": relationship_type, "target_id": target_id}
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"edge:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


class SemanticEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relationship_id: ClassVar[str]
    relationship_type: ClassVar[str]
    source_entity_type: ClassVar[str]
    target_entity_type: ClassVar[str]

    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    attributes: dict[str, object] = Field(default_factory=dict)
    metrics: dict[str, MetricValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_endpoint_types(self) -> SemanticEdge:
        if _entity_type_from_id(self.source_id) != self.source_entity_type:
            raise ValueError(f"source_id must identify {self.source_entity_type!r}, got {self.source_id!r}")
        if _entity_type_from_id(self.target_id) != self.target_entity_type:
            raise ValueError(f"target_id must identify {self.target_entity_type!r}, got {self.target_id!r}")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def edge_id(self) -> str:
        return edge_id(self.source_id, self.relationship_type, self.target_id)


def semantic_edge_from_data(
    relationship_type: str,
    source_id: str,
    target_id: str,
    *,
    attributes: dict[str, object] | None = None,
    metrics: dict[str, MetricValue] | None = None,
    expected_id: str | None = None,
) -> SemanticEdge:
    from extended_otel_semconv.generated.edges import EDGE_MODELS

    source_type = _entity_type_from_id(source_id)
    target_type = _entity_type_from_id(target_id)
    model = EDGE_MODELS.get((source_type, relationship_type, target_type))
    if model is None:
        raise UnknownSemanticTypeError(
            "no generated semantic edge model for "
            f"{source_type!r} -[{relationship_type!r}]-> {target_type!r}"
        )
    try:
        edge = model(
            source_id=source_id,
            target_id=target_id,
            attributes=attributes or {},
            metrics=metrics or {},
        )
    except ValidationError as error:
        raise SemanticModelValidationError(f"invalid {model.__name__} data: {error}") from error
    if expected_id is not None and edge.edge_id != expected_id:
        raise SemanticIdentityMismatchError(
            f"stored edge ID {expected_id!r} does not match reconstructed ID {edge.edge_id!r}"
        )
    return edge


def _entity_type_from_id(element_id: str) -> str:
    entity_type, separator, identity = element_id.partition(":")
    if not separator or not entity_type or not identity:
        raise SemanticModelValidationError(f"invalid semantic entity ID: {element_id!r}")
    return entity_type
