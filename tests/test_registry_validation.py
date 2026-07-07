from __future__ import annotations

from pathlib import Path

from extended_otel_semconv.registry.model import AttributeGroup, EntityDefinition, load_registry_document
from extended_otel_semconv.registry.validation import validate_model_files

ROOT = Path(__file__).resolve().parents[1]


def test_otel_style_registry_files_parse_into_pydantic_models() -> None:
    validate_model_files(ROOT / "model" / "k8s" / "registry.yaml", ROOT / "model" / "k8s" / "entities.yaml")

    registry = load_registry_document(ROOT / "model" / "k8s" / "registry.yaml")
    entities = load_registry_document(ROOT / "model" / "k8s" / "entities.yaml")

    assert isinstance(registry.groups[0], AttributeGroup)
    assert all(isinstance(group, EntityDefinition) for group in entities.groups)
    assert "k8s.pod.uid" in registry.attributes_by_id
    assert "k8s.pod" in entities.entities_by_name
