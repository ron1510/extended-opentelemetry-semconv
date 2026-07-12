from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from extended_otel_semconv.registry.model import AttributeDefinition, EntityAttributeRef, EntityDefinition  # noqa: E402
from extended_otel_semconv.registry.validation import load_model_registry, validate_extension_model  # noqa: E402

UPSTREAM_MODEL = ROOT / "upstream" / "otel-semconv" / "v1.43.0" / "model"
EXTENSION_MODEL = ROOT / "model" / "extensions"
GENERATED_DIR = ROOT / "src" / "extended_otel_semconv" / "generated"


class GeneratedEntity(NamedTuple):
    entity: EntityDefinition
    class_name: str
    domain: str
    field_refs: tuple[EntityAttributeRef, ...]
    identifying_refs: tuple[EntityAttributeRef, ...]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Python entity models from the merged OTel registry.")
    parser.add_argument("--check", action="store_true", help="Fail if generated files are not up to date.")
    args = parser.parse_args()

    files = generate_files()
    if args.check:
        return _check_files(files)
    _write_files(files)
    return 0


def generate_files() -> dict[Path, str]:
    validate_extension_model(UPSTREAM_MODEL, EXTENSION_MODEL)
    upstream = load_model_registry(UPSTREAM_MODEL)
    extension = load_model_registry(EXTENSION_MODEL)
    attributes = {**upstream.attributes_by_id, **extension.attributes_by_id}
    entities = {**upstream.entities_by_name, **extension.entities_by_name}

    generated_entities = tuple(
        _generated_entity(entity)
        for entity in sorted(entities.values(), key=lambda entity: entity.name)
        if _identifying_refs(entity)
    )
    domains = sorted({entity.domain for entity in generated_entities})

    files: dict[Path, str] = {
        GENERATED_DIR / "__init__.py": _render_package_init(generated_entities, domains),
    }
    for domain in domains:
        domain_entities = tuple(entity for entity in generated_entities if entity.domain == domain)
        files[GENERATED_DIR / f"{domain}.py"] = _render_domain_module(domain_entities, attributes)
    return files


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
    value_readers = sorted(
        {
            _value_reader(attributes.get(ref.ref))
            for entity in entities
            for ref in entity.field_refs
        }
    )
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
        blocks.append("")
        blocks.append("")
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
    lines.append(f"    for entity_class in ({class_names}):")
    lines.append("        entity = entity_class.from_attributes(attributes)")
    lines.append("        if entity is not None:")
    lines.append("            entities.append(entity)")
    lines.append("    return entities")
    return lines


def _render_package_init(entities: tuple[GeneratedEntity, ...], domains: list[str]) -> str:
    lines = [
        '"""Generated semantic entity interfaces."""',
        "",
        "from extended_otel_semconv.entities import RawAttributes, SemanticEntity",
    ]
    for domain in domains:
        domain_entities = tuple(entity for entity in entities if entity.domain == domain)
        names = ", ".join(entity.class_name for entity in domain_entities)
        lines.append(f"from extended_otel_semconv.generated.{domain} import {names}")
        lines.append(f"from extended_otel_semconv.generated.{domain} import entities_from_attributes as _{domain}_entities")
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
    lines.extend(
        [
            "    return entities",
            "",
            "",
            "__all__ = [",
        ]
    )
    for entity in entities:
        lines.append(f'    "{entity.class_name}",')
    lines.extend(
        [
            '    "SemanticEntity",',
            '    "entities_from_attributes",',
            "]",
        ]
    )
    return _finalize(lines)


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
    python_type = _python_type(attribute)
    return {
        "bool": "bool_value",
        "int": "int_value",
        "object": "object_value",
        "str": "string_value",
    }[python_type]


def _domain_name(entity_name: str) -> str:
    return entity_name.split(".", maxsplit=1)[0].replace("-", "_")


def _class_name(entity_name: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[._-]+", entity_name))


def _field_name(attribute_ref: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", attribute_ref).strip("_")


def _finalize(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"


def _write_files(files: dict[Path, str]) -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    for stale_file in GENERATED_DIR.glob("*.py"):
        if stale_file not in files:
            stale_file.unlink()
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")


def _check_files(files: dict[Path, str]) -> int:
    failed = False
    for path, expected in files.items():
        actual = path.read_text(encoding="utf-8") if path.exists() else ""
        if actual != expected:
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


if __name__ == "__main__":
    raise SystemExit(main())
