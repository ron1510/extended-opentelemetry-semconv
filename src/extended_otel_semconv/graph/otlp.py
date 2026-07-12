from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Span

from extended_otel_semconv.entities import RawAttributes


@dataclass(frozen=True)
class SpanRecord:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    kind: int
    attributes: dict[str, object]

    @property
    def is_server(self) -> bool:
        return self.kind == Span.SPAN_KIND_SERVER


def parse_trace_request(body: bytes) -> list[SpanRecord]:
    request = ExportTraceServiceRequest()
    request.ParseFromString(body)
    return list(iter_span_records(request))


def iter_span_records(request: ExportTraceServiceRequest) -> Iterable[SpanRecord]:
    for resource_spans in request.resource_spans:
        resource_attributes = key_values_to_attributes(resource_spans.resource.attributes)
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                span_attributes = {**resource_attributes, **key_values_to_attributes(span.attributes)}
                yield SpanRecord(
                    trace_id=span.trace_id.hex(),
                    span_id=span.span_id.hex(),
                    parent_span_id=span.parent_span_id.hex() or None,
                    kind=span.kind,
                    attributes=span_attributes,
                )


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


def span_key(trace_id: str, span_id: str) -> str:
    return f"{trace_id}:{span_id}"


def raw_attributes(record: SpanRecord) -> RawAttributes:
    return record.attributes
