from __future__ import annotations

from extended_otel_semconv import AppEndpoint, K8sPod, Service
from extended_otel_semconv.generated import __all__ as generated_exports


def test_generated_public_api_includes_upstream_and_extension_entities() -> None:
    assert Service.entity_type == "service"
    assert K8sPod.entity_type == "k8s.pod"
    assert AppEndpoint.entity_type == "app.endpoint"


def test_entities_without_identifying_refs_are_not_generated() -> None:
    assert "Browser" not in generated_exports
    assert "Cloud" not in generated_exports
