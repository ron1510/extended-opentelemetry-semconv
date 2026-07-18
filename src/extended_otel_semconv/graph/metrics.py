"""OTLP metric parsing for Collector service graph connector output."""

from __future__ import annotations

from dataclasses import dataclass

from google.protobuf.json_format import ParseDict, ParseError  # type: ignore[import-untyped]
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.metrics.v1.metrics_pb2 import Metric, NumberDataPoint

from extended_otel_semconv.graph.otlp import key_values_to_attributes

SERVICE_GRAPH_REQUEST_TOTAL = "traces_service_graph_request_total"
SERVICE_GRAPH_REQUEST_FAILED_TOTAL = "traces_service_graph_request_failed_total"


@dataclass(frozen=True)
class MetricPoint:
    name: str
    attributes: dict[str, object]
    value: int | float
    observed_at_unix_nano: int | None = None


def parse_metrics_request(body: bytes) -> list[MetricPoint]:
    request = ExportMetricsServiceRequest()
    request.ParseFromString(body)
    return metric_points_from_request(request)


def parse_metrics_json_document(document: dict[str, object]) -> list[MetricPoint]:
    try:
        request = ParseDict(document, ExportMetricsServiceRequest(), ignore_unknown_fields=True)
    except ParseError as exc:
        raise ValueError(str(exc)) from exc
    return metric_points_from_request(request)


def metric_points_from_request(request: ExportMetricsServiceRequest) -> list[MetricPoint]:
    points: list[MetricPoint] = []
    for resource_metrics in request.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                points.extend(_metric_points(metric))
    return points


def _metric_points(metric: Metric) -> list[MetricPoint]:
    if metric.name not in {SERVICE_GRAPH_REQUEST_TOTAL, SERVICE_GRAPH_REQUEST_FAILED_TOTAL}:
        return []
    data = metric.WhichOneof("data")
    if data != "sum":
        return []
    return [
        MetricPoint(
            name=metric.name,
            attributes=key_values_to_attributes(point.attributes),
            value=_number_value(point),
            observed_at_unix_nano=point.time_unix_nano or None,
        )
        for point in metric.sum.data_points
    ]


def _number_value(point: NumberDataPoint) -> int | float:
    value_kind = point.WhichOneof("value")
    if value_kind == "as_int":
        return point.as_int
    if value_kind == "as_double":
        return point.as_double
    return 0
