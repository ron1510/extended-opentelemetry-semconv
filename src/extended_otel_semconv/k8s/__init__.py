"""Kubernetes semantic entity interfaces."""

from extended_otel_semconv.k8s.entities import (
    K8sCluster,
    K8sContainer,
    K8sNamespace,
    K8sNode,
    K8sPod,
    SemanticEntity,
    entities_from_attributes,
)

__all__ = [
    "K8sCluster",
    "K8sContainer",
    "K8sNamespace",
    "K8sNode",
    "K8sPod",
    "SemanticEntity",
    "entities_from_attributes",
]
