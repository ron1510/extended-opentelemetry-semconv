from __future__ import annotations

from typing import ClassVar, Self

from pydantic import Field, computed_field

from extended_otel_semconv.entities import (
    RawAttributes,
    SemanticEntity,
    quoted_entity_id,
    string_value,
)

class VcsRef(SemanticEntity):
    entity_type: ClassVar[str] = "vcs.ref"

    vcs_ref_head_name: str | None = Field(default=None, alias="vcs.ref.head.name")
    vcs_ref_head_revision: str = Field(alias="vcs.ref.head.revision")
    vcs_ref_type: str | None = Field(default=None, alias="vcs.ref.type")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.vcs_ref_head_revision,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        vcs_ref_head_revision = string_value(attributes, "vcs.ref.head.revision")
        if vcs_ref_head_revision is None:
            return None
        return cls.model_validate({
            "vcs.ref.head.name": string_value(attributes, "vcs.ref.head.name"),
            "vcs.ref.head.revision": vcs_ref_head_revision,
            "vcs.ref.type": string_value(attributes, "vcs.ref.type"),
        })


class VcsRepository(SemanticEntity):
    entity_type: ClassVar[str] = "vcs.repository"

    vcs_repository_url_full: str = Field(alias="vcs.repository.url.full")
    vcs_repository_name: str | None = Field(default=None, alias="vcs.repository.name")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.vcs_repository_url_full,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        vcs_repository_url_full = string_value(attributes, "vcs.repository.url.full")
        if vcs_repository_url_full is None:
            return None
        return cls.model_validate({
            "vcs.repository.url.full": vcs_repository_url_full,
            "vcs.repository.name": string_value(attributes, "vcs.repository.name"),
        })


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    for entity_class in (VcsRef, VcsRepository):
        entity = entity_class.from_attributes(attributes)
        if entity is not None:
            entities.append(entity)
    return entities
