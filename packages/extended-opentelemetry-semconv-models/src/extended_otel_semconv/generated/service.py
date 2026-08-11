from __future__ import annotations

from typing import ClassVar, Self

from pydantic import Field, computed_field

from extended_otel_semconv.entities import (
    RawAttributes,
    SemanticEntity,
    quoted_entity_id,
    string_value,
)

class Service(SemanticEntity):
    entity_type: ClassVar[str] = "service"

    service_name: str = Field(alias="service.name")
    service_version: str | None = Field(default=None, alias="service.version")
    service_criticality: str | None = Field(default=None, alias="service.criticality")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.service_name,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        service_name = string_value(attributes, "service.name")
        if service_name is None:
            return None
        return cls.model_validate({
            "service.name": service_name,
            "service.version": string_value(attributes, "service.version"),
            "service.criticality": string_value(attributes, "service.criticality"),
        })


class ServiceInstance(SemanticEntity):
    entity_type: ClassVar[str] = "service.instance"

    service_instance_id: str = Field(alias="service.instance.id")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.service_instance_id,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        service_instance_id = string_value(attributes, "service.instance.id")
        if service_instance_id is None:
            return None
        return cls.model_validate({
            "service.instance.id": service_instance_id,
        })


class ServiceNamespace(SemanticEntity):
    entity_type: ClassVar[str] = "service.namespace"

    service_namespace: str = Field(alias="service.namespace")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.service_namespace,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        service_namespace = string_value(attributes, "service.namespace")
        if service_namespace is None:
            return None
        return cls.model_validate({
            "service.namespace": service_namespace,
        })


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    for entity_class in (Service, ServiceInstance, ServiceNamespace):
        entity = entity_class.from_attributes(attributes)
        if entity is not None:
            entities.append(entity)
    return entities
