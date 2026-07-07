from __future__ import annotations

from extended_otel_semconv.upstream.package_source import inspect_semconv_package


def test_installed_otel_semconv_package_is_visible() -> None:
    inspection = inspect_semconv_package()

    assert inspection.package == "opentelemetry-semantic-conventions"
    assert inspection.version
    assert inspection.exposes_model_yaml is False
