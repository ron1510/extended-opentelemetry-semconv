from __future__ import annotations

from pathlib import Path

from extended_otel_semconv.registry.model import AttributeGroup, EntityDefinition, load_registry_document


def validate_model_files(registry_path: Path, entities_path: Path) -> None:
    registry = load_registry_document(registry_path)
    entities = load_registry_document(entities_path)

    attribute_ids: set[str] = set()
    for group in registry.groups:
        if not isinstance(group, AttributeGroup):
            raise AssertionError(f"{registry_path}: expected only attribute_group entries")
        for attribute in group.attributes:
            if attribute.id in attribute_ids:
                raise AssertionError(f"{registry_path}: duplicate attribute {attribute.id}")
            attribute_ids.add(attribute.id)

    entity_ids: set[str] = set()
    entity_names: set[str] = set()
    for group in entities.groups:
        if not isinstance(group, EntityDefinition):
            raise AssertionError(f"{entities_path}: expected only entity entries")
        if group.id in entity_ids:
            raise AssertionError(f"{entities_path}: duplicate entity id {group.id}")
        if group.name in entity_names:
            raise AssertionError(f"{entities_path}: duplicate entity name {group.name}")
        entity_ids.add(group.id)
        entity_names.add(group.name)
        for attribute_ref in group.attributes:
            if attribute_ref.ref not in attribute_ids:
                raise AssertionError(f"{entities_path}: {group.name} references unknown attribute {attribute_ref.ref}")
