"""Build the strict semantic entity IR and its JSON Schema representation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum

from tools.semconv_codegen.registry.model import (
    AttributeDefinition,
    EntityDefinition,
    EnumAttributeType,
)

type EnumValue = str | int | float | bool
type JsonSchema = dict[str, object]


class SemanticFieldKind(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    STRING_ARRAY = "string_array"
    INTEGER_ARRAY = "integer_array"
    NUMBER_ARRAY = "number_array"
    BOOLEAN_ARRAY = "boolean_array"
    STRING_MAP = "string_map"
    INTEGER_MAP = "integer_map"
    NUMBER_MAP = "number_map"
    BOOLEAN_MAP = "boolean_map"
    STRING_ARRAY_MAP = "string_array_map"
    INTEGER_ARRAY_MAP = "integer_array_map"
    NUMBER_ARRAY_MAP = "number_array_map"
    BOOLEAN_ARRAY_MAP = "boolean_array_map"
    ENUM = "enum"


@dataclass(frozen=True, slots=True)
class SemanticField:
    canonical_name: str
    python_name: str
    kind: SemanticFieldKind
    required: bool
    description: str | None
    enum_values: tuple[EnumValue, ...] = ()

    @property
    def is_template(self) -> bool:
        return self.kind.value.endswith("_map")


@dataclass(frozen=True, slots=True)
class SemanticModel:
    semantic_type: str
    class_name: str
    fields_class_name: str
    fields: tuple[SemanticField, ...]
    identity_fields: tuple[str, ...]

    @property
    def template_fields(self) -> tuple[str, ...]:
        return tuple(field.canonical_name for field in self.fields if field.is_template)


def build_semantic_models(
    entities: tuple[EntityDefinition, ...],
    attributes: dict[str, AttributeDefinition],
) -> tuple[SemanticModel, ...]:
    models: list[SemanticModel] = []
    for entity in entities:
        identity_fields = tuple(ref.ref for ref in entity.attributes if ref.role == "identifying")
        if not identity_fields:
            continue
        fields: list[SemanticField] = []
        for ref in entity.attributes:
            attribute = attributes.get(ref.ref)
            if attribute is None:
                raise ValueError(f"entity {entity.name!r} references unknown attribute {ref.ref!r}")
            fields.append(
                SemanticField(
                    canonical_name=ref.ref,
                    python_name=python_field_name(ref.ref),
                    kind=_field_kind(attribute),
                    required=ref.role == "identifying",
                    description=attribute.brief,
                    enum_values=_enum_values(attribute),
                )
            )
        class_name = python_class_name(entity.name)
        models.append(
            SemanticModel(
                semantic_type=entity.name,
                class_name=class_name,
                fields_class_name=f"{class_name}Fields",
                fields=tuple(fields),
                identity_fields=identity_fields,
            )
        )
    return tuple(sorted(models, key=lambda model: model.semantic_type))


def render_semantic_schema(models: tuple[SemanticModel, ...]) -> str:
    definitions: dict[str, object] = {}
    for model in models:
        properties = {field.canonical_name: _field_schema(field) for field in model.fields}
        definitions[model.fields_class_name] = {
            "type": "object",
            "title": model.fields_class_name,
            "additionalProperties": False,
            "properties": properties,
            "required": list(model.identity_fields),
            "x-semantic-type": model.semantic_type,
            "x-identity-fields": list(model.identity_fields),
            "x-template-fields": list(model.template_fields),
        }
    schema: JsonSchema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://extended-opentelemetry-semconv.dev/schema/semantic-entities.json",
        "title": "GeneratedSemanticEntityFields",
        "oneOf": [{"$ref": f"#/$defs/{model.fields_class_name}"} for model in models],
        "$defs": definitions,
    }
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def python_class_name(value: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[._-]+", value))


def python_field_name(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", value).strip("_")


def _field_kind(attribute: AttributeDefinition) -> SemanticFieldKind:
    attribute_type = attribute.type
    if isinstance(attribute_type, EnumAttributeType):
        return SemanticFieldKind.ENUM
    try:
        return {
            "string": SemanticFieldKind.STRING,
            "int": SemanticFieldKind.INTEGER,
            "double": SemanticFieldKind.NUMBER,
            "boolean": SemanticFieldKind.BOOLEAN,
            "string[]": SemanticFieldKind.STRING_ARRAY,
            "int[]": SemanticFieldKind.INTEGER_ARRAY,
            "double[]": SemanticFieldKind.NUMBER_ARRAY,
            "boolean[]": SemanticFieldKind.BOOLEAN_ARRAY,
            "template[string]": SemanticFieldKind.STRING_MAP,
            "template[int]": SemanticFieldKind.INTEGER_MAP,
            "template[double]": SemanticFieldKind.NUMBER_MAP,
            "template[boolean]": SemanticFieldKind.BOOLEAN_MAP,
            "template[string[]]": SemanticFieldKind.STRING_ARRAY_MAP,
            "template[int[]]": SemanticFieldKind.INTEGER_ARRAY_MAP,
            "template[double[]]": SemanticFieldKind.NUMBER_ARRAY_MAP,
            "template[boolean[]]": SemanticFieldKind.BOOLEAN_ARRAY_MAP,
        }[attribute_type]
    except KeyError as error:
        raise ValueError(f"unsupported generated attribute type {attribute_type!r} for {attribute.id!r}") from error


def _enum_values(attribute: AttributeDefinition) -> tuple[EnumValue, ...]:
    if not isinstance(attribute.type, EnumAttributeType):
        return ()
    values = tuple(member.value for member in attribute.type.members)
    if not values:
        raise ValueError(f"enum attribute {attribute.id!r} has no members")
    value_types = {type(value) for value in values}
    if len(value_types) != 1:
        raise ValueError(f"enum attribute {attribute.id!r} mixes value types")
    return values


def _field_schema(field: SemanticField) -> JsonSchema:
    if field.kind is SemanticFieldKind.ENUM:
        schema: JsonSchema = {"enum": list(field.enum_values), "type": _json_type(field.enum_values[0])}
    elif field.kind in {
        SemanticFieldKind.STRING_ARRAY,
        SemanticFieldKind.INTEGER_ARRAY,
        SemanticFieldKind.NUMBER_ARRAY,
        SemanticFieldKind.BOOLEAN_ARRAY,
    }:
        item_kind = field.kind.value.removesuffix("_array")
        schema = {"type": "array", "items": {"type": _scalar_json_type(item_kind)}}
    elif field.is_template:
        value_kind = field.kind.value.removesuffix("_map")
        if value_kind.endswith("_array"):
            item_kind = value_kind.removesuffix("_array")
            value_schema: JsonSchema = {
                "type": "array",
                "items": {"type": _scalar_json_type(item_kind)},
            }
        else:
            value_schema = {"type": _scalar_json_type(value_kind)}
        schema = {"type": "object", "additionalProperties": value_schema}
    else:
        schema = {"type": _scalar_json_type(field.kind.value)}
    if field.required and schema.get("type") == "string":
        schema["minLength"] = 1
    if field.description:
        schema["description"] = field.description.strip()
    return schema


def _scalar_json_type(kind: str) -> str:
    return {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
    }[kind]


def _json_type(value: EnumValue) -> str:
    match value:
        case bool():
            return "boolean"
        case int():
            return "integer"
        case float():
            return "number"
        case str():
            return "string"
