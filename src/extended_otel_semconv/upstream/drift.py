from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, computed_field

from extended_otel_semconv.registry.model import AttributeDefinition, EntityDefinition, load_registry_document


class DriftReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    added_attributes: tuple[str, ...] = ()
    removed_attributes: tuple[str, ...] = ()
    changed_attributes: tuple[str, ...] = ()
    added_entities: tuple[str, ...] = ()
    removed_entities: tuple[str, ...] = ()
    changed_entities: tuple[str, ...] = ()

    @computed_field
    @property
    def has_changes(self) -> bool:
        return any(
            (
                self.added_attributes,
                self.removed_attributes,
                self.changed_attributes,
                self.added_entities,
                self.removed_entities,
                self.changed_entities,
            )
        )

    def lines(self) -> list[str]:
        lines: list[str] = []
        for label, values in (
            ("added attributes", self.added_attributes),
            ("removed attributes", self.removed_attributes),
            ("changed attributes", self.changed_attributes),
            ("added entities", self.added_entities),
            ("removed entities", self.removed_entities),
            ("changed entities", self.changed_entities),
        ):
            if values:
                lines.append(f"{label}: {', '.join(values)}")
        return lines or ["no semantic convention drift detected"]


def compare_model_dirs(old_model_dir: Path, new_model_dir: Path, domain: str = "k8s") -> DriftReport:
    old_registry = load_registry_document(old_model_dir / domain / "registry.yaml")
    new_registry = load_registry_document(new_model_dir / domain / "registry.yaml")
    old_entities = load_registry_document(old_model_dir / domain / "entities.yaml")
    new_entities = load_registry_document(new_model_dir / domain / "entities.yaml")

    old_attributes = old_registry.attributes_by_id
    new_attributes = new_registry.attributes_by_id
    old_entity_map = old_entities.entities_by_name
    new_entity_map = new_entities.entities_by_name

    return DriftReport(
        added_attributes=tuple(sorted(set(new_attributes) - set(old_attributes))),
        removed_attributes=tuple(sorted(set(old_attributes) - set(new_attributes))),
        changed_attributes=tuple(sorted(_changed_attributes(old_attributes, new_attributes))),
        added_entities=tuple(sorted(set(new_entity_map) - set(old_entity_map))),
        removed_entities=tuple(sorted(set(old_entity_map) - set(new_entity_map))),
        changed_entities=tuple(sorted(_changed_entities(old_entity_map, new_entity_map))),
    )


def _changed_attributes(
    old_attributes: dict[str, AttributeDefinition], new_attributes: dict[str, AttributeDefinition]
) -> set[str]:
    changed: set[str] = set()
    for attribute_id in set(old_attributes) & set(new_attributes):
        old = old_attributes[attribute_id]
        new = new_attributes[attribute_id]
        if old.type != new.type or old.stability != new.stability or old.brief != new.brief:
            changed.add(attribute_id)
    return changed


def _changed_entities(old_entities: dict[str, EntityDefinition], new_entities: dict[str, EntityDefinition]) -> set[str]:
    changed: set[str] = set()
    for entity_name in set(old_entities) & set(new_entities):
        old = old_entities[entity_name]
        new = new_entities[entity_name]
        old_refs = tuple(attribute.ref for attribute in old.attributes)
        new_refs = tuple(attribute.ref for attribute in new.attributes)
        if old.id != new.id or old.stability != new.stability or old.brief != new.brief or old_refs != new_refs:
            changed.add(entity_name)
    return changed
