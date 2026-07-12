from __future__ import annotations

from typing import ClassVar, Self

from pydantic import Field, computed_field

from extended_otel_semconv.entities import (
    RawAttributes,
    SemanticEntity,
    quoted_entity_id,
    string_value,
)

class GcpGceInstanceGroupManager(SemanticEntity):
    entity_type: ClassVar[str] = "gcp.gce.instance_group_manager"

    gcp_gce_instance_group_manager_name: str = Field(alias="gcp.gce.instance_group_manager.name")
    gcp_gce_instance_group_manager_zone: str = Field(alias="gcp.gce.instance_group_manager.zone")
    gcp_gce_instance_group_manager_region: str = Field(alias="gcp.gce.instance_group_manager.region")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.gcp_gce_instance_group_manager_name,
            self.gcp_gce_instance_group_manager_zone,
            self.gcp_gce_instance_group_manager_region,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        gcp_gce_instance_group_manager_name = string_value(attributes, "gcp.gce.instance_group_manager.name")
        if gcp_gce_instance_group_manager_name is None:
            return None
        gcp_gce_instance_group_manager_zone = string_value(attributes, "gcp.gce.instance_group_manager.zone")
        if gcp_gce_instance_group_manager_zone is None:
            return None
        gcp_gce_instance_group_manager_region = string_value(attributes, "gcp.gce.instance_group_manager.region")
        if gcp_gce_instance_group_manager_region is None:
            return None
        return cls.model_validate({
            "gcp.gce.instance_group_manager.name": gcp_gce_instance_group_manager_name,
            "gcp.gce.instance_group_manager.zone": gcp_gce_instance_group_manager_zone,
            "gcp.gce.instance_group_manager.region": gcp_gce_instance_group_manager_region,
        })


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    for entity_class in (GcpGceInstanceGroupManager,):
        entity = entity_class.from_attributes(attributes)
        if entity is not None:
            entities.append(entity)
    return entities
