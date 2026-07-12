from __future__ import annotations

from typing import ClassVar, Self

from pydantic import Field, computed_field

from extended_otel_semconv.entities import (
    RawAttributes,
    SemanticEntity,
    quoted_entity_id,
    string_value,
)

class CicdPipeline(SemanticEntity):
    entity_type: ClassVar[str] = "cicd.pipeline"

    cicd_pipeline_name: str = Field(alias="cicd.pipeline.name")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.cicd_pipeline_name,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        cicd_pipeline_name = string_value(attributes, "cicd.pipeline.name")
        if cicd_pipeline_name is None:
            return None
        return cls.model_validate({
            "cicd.pipeline.name": cicd_pipeline_name,
        })


class CicdPipelineRun(SemanticEntity):
    entity_type: ClassVar[str] = "cicd.pipeline.run"

    cicd_pipeline_run_id: str = Field(alias="cicd.pipeline.run.id")
    cicd_pipeline_run_url_full: str | None = Field(default=None, alias="cicd.pipeline.run.url.full")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.cicd_pipeline_run_id,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        cicd_pipeline_run_id = string_value(attributes, "cicd.pipeline.run.id")
        if cicd_pipeline_run_id is None:
            return None
        return cls.model_validate({
            "cicd.pipeline.run.id": cicd_pipeline_run_id,
            "cicd.pipeline.run.url.full": string_value(attributes, "cicd.pipeline.run.url.full"),
        })


class CicdWorker(SemanticEntity):
    entity_type: ClassVar[str] = "cicd.worker"

    cicd_worker_id: str = Field(alias="cicd.worker.id")
    cicd_worker_name: str | None = Field(default=None, alias="cicd.worker.name")
    cicd_worker_url_full: str | None = Field(default=None, alias="cicd.worker.url.full")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.cicd_worker_id,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        cicd_worker_id = string_value(attributes, "cicd.worker.id")
        if cicd_worker_id is None:
            return None
        return cls.model_validate({
            "cicd.worker.id": cicd_worker_id,
            "cicd.worker.name": string_value(attributes, "cicd.worker.name"),
            "cicd.worker.url.full": string_value(attributes, "cicd.worker.url.full"),
        })


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    for entity_class in (CicdPipeline, CicdPipelineRun, CicdWorker):
        entity = entity_class.from_attributes(attributes)
        if entity is not None:
            entities.append(entity)
    return entities
