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
    kind = value.WhichOneof("value")
    if kind is None:
        return None
    if kind == "string_value":
        return value.string_value
    if kind == "bool_value":
        return value.bool_value
    if kind == "int_value":
        return value.int_value
    if kind == "double_value":
        return value.double_value
    if kind == "bytes_value":
        return value.bytes_value
    if kind == "array_value":
        return [any_value_to_python(item) for item in value.array_value.values]
    if kind == "kvlist_value":
        return key_values_to_attributes(value.kvlist_value.values)
    return None
