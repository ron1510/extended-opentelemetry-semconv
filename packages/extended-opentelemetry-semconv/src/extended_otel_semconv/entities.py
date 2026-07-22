"""Runtime primitives shared by generated semantic entity classes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

RawAttributes = Mapping[str, Any]


def string_value(attributes: RawAttributes, key: str) -> str | None:
    value = attributes.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool | int | float):
        return str(value)
    return None


def int_value(attributes: RawAttributes, key: str) -> int | None:
    value = attributes.get(key)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def bool_value(attributes: RawAttributes, key: str) -> bool | None:
    value = attributes.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return True
        if normalized in {"false", "0"}:
            return False
    return None


def object_value(attributes: RawAttributes, key: str) -> object | None:
    return attributes.get(key)


def quoted_entity_id(entity_type: str, *parts: object) -> str:
    encoded_parts = (quote(str(part), safe="") for part in parts)
    return ":".join((entity_type, *encoded_parts))


class SemanticEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    entity_type: ClassVar[str]

    @property
    def entity_id(self) -> str:
        raise NotImplementedError


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    from extended_otel_semconv.generated import entities_from_attributes as generated_entities_from_attributes

    return generated_entities_from_attributes(attributes)
