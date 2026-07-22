"""Application semantic entity interfaces."""

from extended_otel_semconv.generated.app import App, AppEndpoint
from extended_otel_semconv.generated.app import entities_from_attributes as app_entities_from_attributes

__all__ = [
    "App",
    "AppEndpoint",
    "app_entities_from_attributes",
]
