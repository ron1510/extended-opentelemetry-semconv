from __future__ import annotations

from typing import ClassVar, Self

from pydantic import Field, computed_field

from extended_otel_semconv.entities import (
    RawAttributes,
    SemanticEntity,
    quoted_entity_id,
    string_value,
)

class OpenshiftClusterquota(SemanticEntity):
    entity_type: ClassVar[str] = "openshift.clusterquota"

    openshift_clusterquota_uid: str = Field(alias="openshift.clusterquota.uid")
    openshift_clusterquota_name: str | None = Field(default=None, alias="openshift.clusterquota.name")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.openshift_clusterquota_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        openshift_clusterquota_uid = string_value(attributes, "openshift.clusterquota.uid")
        if openshift_clusterquota_uid is None:
            return None
        return cls.model_validate({
            "openshift.clusterquota.uid": openshift_clusterquota_uid,
            "openshift.clusterquota.name": string_value(attributes, "openshift.clusterquota.name"),
        })


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    for entity_class in (OpenshiftClusterquota,):
        entity = entity_class.from_attributes(attributes)
        if entity is not None:
            entities.append(entity)
    return entities
