"""Collector service-graph metric ingestion."""

from otel_servicegraph_diff.ingest.interaction import (
    observation_from_metric_point,
    observation_from_servicegraph_datapoint,
)

__all__ = ["observation_from_metric_point", "observation_from_servicegraph_datapoint"]
