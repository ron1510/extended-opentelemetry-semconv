# Duplicate guards are internal but have direct behavioral contracts.
# pyright: reportPrivateUsage=false

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from extended_otel_semconv.registry.model import (
    RegistryDocument,
    load_registry_document,
    load_registry_documents,
    model_yaml_files,
)
from extended_otel_semconv.registry.validation import (
    _assert_no_duplicate_attributes,
    _assert_no_duplicate_entities,
    _assert_no_duplicate_relationships,
)
from extended_otel_semconv.registry.yaml_loader import load_yaml_document


def test_yaml_loader_requires_mapping_document(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="expected mapping document"):
        load_yaml_document(path)


def test_registry_parser_keeps_supported_groups_and_filters_attribute_refs(tmp_path: Path) -> None:
    path = tmp_path / "registry.yaml"
    path.write_text(
        """
groups:
  - id: registry.fixture
    type: attribute_group
    attributes:
      - id: service.name
        type: string
      - ref: ignored.reference
      - malformed
  - id: entity.service
    type: entity
    name: service
    attributes:
      - ref: service.name
        role: identifying
  - id: ignored.group
    type: span
""".lstrip(),
        encoding="utf-8",
    )

    registry = load_registry_document(path)

    assert set(registry.attributes_by_id) == {"service.name"}
    assert set(registry.entities_by_name) == {"service"}
    assert registry.relationships_by_id == {}


def test_registry_groups_must_be_a_list() -> None:
    with pytest.raises(TypeError, match="groups must be a list"):
        RegistryDocument.model_validate({"groups": "invalid"})


def test_model_files_are_recursive_sorted_and_yaml_only(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    second = nested / "second.yaml"
    first = tmp_path / "first.yaml"
    ignored = tmp_path / "ignored.yml"
    for path in (second, first, ignored):
        path.write_text("groups: []\n", encoding="utf-8")

    files = model_yaml_files(tmp_path)
    merged = load_registry_documents(files)

    assert files == [first, second]
    assert merged.groups == ()


def test_duplicate_attributes_are_rejected() -> None:
    registry = _registry(
        """
  - id: registry.one
    type: attribute_group
    attributes:
      - id: duplicate
  - id: registry.two
    type: attribute_group
    attributes:
      - id: duplicate
"""
    )

    with pytest.raises(AssertionError, match="duplicate extension attribute duplicate"):
        _assert_no_duplicate_attributes(registry)


@pytest.mark.parametrize(
    ("second_id", "second_name", "message"),
    [
        ("entity.same", "other", "duplicate extension entity id entity.same"),
        ("entity.other", "same", "duplicate extension entity name same"),
    ],
)
def test_duplicate_entity_ids_and_names_are_rejected(second_id: str, second_name: str, message: str) -> None:
    registry = _registry(
        f"""
  - id: entity.same
    type: entity
    name: same
    attributes: []
  - id: {second_id}
    type: entity
    name: {second_name}
    attributes: []
"""
    )

    with pytest.raises(AssertionError, match=message):
        _assert_no_duplicate_entities(registry)


def test_duplicate_relationship_ids_are_rejected() -> None:
    registry = _registry(
        """
  - id: relationship.same
    type: relationship
    name: calls
    source_entity: service
    target_entity: service
    source_signals: [service_graph]
  - id: relationship.same
    type: relationship
    name: queries
    source_entity: service
    target_entity: service
    source_signals: [service_graph]
"""
    )

    with pytest.raises(AssertionError, match="duplicate extension relationship id relationship.same"):
        _assert_no_duplicate_relationships(registry)


def _registry(groups: str) -> RegistryDocument:
    document = yaml.safe_load(f"groups:\n{groups}")
    assert isinstance(document, dict)
    return RegistryDocument.model_validate(document)
