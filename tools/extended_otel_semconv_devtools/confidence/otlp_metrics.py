"""Typed builders for deterministic OTLP JSON metric fixtures."""

# Protobuf's generated stubs partially erase repeated-field member types. This
# file is the single fixture-construction boundary for that unsoundness.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from typing import Literal

from google.protobuf.json_format import MessageToJson  # type: ignore[import-untyped]
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.metrics.v1.metrics_pb2 import AggregationTemporality, Metric
from pydantic import BaseModel, ConfigDict, Field

from extended_otel_semconv.graph.interaction import TelemetryScalar


class MetricSample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    attributes: dict[str, TelemetryScalar]
    value: int | float
    observed_at_unix_nano: int | None = Field(default=None, gt=0)
    start_time_unix_nano: int | None = Field(default=None, gt=0)
    temporality: Literal["delta", "cumulative"] = "cumulative"


def metrics_json(samples: tuple[MetricSample, ...]) -> str:
    request = ExportMetricsServiceRequest()
    scope_metrics = request.resource_metrics.add().scope_metrics.add()
    metrics_by_contract: dict[tuple[str, str], Metric] = {}
    for sample in samples:
        contract = (sample.name, sample.temporality)
        metric = metrics_by_contract.get(contract)
        if metric is None:
            metric = scope_metrics.metrics.add()
            metric.name = sample.name
            metric.sum.is_monotonic = True
            metric.sum.aggregation_temporality = (
                AggregationTemporality.AGGREGATION_TEMPORALITY_CUMULATIVE
                if sample.temporality == "cumulative"
                else AggregationTemporality.AGGREGATION_TEMPORALITY_DELTA
            )
            metrics_by_contract[contract] = metric
        point = metric.sum.data_points.add()
        if isinstance(sample.value, int):
            point.as_int = sample.value
        else:
            point.as_double = sample.value
        if sample.observed_at_unix_nano is not None:
            point.time_unix_nano = sample.observed_at_unix_nano
        if sample.start_time_unix_nano is not None:
            point.start_time_unix_nano = sample.start_time_unix_nano
        for key, value in sample.attributes.items():
            attribute = point.attributes.add()
            attribute.key = key
            if isinstance(value, bool):
                attribute.value.bool_value = value
            elif isinstance(value, int):
                attribute.value.int_value = value
            elif isinstance(value, float):
                attribute.value.double_value = value
            else:
                attribute.value.string_value = value
    return MessageToJson(request)
