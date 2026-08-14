"""Runtime primitives shared by generated semantic entity classes."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, ClassVar, Self, cast
from urllib.parse import quote

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    FiniteFloat,
    PlainSerializer,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
    computed_field,
    model_validator,
)

from extended_otel_semconv.errors import (
    SemanticIdentityMismatchError,
    SemanticModelValidationError,
    UnknownSemanticTypeError,
)

type EntityId = str
type SemanticScalar = StrictStr | StrictInt | StrictFloat | StrictBool
type SemanticSequence = tuple[SemanticScalar, ...]
type SemanticAttributeValue = SemanticScalar | SemanticSequence
type RawAttributes = Mapping[str, object]

def _as_tuple(value: object) -> object:
    return tuple(cast(list[object], value)) if isinstance(value, list) else value


def _freeze_mapping[Value](value: Mapping[str, Value]) -> Mapping[str, Value]:
    return MappingProxyType(dict(value))


def _serialize_mapping[Value](value: Mapping[str, Value]) -> dict[str, Value]:
    return dict(value)


type StringSequence = Annotated[tuple[StrictStr, ...], BeforeValidator(_as_tuple)]
type IntegerSequence = Annotated[tuple[StrictInt, ...], BeforeValidator(_as_tuple)]
type NumberSequence = Annotated[tuple[FiniteFloat, ...], BeforeValidator(_as_tuple)]
type BooleanSequence = Annotated[tuple[StrictBool, ...], BeforeValidator(_as_tuple)]

type FrozenStringMap = Annotated[
    Mapping[str, StrictStr],
    AfterValidator(_freeze_mapping),
    PlainSerializer(_serialize_mapping),
]
type FrozenIntegerMap = Annotated[
    Mapping[str, StrictInt],
    AfterValidator(_freeze_mapping),
    PlainSerializer(_serialize_mapping),
]
type FrozenNumberMap = Annotated[
    Mapping[str, FiniteFloat],
    AfterValidator(_freeze_mapping),
    PlainSerializer(_serialize_mapping),
]
type FrozenBooleanMap = Annotated[
    Mapping[str, StrictBool],
    AfterValidator(_freeze_mapping),
    PlainSerializer(_serialize_mapping),
]
type FrozenStringSequenceMap = Annotated[
    Mapping[str, StringSequence],
    AfterValidator(_freeze_mapping),
    PlainSerializer(_serialize_mapping),
]
type FrozenIntegerSequenceMap = Annotated[
    Mapping[str, IntegerSequence],
    AfterValidator(_freeze_mapping),
    PlainSerializer(_serialize_mapping),
]
type FrozenNumberSequenceMap = Annotated[
    Mapping[str, NumberSequence],
    AfterValidator(_freeze_mapping),
    PlainSerializer(_serialize_mapping),
]
type FrozenBooleanSequenceMap = Annotated[
    Mapping[str, BooleanSequence],
    AfterValidator(_freeze_mapping),
    PlainSerializer(_serialize_mapping),
]


def quoted_entity_id(entity_type: str, *parts: object) -> EntityId:
    if not entity_type or not parts or any(part == "" for part in parts):
        raise ValueError("semantic entity IDs require a type and non-empty identity values")
    encoded_parts = (quote(str(part), safe="") for part in parts)
    return ":".join((entity_type, *encoded_parts))


class SemanticEntity(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )

    entity_type: ClassVar[str]
    identity_fields: ClassVar[tuple[str, ...]]
    template_fields: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def freeze_containers(self) -> Self:
        for field_name in type(self).model_fields:
            object.__setattr__(self, field_name, _freeze_value(getattr(self, field_name)))
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> EntityId:
        values = tuple(getattr(self, self._python_field_name(alias)) for alias in self.identity_fields)
        return quoted_entity_id(self.entity_type, *values)

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        if any(field not in attributes for field in cls.identity_fields):
            return None
        values: dict[str, object] = {}
        for field_name, field in cls.model_fields.items():
            alias = field.alias or field_name
            if alias in cls.template_fields:
                template_values = _template_values(attributes, alias)
                if template_values:
                    values[alias] = template_values
            elif alias in attributes:
                values[alias] = attributes[alias]
        try:
            return cls.model_validate(values)
        except ValidationError as error:
            raise SemanticModelValidationError(f"invalid {cls.__name__} attributes: {error}") from error

    def semantic_attributes(self) -> dict[str, object]:
        attributes: dict[str, object] = {}
        for field_name, field in type(self).model_fields.items():
            value = getattr(self, field_name)
            if value is None:
                continue
            alias = field.alias or field_name
            if alias in self.template_fields:
                for suffix, template_value in value.items():
                    attributes[f"{alias}.{suffix}"] = template_value
            else:
                attributes[alias] = value
        return attributes

    @classmethod
    def _python_field_name(cls, alias: str) -> str:
        for field_name, field in cls.model_fields.items():
            if field.alias == alias:
                return field_name
        raise SemanticModelValidationError(f"{cls.__name__} has no generated field for {alias!r}")


def entity_from_attributes(
    entity_type: str,
    attributes: RawAttributes,
    *,
    expected_id: str | None = None,
) -> SemanticEntity:
    from extended_otel_semconv.generated import ENTITY_MODELS

    model = ENTITY_MODELS.get(entity_type)
    if model is None:
        raise UnknownSemanticTypeError(f"no generated semantic entity model for {entity_type!r}")
    entity = model.from_attributes(attributes)
    if entity is None:
        raise SemanticModelValidationError(
            f"attributes do not contain the identifying fields required by {model.__name__}"
        )
    if expected_id is not None and entity.entity_id != expected_id:
        raise SemanticIdentityMismatchError(
            f"stored entity ID {expected_id!r} does not match reconstructed ID {entity.entity_id!r}"
        )
    return entity


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    from extended_otel_semconv.generated import entities_from_attributes as generated_entities_from_attributes

    return generated_entities_from_attributes(attributes)


def _template_values(attributes: RawAttributes, prefix: str) -> dict[str, object]:
    dotted_prefix = f"{prefix}."
    return {
        key.removeprefix(dotted_prefix): value
        for key, value in attributes.items()
        if key.startswith(dotted_prefix) and key != dotted_prefix
    }


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return MappingProxyType({str(key): _freeze_value(item) for key, item in mapping.items()})
    if isinstance(value, list | tuple):
        sequence = cast(list[object] | tuple[object, ...], value)
        return tuple(_freeze_value(item) for item in sequence)
    return value
