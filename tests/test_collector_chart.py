from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "deploy" / "helm" / "servicegraph-collector"


def _yaml(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8")))


def test_chart_defaults_fix_the_servicegraph_hash_ring_at_two_backends() -> None:
    values = _yaml(CHART / "values.yaml")
    schema = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))

    assert values["router"]["replicaCount"] == 2
    assert values["backend"]["replicaCount"] == 2
    backend_replicas = schema["properties"]["backend"]["properties"]["replicaCount"]
    assert backend_replicas == {"type": "integer", "minimum": 2, "maximum": 2}


def test_chart_reserves_dns_label_space_for_stateful_backend_suffixes() -> None:
    helpers = (CHART / "templates" / "_helpers.tpl").read_text(encoding="utf-8")
    schema = json.loads((CHART / "values.schema.json").read_text(encoding="utf-8"))

    assert helpers.count("trunc 40") == 2
    assert schema["properties"]["fullnameOverride"]["maxLength"] == 40


def test_router_uses_trace_id_and_stable_statefulset_ordinal_dns() -> None:
    router = (CHART / "templates" / "router-configmap.yaml").read_text(encoding="utf-8")

    assert "routing_key: traceID" in router
    assert "resolver:\n          static:" in router
    assert "-backend-{{ $ordinal }}" in router
    assert "-backend-headless" in router
    assert ".svc:4317" in router


def test_headless_service_and_backend_statefulset_share_a_governing_service() -> None:
    service = (CHART / "templates" / "backend-service.yaml").read_text(encoding="utf-8")
    statefulset = (CHART / "templates" / "backend-statefulset.yaml").read_text(encoding="utf-8")

    assert "clusterIP: None" in service
    assert "publishNotReadyAddresses: true" in service
    assert "kind: StatefulSet" in statefulset
    assert "serviceName: {{ include \"servicegraph-collector.fullname\" . }}-backend-headless" in statefulset
    assert "volumeClaimTemplates:" in statefulset
    assert "automountServiceAccountToken: false" in statefulset


def test_chart_is_namespace_scoped_and_openshift_arbitrary_uid_safe() -> None:
    templates = "\n".join(path.read_text(encoding="utf-8") for path in (CHART / "templates").rglob("*.yaml"))

    assert "kind: ClusterRole" not in templates
    assert "kind: ClusterRoleBinding" not in templates
    assert "kind: CustomResourceDefinition" not in templates
    assert "runAsUser:" not in templates
    assert "allowPrivilegeEscalation: false" in templates
    assert "readOnlyRootFilesystem: true" in templates


def test_generated_dimensions_are_shared_by_local_and_helm_backends() -> None:
    dimensions = _yaml(CHART / "files" / "dimensions.yaml")["dimensions"]
    local_backend = _yaml(ROOT / "deploy" / "local" / "otelcol-backend.yaml")
    local_dimensions = local_backend["connectors"]["service_graph"]["dimensions"]

    assert dimensions
    assert dimensions == local_dimensions
    assert not any(str(name).endswith((".label", ".annotation", ".selector")) for name in dimensions)


def test_persistent_queue_compaction_stays_on_the_mounted_volume() -> None:
    backend = (CHART / "templates" / "backend-configmap.yaml").read_text(encoding="utf-8")
    openshift = _yaml(ROOT / "deploy" / "openshift" / "otelcol.yaml")
    expected = (
        "compaction:\n"
        "          on_start: true\n"
        "          on_rebound: false\n"
        "          directory: /var/lib/otelcol/queue"
    )

    assert expected in backend
    assert openshift["extensions"]["file_storage/queue"]["compaction"]["directory"] == "/var/lib/otelcol/queue"


def test_local_compose_exercises_router_and_two_backends() -> None:
    compose = _yaml(ROOT / "docker-compose.yaml")
    services = compose["services"]

    assert services["otelcol"]["volumes"] == ["./deploy/local/otelcol.yaml:/etc/otelcol/config.yaml:ro"]
    assert services["otelcol"]["depends_on"].keys() == {"otelcol-backend-0", "otelcol-backend-1"}
    assert services["otelcol-backend-0"]["volumes"] == [
        "./deploy/local/otelcol-backend.yaml:/etc/otelcol/config.yaml:ro"
    ]
    assert services["otelcol-backend-1"]["volumes"] == [
        "./deploy/local/otelcol-backend.yaml:/etc/otelcol/config.yaml:ro"
    ]


def test_shared_stream_contract_matches_chart_and_runtime_topics() -> None:
    contract = _yaml(ROOT / "deploy" / "contracts" / "servicegraph-stream.values.yaml")["streamContract"]
    values = _yaml(CHART / "values.yaml")["streamContract"]

    assert contract == values
    assert contract["topics"] == {
        "servicegraphMetrics": "otel.servicegraph.metrics",
        "interactionEvents": "graph.interactions.events",
        "interactionDlq": "graph.interactions.dlq",
    }
