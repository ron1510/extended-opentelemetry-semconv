from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
OPENSHIFT = ROOT / "deploy" / "openshift"
WORKLOAD_KINDS = {"Deployment", "Job"}
CLUSTER_SCOPED_KINDS = {
    "ClusterRole",
    "ClusterRoleBinding",
    "CustomResourceDefinition",
    "Namespace",
    "SecurityContextConstraints",
}


def _resources() -> tuple[dict[str, Any], ...]:
    kustomization = cast(dict[str, Any], yaml.safe_load((OPENSHIFT / "kustomization.yaml").read_text()))
    documents: list[dict[str, Any]] = []
    for relative_path in cast(list[str], kustomization["resources"]):
        text = (OPENSHIFT / relative_path).read_text(encoding="utf-8")
        documents.extend(cast(Iterator[dict[str, Any]], yaml.safe_load_all(text)))
    return tuple(document for document in documents if document)


def _containers(resource: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    pod_spec = resource["spec"]["template"]["spec"]
    return tuple(cast(list[dict[str, Any]], pod_spec.get("initContainers", []))) + tuple(
        cast(list[dict[str, Any]], pod_spec["containers"])
    )


def test_openshift_bundle_is_namespace_scoped_and_excludes_example_secret() -> None:
    resources = _resources()
    kinds = {resource["kind"] for resource in resources}

    assert not kinds.intersection(CLUSTER_SCOPED_KINDS)
    assert "Secret" not in kinds
    assert "Route" not in kinds
    assert not any(resource["metadata"]["name"] == "servicegraph-kafka-auth" for resource in resources)


def test_workloads_follow_restricted_openshift_security_baseline() -> None:
    workloads = tuple(resource for resource in _resources() if resource["kind"] in WORKLOAD_KINDS)

    assert workloads
    for workload in workloads:
        pod_spec = workload["spec"]["template"]["spec"]
        pod_security = pod_spec["securityContext"]
        assert pod_security["runAsNonRoot"] is True
        assert "runAsUser" not in pod_security
        assert pod_security["seccompProfile"]["type"] == "RuntimeDefault"

        for container in _containers(workload):
            security = container["securityContext"]
            assert security["allowPrivilegeEscalation"] is False
            assert security["readOnlyRootFilesystem"] is True
            assert security["capabilities"]["drop"] == ["ALL"]
            assert "runAsUser" not in security
            assert container["resources"]["requests"]
            assert container["resources"]["limits"]["memory"]
            assert "@sha256:" in container["image"]
            assert not container["image"].endswith(":latest")


def test_kustomization_targets_team_and_does_not_deploy_mock_secret() -> None:
    kustomization = cast(dict[str, Any], yaml.safe_load((OPENSHIFT / "kustomization.yaml").read_text()))

    assert kustomization["namespace"] == "team"
    assert "kafka-secret.example.yaml" not in kustomization["resources"]


def test_flink_storage_and_collector_queue_use_distinct_access_modes() -> None:
    claims = {
        resource["metadata"]["name"]: resource
        for resource in _resources()
        if resource["kind"] == "PersistentVolumeClaim"
    }

    assert claims["servicegraph-flink-state"]["spec"]["accessModes"] == ["ReadWriteMany"]
    assert claims["servicegraph-flink-state"]["spec"]["storageClassName"] == "basic"
    assert claims["servicegraph-otelcol-queue"]["spec"]["accessModes"] == ["ReadWriteOnce"]


def test_all_flink_runtime_pods_mount_the_kafka_ca() -> None:
    flink_workloads = tuple(
        resource
        for resource in _resources()
        if resource["kind"] in WORKLOAD_KINDS and resource["metadata"]["name"].startswith("servicegraph-flink-")
    )

    assert flink_workloads
    for workload in flink_workloads:
        pod_spec = workload["spec"]["template"]["spec"]
        volumes = {volume["name"]: volume for volume in pod_spec["volumes"]}
        assert volumes["kafka-ca"]["secret"]["secretName"] == "servicegraph-kafka-auth"
        for container in _containers(workload):
            mounts = {mount["name"]: mount for mount in container["volumeMounts"]}
            assert mounts["kafka-ca"]["mountPath"] == "/etc/kafka/tls"
            assert mounts["kafka-ca"]["readOnly"] is True


def test_network_policy_isolation_is_scoped_to_this_application() -> None:
    policies = {
        resource["metadata"]["name"]: resource
        for resource in _resources()
        if resource["kind"] == "NetworkPolicy"
    }

    default_deny = policies["servicegraph-default-deny"]
    assert default_deny["spec"]["podSelector"]["matchLabels"] == {
        "app.kubernetes.io/part-of": "extended-otel-semconv"
    }
    assert default_deny["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert "ingress" not in default_deny["spec"]
    assert "egress" not in default_deny["spec"]
