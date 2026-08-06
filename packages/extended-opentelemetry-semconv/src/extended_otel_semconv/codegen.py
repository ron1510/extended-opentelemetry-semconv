"""Generate entity models and Collector dimensions from OTel registries."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

import yaml

from extended_otel_semconv.graph.dimensions import service_graph_dimensions
from extended_otel_semconv.graph.elements import GRAPH_REQUEST_FAILED_TOTAL, GRAPH_REQUEST_TOTAL
from extended_otel_semconv.registry.model import (
    AttributeDefinition,
    EntityAttributeRef,
    EntityDefinition,
    RegistryDocument,
    RelationshipDefinition,
)
from extended_otel_semconv.registry.validation import load_model_registry, validate_extension_model

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ELASTICSEARCH_MAPPING_SCHEMA_VERSION = "1"


class GenerationPaths(NamedTuple):
    upstream_model: Path
    extension_model: Path
    upstream_lock: Path
    generated_dir: Path
    package_lock: Path
    relationship_metadata: Path
    collector_dimensions: Path
    elasticsearch_mapping: Path


class GeneratedEntity(NamedTuple):
    entity: EntityDefinition
    class_name: str
    domain: str
    field_refs: tuple[EntityAttributeRef, ...]
    identifying_refs: tuple[EntityAttributeRef, ...]


def default_generation_paths(root: Path = REPOSITORY_ROOT) -> GenerationPaths:
    package_root = root / "packages" / "extended-opentelemetry-semconv"
    package = package_root / "src" / "extended_otel_semconv"
    return GenerationPaths(
        upstream_model=package_root / "upstream" / "otel-semconv" / "v1.43.0" / "model",
        extension_model=package_root / "model" / "extensions",
        upstream_lock=package_root / "upstream" / "otel-semconv.lock.json",
        generated_dir=package / "generated",
        package_lock=package / "metadata" / "otel-semconv.lock.json",
        relationship_metadata=package / "metadata" / "service-graph-relationships.json",
        collector_dimensions=root / "deploy" / "helm" / "servicegraph-collector" / "files" / "dimensions.yaml",
        elasticsearch_mapping=package / "metadata" / "elasticsearch-graph-elements-index.json",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate models and Collector dimensions from the merged registry.")
    parser.add_argument("--check", action="store_true", help="Fail if generated files are not up to date.")
    args = parser.parse_args(argv)

    paths = default_generation_paths()
    files = generate_files(paths)
    if args.check:
        return check_files(files, paths.generated_dir)
    write_files(files, paths.generated_dir)
    return 0


def generate_files(paths: GenerationPaths) -> dict[Path, str]:
    validate_extension_model(paths.upstream_model, paths.extension_model)
    upstream = load_model_registry(paths.upstream_model)
    extension = load_model_registry(paths.extension_model)
    registry = _merged_registry(upstream, extension)
    attributes = registry.attributes_by_id
    relationships = registry.relationships_by_id

    generated_entities = tuple(
        _generated_entity(entity)
        for entity in sorted(registry.entities_by_name.values(), key=lambda item: item.name)
        if _identifying_refs(entity)
    )
    domains = sorted({entity.domain for entity in generated_entities})

    files: dict[Path, str] = {
        paths.generated_dir / "__init__.py": _render_package_init(generated_entities, domains),
        paths.package_lock: paths.upstream_lock.read_text(encoding="utf-8"),
        paths.relationship_metadata: _render_relationship_metadata(relationships),
        paths.collector_dimensions: _render_collector_dimensions(registry),
        paths.elasticsearch_mapping: _render_elasticsearch_mapping(registry, paths.upstream_lock),
    }
    for domain in domains:
        domain_entities = tuple(entity for entity in generated_entities if entity.domain == domain)
        files[paths.generated_dir / f"{domain}.py"] = _render_domain_module(domain_entities, attributes)
    return files


def write_files(files: dict[Path, str], generated_dir: Path) -> None:
    generated_dir.mkdir(parents=True, exist_ok=True)
    for stale_file in generated_dir.glob("*.py"):
        if stale_file not in files:
            stale_file.unlink()
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def check_files(files: dict[Path, str], generated_dir: Path) -> int:
    failed = False
    expected_generated = {path for path in files if path.parent == generated_dir and path.suffix == ".py"}
    for stale_file in sorted(set(generated_dir.glob("*.py")) - expected_generated):
        failed = True
        print(f"{stale_file} is stale")
    for path, expected in files.items():
        actual = path.read_text(encoding="utf-8") if path.exists() else ""
        if actual == expected:
            continue
        failed = True
        print(f"{path} is not up to date")
        for line in difflib.unified_diff(
            actual.splitlines(),
            expected.splitlines(),
            fromfile=f"{path} (actual)",
            tofile=f"{path} (expected)",
            lineterm="",
        ):
            print(line)
    return 1 if failed else 0


def _merged_registry(upstream: RegistryDocument, extension: RegistryDocument) -> RegistryDocument:
    return upstream.model_copy(update={"groups": (*upstream.groups, *extension.groups)})


def _generated_entity(entity: EntityDefinition) -> GeneratedEntity:
    return GeneratedEntity(
        entity=entity,
        class_name=_class_name(entity.name),
        domain=_domain_name(entity.name),
        field_refs=entity.attributes,
        identifying_refs=_identifying_refs(entity),
    )


def _identifying_refs(entity: EntityDefinition) -> tuple[EntityAttributeRef, ...]:
    return tuple(ref for ref in entity.attributes if getattr(ref, "role", None) == "identifying")


def _render_domain_module(entities: tuple[GeneratedEntity, ...], attributes: dict[str, AttributeDefinition]) -> str:
    value_readers = sorted({_value_reader(attributes.get(ref.ref)) for entity in entities for ref in entity.field_refs})
    imports = [
        "from __future__ import annotations",
        "",
        "from typing import ClassVar, Self",
        "",
        "from pydantic import Field, computed_field",
        "",
        "from extended_otel_semconv.entities import (",
        "    RawAttributes,",
        "    SemanticEntity,",
        "    quoted_entity_id,",
    ]
    imports.extend(f"    {reader}," for reader in value_readers)
    imports.extend([")", ""])
    blocks = [*imports]
    for entity in entities:
        blocks.extend(_render_entity_class(entity, attributes))
        blocks.extend(["", ""])
    blocks.extend(_render_domain_parser(entities))
    return _finalize(blocks)


def _render_entity_class(entity: GeneratedEntity, attributes: dict[str, AttributeDefinition]) -> list[str]:
    lines = [
        f"class {entity.class_name}(SemanticEntity):",
        f'    entity_type: ClassVar[str] = "{entity.entity.name}"',
        "",
    ]
    for ref in entity.field_refs:
        attribute = attributes.get(ref.ref)
        field_name = _field_name(ref.ref)
        python_type = _python_type(attribute)
        if ref in entity.identifying_refs:
            lines.append(f'    {field_name}: {python_type} = Field(alias="{ref.ref}")')
        else:
            lines.append(f'    {field_name}: {python_type} | None = Field(default=None, alias="{ref.ref}")')
    lines.extend(
        [
            "",
            "    @computed_field  # type: ignore[prop-decorator]",
            "    @property",
            "    def entity_id(self) -> str:",
            "        return quoted_entity_id(",
            "            self.entity_type,",
        ]
    )
    for ref in entity.identifying_refs:
        lines.append(f"            self.{_field_name(ref.ref)},")
    lines.extend(
        [
            "        )",
            "",
            "    @classmethod",
            "    def from_attributes(cls, attributes: RawAttributes) -> Self | None:",
        ]
    )
    for ref in entity.identifying_refs:
        attribute = attributes.get(ref.ref)
        field_name = _field_name(ref.ref)
        lines.append(f'        {field_name} = {_value_reader(attribute)}(attributes, "{ref.ref}")')
        lines.append(f"        if {field_name} is None:")
        lines.append("            return None")
    lines.append("        return cls.model_validate({")
    for ref in entity.field_refs:
        attribute = attributes.get(ref.ref)
        field_name = _field_name(ref.ref)
        if ref in entity.identifying_refs:
            lines.append(f'            "{ref.ref}": {field_name},')
        else:
            lines.append(f'            "{ref.ref}": {_value_reader(attribute)}(attributes, "{ref.ref}"),')
    lines.append("        })")
    return lines


def _render_domain_parser(entities: tuple[GeneratedEntity, ...]) -> list[str]:
    lines = [
        "def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:",
        "    entities: list[SemanticEntity] = []",
    ]
    if not entities:
        lines.append("    return entities")
        return lines
    class_names = ", ".join(entity.class_name for entity in entities)
    if len(entities) == 1:
        class_names += ","
    lines.extend(
        [
            f"    for entity_class in ({class_names}):",
            "        entity = entity_class.from_attributes(attributes)",
            "        if entity is not None:",
            "            entities.append(entity)",
            "    return entities",
        ]
    )
    return lines


def _render_package_init(entities: tuple[GeneratedEntity, ...], domains: list[str]) -> str:
    lines = [
        '\"\"\"Generated semantic entity interfaces.\"\"\"',
        "",
        "from extended_otel_semconv.entities import RawAttributes, SemanticEntity",
    ]
    for domain in domains:
        domain_entities = tuple(entity for entity in entities if entity.domain == domain)
        names = ", ".join(entity.class_name for entity in domain_entities)
        lines.append(f"from extended_otel_semconv.generated.{domain} import {names}")
        lines.append(
            f"from extended_otel_semconv.generated.{domain} import entities_from_attributes as _{domain}_entities"
        )
    lines.extend(
        [
            "",
            "",
            "def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:",
            "    entities: list[SemanticEntity] = []",
        ]
    )
    for domain in domains:
        lines.append(f"    entities.extend(_{domain}_entities(attributes))")
    lines.extend(["    return entities", "", "", "__all__ = ["])
    for entity in entities:
        lines.append(f'    "{entity.class_name}",')
    lines.extend(['    "SemanticEntity",', '    "entities_from_attributes",', "]"])
    return _finalize(lines)


def _render_relationship_metadata(relationships: dict[str, RelationshipDefinition]) -> str:
    rendered = [
        relationship.model_dump(mode="json")
        for relationship in sorted(relationships.values(), key=lambda item: item.id)
        if "service_graph" in relationship.source_signals
    ]
    return json.dumps(rendered, indent=2, sort_keys=True) + "\n"


def _render_collector_dimensions(registry: RegistryDocument) -> str:
    return yaml.safe_dump(
        {"dimensions": service_graph_dimensions(registry)},
        sort_keys=False,
        default_flow_style=False,
    )


def _render_elasticsearch_mapping(registry: RegistryDocument, upstream_lock: Path) -> str:
    attributes = {
        dimension: _elasticsearch_field_mapping(registry.attributes_by_id[dimension])
        for dimension in service_graph_dimensions(registry)
    }
    mappings: dict[str, object] = {
        "_meta": {
            "schema_version": ELASTICSEARCH_MAPPING_SCHEMA_VERSION,
            "upstream_registry_lock_sha256": hashlib.sha256(upstream_lock.read_bytes()).hexdigest(),
        },
        "dynamic": "strict",
        "properties": {
            "schema_version": {"type": "keyword"},
            "event_id": {"type": "keyword"},
            "payload_hash": {"type": "keyword"},
            "id": {"type": "keyword"},
            "kind": {"type": "keyword"},
            "type": {"type": "keyword"},
            "source_id": {"type": "keyword"},
            "target_id": {"type": "keyword"},
            "attributes": {
                "dynamic": "strict",
                "subobjects": False,
                "properties": attributes,
            },
            "metrics": {
                "dynamic": "strict",
                "subobjects": False,
                "properties": {
                    GRAPH_REQUEST_FAILED_TOTAL: {"type": "double", "coerce": False},
                    GRAPH_REQUEST_TOTAL: {"type": "double", "coerce": False},
                },
            },
            "observed_at_unix_nano": {"type": "long", "coerce": False},
            "emitted_at_unix_ms": {"type": "long", "coerce": False},
        },
    }
    metadata = mappings["_meta"]
    assert isinstance(metadata, dict)
    metadata["mapping_hash"] = _mapping_hash(mappings)
    return json.dumps({"mappings": mappings}, indent=2, sort_keys=True) + "\n"


def _elasticsearch_field_mapping(attribute: AttributeDefinition) -> dict[str, object]:
    attribute_type = attribute.type
    if isinstance(attribute_type, dict) and "members" in attribute_type:
        return {"type": "keyword"}
    if attribute_type == "string":
        return {"type": "keyword"}
    if attribute_type == "int":
        return {"type": "long", "coerce": False}
    if attribute_type == "boolean":
        return {"type": "boolean"}
    if attribute_type == "double":
        return {"type": "double", "coerce": False}
    raise ValueError(f"unsupported Elasticsearch field type for {attribute.id}: {attribute_type!r}")


def _mapping_hash(mappings: dict[str, object]) -> str:
    canonical = json.dumps(mappings, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _python_type(attribute: AttributeDefinition | None) -> str:
    if attribute is None:
        return "object"
    attribute_type = attribute.type
    if isinstance(attribute_type, dict) and "members" in attribute_type:
        return "str"
    if attribute_type == "int":
        return "int"
    if attribute_type == "boolean":
        return "bool"
    if attribute_type == "string":
        return "str"
    return "object"


def _value_reader(attribute: AttributeDefinition | None) -> str:
    return {
        "bool": "bool_value",
        "int": "int_value",
        "object": "object_value",
        "str": "string_value",
    }[_python_type(attribute)]


def _domain_name(entity_name: str) -> str:
    return entity_name.split(".", maxsplit=1)[0].replace("-", "_")


def _class_name(entity_name: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[._-]+", entity_name))


def _field_name(attribute_ref: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", attribute_ref).strip("_")


def _finalize(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
