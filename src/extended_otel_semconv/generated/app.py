from __future__ import annotations

from typing import ClassVar, Self

from pydantic import Field, computed_field

from extended_otel_semconv.entities import (
    RawAttributes,
    SemanticEntity,
    quoted_entity_id,
    string_value,
)

class App(SemanticEntity):
    entity_type: ClassVar[str] = "app"

    app_installation_id: str | None = Field(default=None, alias="app.installation.id")
    app_build_id: str = Field(alias="app.build_id")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.app_build_id,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        app_build_id = string_value(attributes, "app.build_id")
        if app_build_id is None:
            return None
        return cls.model_validate({
            "app.installation.id": string_value(attributes, "app.installation.id"),
            "app.build_id": app_build_id,
        })


class AppEndpoint(SemanticEntity):
    entity_type: ClassVar[str] = "app.endpoint"

    service_name: str = Field(alias="service.name")
    service_namespace: str = Field(alias="service.namespace")
    http_request_method: str = Field(alias="http.request.method")
    http_route: str = Field(alias="http.route")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.service_name,
            self.service_namespace,
            self.http_request_method,
            self.http_route,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        service_name = string_value(attributes, "service.name")
        if service_name is None:
            return None
        service_namespace = string_value(attributes, "service.namespace")
        if service_namespace is None:
            return None
        http_request_method = string_value(attributes, "http.request.method")
        if http_request_method is None:
            return None
        http_route = string_value(attributes, "http.route")
        if http_route is None:
            return None
        return cls.model_validate({
            "service.name": service_name,
            "service.namespace": service_namespace,
            "http.request.method": http_request_method,
            "http.route": http_route,
        })


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    for entity_class in (App, AppEndpoint):
        entity = entity_class.from_attributes(attributes)
        if entity is not None:
            entities.append(entity)
    return entities
