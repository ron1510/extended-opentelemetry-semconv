"""Generated semantic entity and edge interfaces."""

from extended_otel_semconv.edges import SemanticEdge, semantic_edge_from_data
from extended_otel_semconv.entities import RawAttributes, SemanticEntity, entity_from_attributes
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
from extended_otel_semconv.generated.edges import ContainerRuntimeRunsK8sContainerEdge, K8sClusterContainsK8sNamespaceEdge, K8sClusterContainsK8sNodeEdge, K8sClusterContainsK8sPersistentvolumeEdge, K8sContainerRunsProcessEdge, K8sNamespaceContainsK8sCronjobEdge, K8sNamespaceContainsK8sDaemonsetEdge, K8sNamespaceContainsK8sDeploymentEdge, K8sNamespaceContainsK8sHpaEdge, K8sNamespaceContainsK8sJobEdge, K8sNamespaceContainsK8sPersistentvolumeclaimEdge, K8sNamespaceContainsK8sPodEdge, K8sNamespaceContainsK8sReplicasetEdge, K8sNamespaceContainsK8sReplicationcontrollerEdge, K8sNamespaceContainsK8sResourcequotaEdge, K8sNamespaceContainsK8sServiceEdge, K8sNamespaceContainsK8sStatefulsetEdge, K8sNodeRunsK8sPodEdge, K8sPodContainsK8sContainerEdge, K8sPodRunsServiceEdge, K8sPodRunsServiceInstanceEdge, ProcessUsesProcessExecutableEdge, ProcessUsesProcessRuntimeEdge, ServiceBuiltFromVcsRepositoryEdge, ServiceCallsServiceEdge, ServiceContainsServiceInstanceEdge, ServiceExposesAppEndpointEdge, ServiceInstrumentedByTelemetryDistroEdge, ServiceInstrumentedByTelemetrySdkEdge, ServiceNamespaceContainsServiceEdge, ServicePublishesToServiceEdge, ServiceQueriesServiceEdge, VcsRepositoryContainsVcsRefEdge
from extended_otel_semconv.generated.edges import EDGE_MODELS

ENTITY_MODELS: dict[str, type[SemanticEntity]] = {
    "app": App,
    "app.endpoint": AppEndpoint,
    "browser.document": BrowserDocument,
    "cicd.pipeline": CicdPipeline,
    "cicd.pipeline.run": CicdPipelineRun,
    "cicd.worker": CicdWorker,
    "container.runtime": ContainerRuntime,
    "gcp.gce.instance_group_manager": GcpGceInstanceGroupManager,
    "k8s.cluster": K8sCluster,
    "k8s.container": K8sContainer,
    "k8s.cronjob": K8sCronjob,
    "k8s.daemonset": K8sDaemonset,
    "k8s.deployment": K8sDeployment,
    "k8s.hpa": K8sHpa,
    "k8s.job": K8sJob,
    "k8s.namespace": K8sNamespace,
    "k8s.node": K8sNode,
    "k8s.node.system_container": K8sNodeSystemContainer,
    "k8s.persistentvolume": K8sPersistentvolume,
    "k8s.persistentvolumeclaim": K8sPersistentvolumeclaim,
    "k8s.pod": K8sPod,
    "k8s.replicaset": K8sReplicaset,
    "k8s.replicationcontroller": K8sReplicationcontroller,
    "k8s.resourcequota": K8sResourcequota,
    "k8s.service": K8sService,
    "k8s.statefulset": K8sStatefulset,
    "openshift.clusterquota": OpenshiftClusterquota,
    "process": Process,
    "process.executable": ProcessExecutable,
    "process.runtime": ProcessRuntime,
    "service": Service,
    "service.instance": ServiceInstance,
    "service.namespace": ServiceNamespace,
    "telemetry.distro": TelemetryDistro,
    "telemetry.sdk": TelemetrySdk,
    "vcs.ref": VcsRef,
    "vcs.repository": VcsRepository,
}


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
    "ContainerRuntimeRunsK8sContainerEdge",
    "K8sClusterContainsK8sNamespaceEdge",
    "K8sClusterContainsK8sNodeEdge",
    "K8sClusterContainsK8sPersistentvolumeEdge",
    "K8sContainerRunsProcessEdge",
    "K8sNamespaceContainsK8sCronjobEdge",
    "K8sNamespaceContainsK8sDaemonsetEdge",
    "K8sNamespaceContainsK8sDeploymentEdge",
    "K8sNamespaceContainsK8sHpaEdge",
    "K8sNamespaceContainsK8sJobEdge",
    "K8sNamespaceContainsK8sPersistentvolumeclaimEdge",
    "K8sNamespaceContainsK8sPodEdge",
    "K8sNamespaceContainsK8sReplicasetEdge",
    "K8sNamespaceContainsK8sReplicationcontrollerEdge",
    "K8sNamespaceContainsK8sResourcequotaEdge",
    "K8sNamespaceContainsK8sServiceEdge",
    "K8sNamespaceContainsK8sStatefulsetEdge",
    "K8sNodeRunsK8sPodEdge",
    "K8sPodContainsK8sContainerEdge",
    "K8sPodRunsServiceEdge",
    "K8sPodRunsServiceInstanceEdge",
    "ProcessUsesProcessExecutableEdge",
    "ProcessUsesProcessRuntimeEdge",
    "ServiceBuiltFromVcsRepositoryEdge",
    "ServiceCallsServiceEdge",
    "ServiceContainsServiceInstanceEdge",
    "ServiceExposesAppEndpointEdge",
    "ServiceInstrumentedByTelemetryDistroEdge",
    "ServiceInstrumentedByTelemetrySdkEdge",
    "ServiceNamespaceContainsServiceEdge",
    "ServicePublishesToServiceEdge",
    "ServiceQueriesServiceEdge",
    "VcsRepositoryContainsVcsRefEdge",
    "EDGE_MODELS",
    "ENTITY_MODELS",
    "SemanticEdge",
    "SemanticEntity",
    "entities_from_attributes",
    "entity_from_attributes",
    "semantic_edge_from_data",
]
