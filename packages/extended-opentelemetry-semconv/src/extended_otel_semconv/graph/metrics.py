"""OTLP metric parsing for Collector servicegraph connector output."""

from __future__ import annotations

from typing import Literal

from google.protobuf.json_format import ParseDict, ParseError  # type: ignore[import-untyped]
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.metrics.v1.metrics_pb2 import AggregationTemporality, Metric, NumberDataPoint
from pydantic import BaseModel, ConfigDict, Field

from extended_otel_semconv.graph.otlp import key_values_to_attributes

SERVICE_GRAPH_REQUEST_TOTAL = "traces_service_graph_request_total"
SERVICE_GRAPH_REQUEST_FAILED_TOTAL = "traces_service_graph_request_failed_total"

type MetricTemporality = Literal["delta", "cumulative"]
type MetricValue = int | float


class MetricPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    attributes: dict[str, str | bool | int | float] = Field(default_factory=dict)
    value: MetricValue
    observed_at_unix_nano: int | None = Field(default=None, gt=0)
    start_time_unix_nano: int | None = Field(default=None, gt=0)
    temporality: MetricTemporality = "cumulative"


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
