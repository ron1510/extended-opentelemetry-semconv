"""Typed Gremlin access for extended semantic models."""

from extended_otel_semconv.gremlin.client import (
    InvalidSemanticQueryError,
    SemanticGraphElement,
    SemanticGremlinClient,
    SemanticGremlinError,
    SemanticGremlinQueryError,
    SemanticGremlinResultError,
    UnsupportedSemanticTraversalError,
)

__all__ = [
    "InvalidSemanticQueryError",
    "SemanticGraphElement",
    "SemanticGremlinClient",
    "SemanticGremlinError",
    "SemanticGremlinQueryError",
    "SemanticGremlinResultError",
    "UnsupportedSemanticTraversalError",
]
