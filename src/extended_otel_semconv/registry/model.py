"""Pydantic models for the subset of OTel registry YAML this project consumes."""

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
    stability: str | None = None
    brief: str | None = None


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
    stability: str | None = None
    brief: str | None = None
    attributes: tuple[EntityAttributeRef, ...]


class RelationshipDefinition(RegistryModel):
    id: str
    type: Literal["relationship"]
    name: str
    source_entity: str
    target_entity: str
    source_signals: tuple[str, ...]
    stability: str | None = None
    brief: str | None = None


RegistryGroup = AttributeGroup | EntityDefinition | RelationshipDefinition


class RegistryDocument(RegistryModel):
    groups: tuple[RegistryGroup, ...] = Field(default_factory=tuple)

    @field_validator("groups", mode="before")
    @classmethod
    def parse_groups(cls, value: object) -> tuple[RegistryGroup, ...]:
        if not isinstance(value, list | tuple):
            raise TypeError("groups must be a list")
        adapter: TypeAdapter[RegistryGroup] = TypeAdapter(RegistryGroup)
        groups: list[RegistryGroup] = []
        for group in value:
            if isinstance(group, AttributeGroup | EntityDefinition | RelationshipDefinition):
                groups.append(group)
                continue
            if not isinstance(group, dict) or group.get("type") not in {"attribute_group", "entity", "relationship"}:
                continue
            if group.get("type") == "attribute_group":
                group = {
                    **group,
                    "attributes": [
                        attribute
                        for attribute in group.get("attributes", [])
                        if isinstance(attribute, dict) and "id" in attribute
                    ],
                }
            groups.append(adapter.validate_python(group))
        return tuple(groups)

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

    @property
    def relationships_by_id(self) -> dict[str, RelationshipDefinition]:
        return {group.id: group for group in self.groups if isinstance(group, RelationshipDefinition)}


def load_registry_document(path: Path) -> RegistryDocument:
    return RegistryDocument.model_validate(load_yaml_document(path))


def load_registry_documents(paths: list[Path]) -> RegistryDocument:
    groups: list[RegistryGroup] = []
    for path in paths:
        groups.extend(load_registry_document(path).groups)
    return RegistryDocument(groups=tuple(groups))


def model_yaml_files(model_dir: Path) -> list[Path]:
    return sorted(path for path in model_dir.rglob("*.yaml") if path.is_file())
