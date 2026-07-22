"""Read service graph datapoint logs from OTLP JSON exported by the Collector."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def iter_service_graph_log_records(
    document: dict[str, Any],
) -> Iterable[tuple[str, dict[str, object], int | float, int | None]]:
    for resource_log in document.get("resourceLogs", []):
        if not isinstance(resource_log, dict):
            continue
        for scope_log in resource_log.get("scopeLogs", []):
            if not isinstance(scope_log, dict):
                continue
            for record in scope_log.get("logRecords", []):
                if not isinstance(record, dict):
                    continue
                parsed = _parse_log_record(record)
                if parsed is not None:
                    yield parsed


def _parse_log_record(record: dict[str, Any]) -> tuple[str, dict[str, object], int | float, int | None] | None:
    attributes = _attributes(record.get("attributes", []))
    body = _any_value(record.get("body", {}))
    metric_name = _metric_name(body, attributes)
    metric_value = _metric_value(body)
    if metric_name is None or metric_value is None:
        return None
    return metric_name, attributes, metric_value, _int_or_none(record.get("timeUnixNano"))


def _metric_name(body: object, attributes: dict[str, object]) -> str | None:
    value = attributes.get("metric.name")
    if isinstance(value, str):
        return value
    if isinstance(body, dict):
        for key in ("metric.name", "name"):
            value = body.get(key)
            if isinstance(value, str):
                return value
    return None


def _metric_value(body: object) -> int | float | None:
    if isinstance(body, int | float):
        return body
    if isinstance(body, dict):
        for key in ("value", "asInt", "asDouble"):
            value = body.get(key)
            if isinstance(value, int | float):
                return value
            if isinstance(value, str):
                parsed = _int_or_float(value)
                if parsed is not None:
                    return parsed
    return None


def _attributes(items: object) -> dict[str, object]:
    if not isinstance(items, list):
        return {}
    attributes: dict[str, object] = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("key"), str):
            attributes[item["key"]] = _any_value(item.get("value", {}))
    return attributes


def _any_value(value: object) -> object:
    if not isinstance(value, dict):
        return value
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in value:
            return value[key]
    if "kvlistValue" in value and isinstance(value["kvlistValue"], dict):
        return _attributes(value["kvlistValue"].get("values", []))
    return value


def _int_or_float(value: str) -> int | float | None:
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
