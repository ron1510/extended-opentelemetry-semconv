from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from extended_otel_semconv import AppEndpoint, K8sPod, Service
from extended_otel_semconv.generated import __all__ as generated_exports

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SOURCE = PACKAGE_ROOT / "src"


def test_generated_public_api_includes_upstream_and_extension_entities() -> None:
    assert Service.entity_type == "service"
    assert K8sPod.entity_type == "k8s.pod"
    assert AppEndpoint.entity_type == "app.endpoint"


def test_entities_without_identifying_refs_are_not_generated() -> None:
    assert "Browser" not in generated_exports
    assert "Cloud" not in generated_exports


def test_generated_files_are_current() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "extended_otel_semconv.codegen", "--check"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(PACKAGE_SOURCE)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
