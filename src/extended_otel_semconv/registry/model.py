from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from extended_otel_semconv.registry.yaml_loader import load_yaml_document


class RegistryModel(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


class AttributeDefinition(RegistryModel):
    id: str
    type: Any = "string"
    stability: str
    brief: str


class EntityAttributeRef(RegistryModel):
    ref: str


class AttributeGroup(RegistryModel):
    id: str
    type: Literal["attribute_group"]
    attributes: tuple[AttributeDefinition, ...]


class EntityDefinition(RegistryModel):
    id: str
    type: Literal["entity"]
    name: str
    stability: str
    brief: str
    attributes: tuple[EntityAttributeRef, ...]


RegistryGroup = AttributeGroup | EntityDefinition


class RegistryDocument(RegistryModel):
    groups: tuple[RegistryGroup, ...] = Field(default_factory=tuple)

    @field_validator("groups", mode="before")
    @classmethod
    def parse_groups(cls, value: object) -> tuple[RegistryGroup, ...]:
        if not isinstance(value, list):
            raise TypeError("groups must be a list")
        adapter = TypeAdapter(RegistryGroup)
        return tuple(adapter.validate_python(group) for group in value)

    @property
    def attributes_by_id(self) -> dict[str, AttributeDefinition]:
        return {
            attribute.id: attribute
            for group in self.groups
            if isinstance(group, AttributeGroup)
            for attribute in group.attributes
        }

    @property
    def entities_by_name(self) -> dict[str, EntityDefinition]:
        return {group.name: group for group in self.groups if isinstance(group, EntityDefinition)}


def load_registry_document(path: Path) -> RegistryDocument:
    return RegistryDocument.model_validate(load_yaml_document(path))
