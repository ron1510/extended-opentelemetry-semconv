"""OTLP value conversion used by Collector metric parsing."""

from __future__ import annotations

from collections.abc import Iterable

from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue


def key_values_to_attributes(values: Iterable[KeyValue]) -> dict[str, object]:
    attributes: dict[str, object] = {}
    for item in values:
        value = any_value_to_python(item.value)
        if value is not None:
            attributes[item.key] = value
    return attributes


def any_value_to_python(value: AnyValue) -> object | None:
    match value.WhichOneof("value"):
        case "string_value":
            return value.string_value
        case "bool_value":
            return value.bool_value
        case "int_value":
            return value.int_value
        case "double_value":
            return value.double_value
        case "bytes_value":
            return value.bytes_value
        case "array_value":
            return [any_value_to_python(item) for item in value.array_value.values]
        case "kvlist_value":
            return key_values_to_attributes(value.kvlist_value.values)
        case _:
            return None
