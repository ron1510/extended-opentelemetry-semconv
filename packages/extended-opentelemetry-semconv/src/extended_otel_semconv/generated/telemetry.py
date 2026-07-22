from __future__ import annotations

from typing import ClassVar, Self

from pydantic import Field, computed_field

from extended_otel_semconv.entities import (
    RawAttributes,
    SemanticEntity,
    quoted_entity_id,
    string_value,
)

class TelemetryDistro(SemanticEntity):
    entity_type: ClassVar[str] = "telemetry.distro"

    telemetry_distro_name: str = Field(alias="telemetry.distro.name")
    telemetry_distro_version: str | None = Field(default=None, alias="telemetry.distro.version")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.telemetry_distro_name,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        telemetry_distro_name = string_value(attributes, "telemetry.distro.name")
        if telemetry_distro_name is None:
            return None
        return cls.model_validate({
            "telemetry.distro.name": telemetry_distro_name,
            "telemetry.distro.version": string_value(attributes, "telemetry.distro.version"),
        })


class TelemetrySdk(SemanticEntity):
    entity_type: ClassVar[str] = "telemetry.sdk"

    telemetry_sdk_name: str = Field(alias="telemetry.sdk.name")
    telemetry_sdk_language: str = Field(alias="telemetry.sdk.language")
    telemetry_sdk_version: str | None = Field(default=None, alias="telemetry.sdk.version")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.telemetry_sdk_name,
            self.telemetry_sdk_language,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        telemetry_sdk_name = string_value(attributes, "telemetry.sdk.name")
        if telemetry_sdk_name is None:
            return None
        telemetry_sdk_language = string_value(attributes, "telemetry.sdk.language")
        if telemetry_sdk_language is None:
            return None
        return cls.model_validate({
            "telemetry.sdk.name": telemetry_sdk_name,
            "telemetry.sdk.language": telemetry_sdk_language,
            "telemetry.sdk.version": string_value(attributes, "telemetry.sdk.version"),
        })


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    for entity_class in (TelemetryDistro, TelemetrySdk):
        entity = entity_class.from_attributes(attributes)
        if entity is not None:
            entities.append(entity)
    return entities
