from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_COMPOSE = ROOT / "docker-compose.acceptance.yaml"
FLINK_SERVICES = ("flink-jobmanager", "flink-taskmanager", "interaction-diff")


def test_acceptance_flink_processes_use_runtime_image_and_wheels_only() -> None:
    document = yaml.safe_load(ACCEPTANCE_COMPOSE.read_text(encoding="utf-8"))
    services = document["services"]

    for service_name in FLINK_SERVICES:
        service = services[service_name]
        assert service["image"] == "extended-otel-flink-runtime:2.2.1-java11"
        assert service["environment"]["PYTHONPATH"] == "/opt/application"
        assert "flink-application:/opt/application:ro" in service["volumes"]
        assert all("workspace" not in volume for volume in service["volumes"])

    command = services["interaction-diff"]["command"]
    assert "/opt/application/otel_servicegraph_diff/cli.py" in command
    assert all("workspace" not in argument for argument in command)
    assert services["interaction-diff"]["environment"]["PYTHONPATH"] == "/opt/application"


def test_acceptance_installs_built_wheels_without_dependencies_or_editable_mode() -> None:
    document = yaml.safe_load(ACCEPTANCE_COMPOSE.read_text(encoding="utf-8"))
    installer = document["services"]["wheel-installer"]
    command = installer["command"][0]

    assert "pip install --no-deps" in command
    assert "--target /opt/application" in command
    assert "*.whl" in command
    assert "--editable" not in command
    assert "-e " not in command
