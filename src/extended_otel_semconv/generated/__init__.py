"""Generated semantic entity interfaces."""

from extended_otel_semconv.entities import RawAttributes, SemanticEntity
from extended_otel_semconv.generated.app import App, AppEndpoint
from extended_otel_semconv.generated.app import entities_from_attributes as _app_entities
from extended_otel_semconv.generated.browser import BrowserDocument
from extended_otel_semconv.generated.browser import entities_from_attributes as _browser_entities
from extended_otel_semconv.generated.cicd import CicdPipeline, CicdPipelineRun, CicdWorker
from extended_otel_semconv.generated.cicd import entities_from_attributes as _cicd_entities
from extended_otel_semconv.generated.container import ContainerRuntime
from extended_otel_semconv.generated.container import entities_from_attributes as _container_entities
from extended_otel_semconv.generated.gcp import GcpGceInstanceGroupManager
from extended_otel_semconv.generated.gcp import entities_from_attributes as _gcp_entities
from extended_otel_semconv.generated.k8s import K8sCluster, K8sContainer, K8sCronjob, K8sDaemonset, K8sDeployment, K8sHpa, K8sJob, K8sNamespace, K8sNode, K8sNodeSystemContainer, K8sPersistentvolume, K8sPersistentvolumeclaim, K8sPod, K8sReplicaset, K8sReplicationcontroller, K8sResourcequota, K8sService, K8sStatefulset
from extended_otel_semconv.generated.k8s import entities_from_attributes as _k8s_entities
from extended_otel_semconv.generated.openshift import OpenshiftClusterquota
from extended_otel_semconv.generated.openshift import entities_from_attributes as _openshift_entities
from extended_otel_semconv.generated.process import Process, ProcessExecutable, ProcessRuntime
from extended_otel_semconv.generated.process import entities_from_attributes as _process_entities
from extended_otel_semconv.generated.service import Service, ServiceInstance, ServiceNamespace
from extended_otel_semconv.generated.service import entities_from_attributes as _service_entities
from extended_otel_semconv.generated.telemetry import TelemetryDistro, TelemetrySdk
from extended_otel_semconv.generated.telemetry import entities_from_attributes as _telemetry_entities
from extended_otel_semconv.generated.vcs import VcsRef, VcsRepository
from extended_otel_semconv.generated.vcs import entities_from_attributes as _vcs_entities


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    entities.extend(_app_entities(attributes))
    entities.extend(_browser_entities(attributes))
    entities.extend(_cicd_entities(attributes))
    entities.extend(_container_entities(attributes))
    entities.extend(_gcp_entities(attributes))
    entities.extend(_k8s_entities(attributes))
    entities.extend(_openshift_entities(attributes))
    entities.extend(_process_entities(attributes))
    entities.extend(_service_entities(attributes))
    entities.extend(_telemetry_entities(attributes))
    entities.extend(_vcs_entities(attributes))
    return entities


__all__ = [
    "App",
    "AppEndpoint",
    "BrowserDocument",
    "CicdPipeline",
    "CicdPipelineRun",
    "CicdWorker",
    "ContainerRuntime",
    "GcpGceInstanceGroupManager",
    "K8sCluster",
    "K8sContainer",
    "K8sCronjob",
    "K8sDaemonset",
    "K8sDeployment",
    "K8sHpa",
    "K8sJob",
    "K8sNamespace",
    "K8sNode",
    "K8sNodeSystemContainer",
    "K8sPersistentvolume",
    "K8sPersistentvolumeclaim",
    "K8sPod",
    "K8sReplicaset",
    "K8sReplicationcontroller",
    "K8sResourcequota",
    "K8sService",
    "K8sStatefulset",
    "OpenshiftClusterquota",
    "Process",
    "ProcessExecutable",
    "ProcessRuntime",
    "Service",
    "ServiceInstance",
    "ServiceNamespace",
    "TelemetryDistro",
    "TelemetrySdk",
    "VcsRef",
    "VcsRepository",
    "SemanticEntity",
    "entities_from_attributes",
]
