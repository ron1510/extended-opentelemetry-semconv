"""OTLP metric parsing for Collector servicegraph connector output."""

from __future__ import annotations

from google.protobuf.json_format import ParseDict, ParseError  # type: ignore[import-untyped]
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.metrics.v1.metrics_pb2 import AggregationTemporality, Metric, NumberDataPoint
from pydantic import BaseModel, ConfigDict

from otel_servicegraph_diff.engine.metrics import (
    SERVICE_GRAPH_METRIC_PREFIX,
    SUPPORTED_SERVICE_GRAPH_METRICS,
    MetricPoint,
    MetricTemporality,
    MetricValue,
)
from otel_servicegraph_diff.ingest.otlp import key_values_to_attributes


class ParsedMetricsDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    points: tuple[MetricPoint, ...]
    metric_names: frozenset[str]


def parse_metrics_request(body: bytes) -> list[MetricPoint]:
    request = ExportMetricsServiceRequest()
    request.ParseFromString(body)
    return metric_points_from_request(request)


def parse_metrics_json_document(document: dict[str, object]) -> list[MetricPoint]:
    return list(parse_metrics_json_document_with_names(document).points)


def parse_metrics_json_document_with_names(document: dict[str, object]) -> ParsedMetricsDocument:
    try:
        request = ParseDict(document, ExportMetricsServiceRequest(), ignore_unknown_fields=True)
    except ParseError as exc:
        raise ValueError(str(exc)) from exc
    return ParsedMetricsDocument(
        points=tuple(metric_points_from_request(request)),
        metric_names=frozenset(_metric_names(request)),
    )


def contains_only_ignored_service_graph_metrics(metric_names: frozenset[str]) -> bool:
    return bool(metric_names) and all(
        name.startswith(SERVICE_GRAPH_METRIC_PREFIX) and name not in SUPPORTED_SERVICE_GRAPH_METRICS
        for name in metric_names
    )


def metric_points_from_request(request: ExportMetricsServiceRequest) -> list[MetricPoint]:
    points: list[MetricPoint] = []
    for resource_metrics in request.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                points.extend(_metric_points(metric))
    return points


def _metric_points(metric: Metric) -> list[MetricPoint]:
    if metric.name not in SUPPORTED_SERVICE_GRAPH_METRICS:
        return []
    if metric.WhichOneof("data") != "sum":
        return []
    temporality = _temporality(metric.sum.aggregation_temporality)
    if temporality is None:
        return []
    points: list[MetricPoint] = []
    for point in metric.sum.data_points:
        attributes = key_values_to_attributes(point.attributes)
        scalar_attributes = {
            key: value
            for key, value in attributes.items()
            if isinstance(value, str | bool | int | float)
        }
        points.append(
            MetricPoint(
                name=metric.name,
                attributes=scalar_attributes,
                value=_number_value(point),
                observed_at_unix_nano=point.time_unix_nano or None,
                start_time_unix_nano=point.start_time_unix_nano or None,
                temporality=temporality,
            )
        )
    return points


def _temporality(value: int) -> MetricTemporality | None:
    if value == AggregationTemporality.AGGREGATION_TEMPORALITY_DELTA:
        return "delta"
    if value == AggregationTemporality.AGGREGATION_TEMPORALITY_CUMULATIVE:
        return "cumulative"
    return None


def _number_value(point: NumberDataPoint) -> MetricValue:
    value_kind = point.WhichOneof("value")
    if value_kind == "as_int":
        return point.as_int
    if value_kind == "as_double":
        return point.as_double
    raise ValueError("servicegraph number datapoint has no numeric value")


def _metric_names(request: ExportMetricsServiceRequest) -> set[str]:
    return {
        metric.name
        for resource_metrics in request.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
        if metric.name
    }
