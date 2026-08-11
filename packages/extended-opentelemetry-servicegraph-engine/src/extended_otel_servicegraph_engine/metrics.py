"""Neutral metric contracts consumed by the lifecycle engine."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SERVICE_GRAPH_REQUEST_TOTAL = "traces_service_graph_request_total"
SERVICE_GRAPH_REQUEST_FAILED_TOTAL = "traces_service_graph_request_failed_total"
SERVICE_GRAPH_METRIC_PREFIX = "traces_service_graph_"
SUPPORTED_SERVICE_GRAPH_METRICS = frozenset(
    {SERVICE_GRAPH_REQUEST_TOTAL, SERVICE_GRAPH_REQUEST_FAILED_TOTAL}
)

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
