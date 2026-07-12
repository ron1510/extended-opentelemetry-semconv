"""Live entity graph built from OpenTelemetry traces."""

from extended_otel_semconv.graph.app import create_app
from extended_otel_semconv.graph.store import EntityGraph

__all__ = ["EntityGraph", "create_app"]
