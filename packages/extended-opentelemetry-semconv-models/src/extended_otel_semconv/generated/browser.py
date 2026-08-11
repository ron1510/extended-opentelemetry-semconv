from __future__ import annotations

from typing import ClassVar, Self

from pydantic import Field, computed_field

from extended_otel_semconv.entities import (
    RawAttributes,
    SemanticEntity,
    quoted_entity_id,
    string_value,
)

class BrowserDocument(SemanticEntity):
    entity_type: ClassVar[str] = "browser.document"

    browser_document_url_full: str = Field(alias="browser.document.url.full")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.browser_document_url_full,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        browser_document_url_full = string_value(attributes, "browser.document.url.full")
        if browser_document_url_full is None:
            return None
        return cls.model_validate({
            "browser.document.url.full": browser_document_url_full,
        })


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    for entity_class in (BrowserDocument,):
        entity = entity_class.from_attributes(attributes)
        if entity is not None:
            entities.append(entity)
    return entities
