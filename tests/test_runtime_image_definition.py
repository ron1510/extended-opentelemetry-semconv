from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "apps" / "otel-servicegraph-diff" / "Dockerfile"
SERIALIZER_POM = ROOT / "apps" / "otel-servicegraph-diff" / "runtime" / "java" / "pom.xml"


def test_deployable_image_does_not_require_root_or_a_fixed_uid() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "USER root" not in dockerfile
    assert "USER 1001" not in dockerfile
    assert "USER flink" in dockerfile
    assert "--chown=flink:0" in dockerfile
    assert "--chmod=0660" in dockerfile
    assert "PYFLINK_CLIENT_EXECUTABLE=/usr/local/bin/python3.12" in dockerfile
    assert "/layout/opt/application" in dockerfile


def test_runtime_targets_java_11_and_uses_package_metadata_for_dependencies() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    serializer_pom = SERIALIZER_POM.read_text(encoding="utf-8")

    assert "maven:3.9.11-eclipse-temurin-11" in dockerfile
    assert "flink:2.2.1-scala_2.12-java11" in dockerfile
    assert "<maven.compiler.release>11</maven.compiler.release>" in serializer_pom
    assert "java17" not in dockerfile
    assert "requirements.lock" not in dockerfile
    assert not (ROOT / "requirements.lock").exists()
