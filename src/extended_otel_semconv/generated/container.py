from __future__ import annotations

from typing import ClassVar, Self

from pydantic import Field, computed_field

from extended_otel_semconv.entities import (
    RawAttributes,
    SemanticEntity,
    quoted_entity_id,
    string_value,
)

class ContainerRuntime(SemanticEntity):
    entity_type: ClassVar[str] = "container.runtime"

    container_runtime_description: str | None = Field(default=None, alias="container.runtime.description")
    container_runtime_name: str = Field(alias="container.runtime.name")
    container_runtime_version: str = Field(alias="container.runtime.version")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.container_runtime_name,
            self.container_runtime_version,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        container_runtime_name = string_value(attributes, "container.runtime.name")
        if container_runtime_name is None:
            return None
        container_runtime_version = string_value(attributes, "container.runtime.version")
        if container_runtime_version is None:
            return None
        return cls.model_validate({
            "container.runtime.description": string_value(attributes, "container.runtime.description"),
            "container.runtime.name": container_runtime_name,
            "container.runtime.version": container_runtime_version,
        })


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    for entity_class in (ContainerRuntime,):
        entity = entity_class.from_attributes(attributes)
        if entity is not None:
            entities.append(entity)
    return entities
