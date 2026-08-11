from __future__ import annotations

from typing import ClassVar, Self

from pydantic import Field, computed_field

from extended_otel_semconv.entities import (
    RawAttributes,
    SemanticEntity,
    quoted_entity_id,
    bool_value,
    int_value,
    object_value,
    string_value,
)

class K8sCluster(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.cluster"

    k8s_cluster_name: str | None = Field(default=None, alias="k8s.cluster.name")
    k8s_cluster_uid: str = Field(alias="k8s.cluster.uid")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_cluster_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_cluster_uid = string_value(attributes, "k8s.cluster.uid")
        if k8s_cluster_uid is None:
            return None
        return cls.model_validate({
            "k8s.cluster.name": string_value(attributes, "k8s.cluster.name"),
            "k8s.cluster.uid": k8s_cluster_uid,
        })


class K8sContainer(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.container"

    k8s_container_name: str = Field(alias="k8s.container.name")
    k8s_container_restart_count: int | None = Field(default=None, alias="k8s.container.restart_count")
    k8s_container_status_last_terminated_reason: str | None = Field(default=None, alias="k8s.container.status.last_terminated_reason")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_container_name,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_container_name = string_value(attributes, "k8s.container.name")
        if k8s_container_name is None:
            return None
        return cls.model_validate({
            "k8s.container.name": k8s_container_name,
            "k8s.container.restart_count": int_value(attributes, "k8s.container.restart_count"),
            "k8s.container.status.last_terminated_reason": string_value(attributes, "k8s.container.status.last_terminated_reason"),
        })


class K8sCronjob(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.cronjob"

    k8s_cronjob_uid: str = Field(alias="k8s.cronjob.uid")
    k8s_cronjob_name: str | None = Field(default=None, alias="k8s.cronjob.name")
    k8s_cronjob_label: object | None = Field(default=None, alias="k8s.cronjob.label")
    k8s_cronjob_annotation: object | None = Field(default=None, alias="k8s.cronjob.annotation")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_cronjob_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_cronjob_uid = string_value(attributes, "k8s.cronjob.uid")
        if k8s_cronjob_uid is None:
            return None
        return cls.model_validate({
            "k8s.cronjob.uid": k8s_cronjob_uid,
            "k8s.cronjob.name": string_value(attributes, "k8s.cronjob.name"),
            "k8s.cronjob.label": object_value(attributes, "k8s.cronjob.label"),
            "k8s.cronjob.annotation": object_value(attributes, "k8s.cronjob.annotation"),
        })


class K8sDaemonset(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.daemonset"

    k8s_daemonset_uid: str = Field(alias="k8s.daemonset.uid")
    k8s_daemonset_name: str | None = Field(default=None, alias="k8s.daemonset.name")
    k8s_daemonset_label: object | None = Field(default=None, alias="k8s.daemonset.label")
    k8s_daemonset_annotation: object | None = Field(default=None, alias="k8s.daemonset.annotation")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_daemonset_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_daemonset_uid = string_value(attributes, "k8s.daemonset.uid")
        if k8s_daemonset_uid is None:
            return None
        return cls.model_validate({
            "k8s.daemonset.uid": k8s_daemonset_uid,
            "k8s.daemonset.name": string_value(attributes, "k8s.daemonset.name"),
            "k8s.daemonset.label": object_value(attributes, "k8s.daemonset.label"),
            "k8s.daemonset.annotation": object_value(attributes, "k8s.daemonset.annotation"),
        })


class K8sDeployment(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.deployment"

    k8s_deployment_uid: str = Field(alias="k8s.deployment.uid")
    k8s_deployment_name: str | None = Field(default=None, alias="k8s.deployment.name")
    k8s_deployment_label: object | None = Field(default=None, alias="k8s.deployment.label")
    k8s_deployment_annotation: object | None = Field(default=None, alias="k8s.deployment.annotation")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_deployment_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_deployment_uid = string_value(attributes, "k8s.deployment.uid")
        if k8s_deployment_uid is None:
            return None
        return cls.model_validate({
            "k8s.deployment.uid": k8s_deployment_uid,
            "k8s.deployment.name": string_value(attributes, "k8s.deployment.name"),
            "k8s.deployment.label": object_value(attributes, "k8s.deployment.label"),
            "k8s.deployment.annotation": object_value(attributes, "k8s.deployment.annotation"),
        })


class K8sHpa(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.hpa"

    k8s_hpa_uid: str = Field(alias="k8s.hpa.uid")
    k8s_hpa_name: str | None = Field(default=None, alias="k8s.hpa.name")
    k8s_hpa_scaletargetref_kind: str | None = Field(default=None, alias="k8s.hpa.scaletargetref.kind")
    k8s_hpa_scaletargetref_name: str | None = Field(default=None, alias="k8s.hpa.scaletargetref.name")
    k8s_hpa_scaletargetref_api_version: str | None = Field(default=None, alias="k8s.hpa.scaletargetref.api_version")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_hpa_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_hpa_uid = string_value(attributes, "k8s.hpa.uid")
        if k8s_hpa_uid is None:
            return None
        return cls.model_validate({
            "k8s.hpa.uid": k8s_hpa_uid,
            "k8s.hpa.name": string_value(attributes, "k8s.hpa.name"),
            "k8s.hpa.scaletargetref.kind": string_value(attributes, "k8s.hpa.scaletargetref.kind"),
            "k8s.hpa.scaletargetref.name": string_value(attributes, "k8s.hpa.scaletargetref.name"),
            "k8s.hpa.scaletargetref.api_version": string_value(attributes, "k8s.hpa.scaletargetref.api_version"),
        })


class K8sJob(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.job"

    k8s_job_uid: str = Field(alias="k8s.job.uid")
    k8s_job_name: str | None = Field(default=None, alias="k8s.job.name")
    k8s_job_label: object | None = Field(default=None, alias="k8s.job.label")
    k8s_job_annotation: object | None = Field(default=None, alias="k8s.job.annotation")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_job_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_job_uid = string_value(attributes, "k8s.job.uid")
        if k8s_job_uid is None:
            return None
        return cls.model_validate({
            "k8s.job.uid": k8s_job_uid,
            "k8s.job.name": string_value(attributes, "k8s.job.name"),
            "k8s.job.label": object_value(attributes, "k8s.job.label"),
            "k8s.job.annotation": object_value(attributes, "k8s.job.annotation"),
        })


class K8sNamespace(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.namespace"

    k8s_namespace_name: str = Field(alias="k8s.namespace.name")
    k8s_namespace_label: object | None = Field(default=None, alias="k8s.namespace.label")
    k8s_namespace_annotation: object | None = Field(default=None, alias="k8s.namespace.annotation")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_namespace_name,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_namespace_name = string_value(attributes, "k8s.namespace.name")
        if k8s_namespace_name is None:
            return None
        return cls.model_validate({
            "k8s.namespace.name": k8s_namespace_name,
            "k8s.namespace.label": object_value(attributes, "k8s.namespace.label"),
            "k8s.namespace.annotation": object_value(attributes, "k8s.namespace.annotation"),
        })


class K8sNode(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.node"

    k8s_node_name: str | None = Field(default=None, alias="k8s.node.name")
    k8s_node_uid: str = Field(alias="k8s.node.uid")
    k8s_node_label: object | None = Field(default=None, alias="k8s.node.label")
    k8s_node_annotation: object | None = Field(default=None, alias="k8s.node.annotation")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_node_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_node_uid = string_value(attributes, "k8s.node.uid")
        if k8s_node_uid is None:
            return None
        return cls.model_validate({
            "k8s.node.name": string_value(attributes, "k8s.node.name"),
            "k8s.node.uid": k8s_node_uid,
            "k8s.node.label": object_value(attributes, "k8s.node.label"),
            "k8s.node.annotation": object_value(attributes, "k8s.node.annotation"),
        })


class K8sNodeSystemContainer(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.node.system_container"

    k8s_node_system_container_name: str = Field(alias="k8s.node.system_container.name")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_node_system_container_name,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_node_system_container_name = string_value(attributes, "k8s.node.system_container.name")
        if k8s_node_system_container_name is None:
            return None
        return cls.model_validate({
            "k8s.node.system_container.name": k8s_node_system_container_name,
        })


class K8sPersistentvolume(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.persistentvolume"

    k8s_persistentvolume_uid: str = Field(alias="k8s.persistentvolume.uid")
    k8s_persistentvolume_name: str | None = Field(default=None, alias="k8s.persistentvolume.name")
    k8s_storageclass_name: str | None = Field(default=None, alias="k8s.storageclass.name")
    k8s_persistentvolume_reclaim_policy: str | None = Field(default=None, alias="k8s.persistentvolume.reclaim_policy")
    k8s_persistentvolume_label: object | None = Field(default=None, alias="k8s.persistentvolume.label")
    k8s_persistentvolume_annotation: object | None = Field(default=None, alias="k8s.persistentvolume.annotation")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_persistentvolume_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_persistentvolume_uid = string_value(attributes, "k8s.persistentvolume.uid")
        if k8s_persistentvolume_uid is None:
            return None
        return cls.model_validate({
            "k8s.persistentvolume.uid": k8s_persistentvolume_uid,
            "k8s.persistentvolume.name": string_value(attributes, "k8s.persistentvolume.name"),
            "k8s.storageclass.name": string_value(attributes, "k8s.storageclass.name"),
            "k8s.persistentvolume.reclaim_policy": string_value(attributes, "k8s.persistentvolume.reclaim_policy"),
            "k8s.persistentvolume.label": object_value(attributes, "k8s.persistentvolume.label"),
            "k8s.persistentvolume.annotation": object_value(attributes, "k8s.persistentvolume.annotation"),
        })


class K8sPersistentvolumeclaim(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.persistentvolumeclaim"

    k8s_persistentvolumeclaim_uid: str = Field(alias="k8s.persistentvolumeclaim.uid")
    k8s_persistentvolumeclaim_name: str | None = Field(default=None, alias="k8s.persistentvolumeclaim.name")
    k8s_storageclass_name: str | None = Field(default=None, alias="k8s.storageclass.name")
    k8s_persistentvolumeclaim_label: object | None = Field(default=None, alias="k8s.persistentvolumeclaim.label")
    k8s_persistentvolumeclaim_annotation: object | None = Field(default=None, alias="k8s.persistentvolumeclaim.annotation")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_persistentvolumeclaim_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_persistentvolumeclaim_uid = string_value(attributes, "k8s.persistentvolumeclaim.uid")
        if k8s_persistentvolumeclaim_uid is None:
            return None
        return cls.model_validate({
            "k8s.persistentvolumeclaim.uid": k8s_persistentvolumeclaim_uid,
            "k8s.persistentvolumeclaim.name": string_value(attributes, "k8s.persistentvolumeclaim.name"),
            "k8s.storageclass.name": string_value(attributes, "k8s.storageclass.name"),
            "k8s.persistentvolumeclaim.label": object_value(attributes, "k8s.persistentvolumeclaim.label"),
            "k8s.persistentvolumeclaim.annotation": object_value(attributes, "k8s.persistentvolumeclaim.annotation"),
        })


class K8sPod(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.pod"

    k8s_pod_uid: str = Field(alias="k8s.pod.uid")
    k8s_pod_name: str | None = Field(default=None, alias="k8s.pod.name")
    k8s_pod_label: object | None = Field(default=None, alias="k8s.pod.label")
    k8s_pod_annotation: object | None = Field(default=None, alias="k8s.pod.annotation")
    k8s_pod_ip: str | None = Field(default=None, alias="k8s.pod.ip")
    k8s_pod_hostname: str | None = Field(default=None, alias="k8s.pod.hostname")
    k8s_pod_start_time: str | None = Field(default=None, alias="k8s.pod.start_time")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_pod_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_pod_uid = string_value(attributes, "k8s.pod.uid")
        if k8s_pod_uid is None:
            return None
        return cls.model_validate({
            "k8s.pod.uid": k8s_pod_uid,
            "k8s.pod.name": string_value(attributes, "k8s.pod.name"),
            "k8s.pod.label": object_value(attributes, "k8s.pod.label"),
            "k8s.pod.annotation": object_value(attributes, "k8s.pod.annotation"),
            "k8s.pod.ip": string_value(attributes, "k8s.pod.ip"),
            "k8s.pod.hostname": string_value(attributes, "k8s.pod.hostname"),
            "k8s.pod.start_time": string_value(attributes, "k8s.pod.start_time"),
        })


class K8sReplicaset(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.replicaset"

    k8s_replicaset_uid: str = Field(alias="k8s.replicaset.uid")
    k8s_replicaset_name: str | None = Field(default=None, alias="k8s.replicaset.name")
    k8s_replicaset_label: object | None = Field(default=None, alias="k8s.replicaset.label")
    k8s_replicaset_annotation: object | None = Field(default=None, alias="k8s.replicaset.annotation")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_replicaset_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_replicaset_uid = string_value(attributes, "k8s.replicaset.uid")
        if k8s_replicaset_uid is None:
            return None
        return cls.model_validate({
            "k8s.replicaset.uid": k8s_replicaset_uid,
            "k8s.replicaset.name": string_value(attributes, "k8s.replicaset.name"),
            "k8s.replicaset.label": object_value(attributes, "k8s.replicaset.label"),
            "k8s.replicaset.annotation": object_value(attributes, "k8s.replicaset.annotation"),
        })


class K8sReplicationcontroller(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.replicationcontroller"

    k8s_replicationcontroller_uid: str = Field(alias="k8s.replicationcontroller.uid")
    k8s_replicationcontroller_name: str | None = Field(default=None, alias="k8s.replicationcontroller.name")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_replicationcontroller_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_replicationcontroller_uid = string_value(attributes, "k8s.replicationcontroller.uid")
        if k8s_replicationcontroller_uid is None:
            return None
        return cls.model_validate({
            "k8s.replicationcontroller.uid": k8s_replicationcontroller_uid,
            "k8s.replicationcontroller.name": string_value(attributes, "k8s.replicationcontroller.name"),
        })


class K8sResourcequota(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.resourcequota"

    k8s_resourcequota_uid: str = Field(alias="k8s.resourcequota.uid")
    k8s_resourcequota_name: str | None = Field(default=None, alias="k8s.resourcequota.name")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_resourcequota_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_resourcequota_uid = string_value(attributes, "k8s.resourcequota.uid")
        if k8s_resourcequota_uid is None:
            return None
        return cls.model_validate({
            "k8s.resourcequota.uid": k8s_resourcequota_uid,
            "k8s.resourcequota.name": string_value(attributes, "k8s.resourcequota.name"),
        })


class K8sService(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.service"

    k8s_service_uid: str = Field(alias="k8s.service.uid")
    k8s_service_name: str | None = Field(default=None, alias="k8s.service.name")
    k8s_service_type: str | None = Field(default=None, alias="k8s.service.type")
    k8s_service_traffic_distribution: str | None = Field(default=None, alias="k8s.service.traffic_distribution")
    k8s_service_publish_not_ready_addresses: bool | None = Field(default=None, alias="k8s.service.publish_not_ready_addresses")
    k8s_service_selector: object | None = Field(default=None, alias="k8s.service.selector")
    k8s_service_label: object | None = Field(default=None, alias="k8s.service.label")
    k8s_service_annotation: object | None = Field(default=None, alias="k8s.service.annotation")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_service_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_service_uid = string_value(attributes, "k8s.service.uid")
        if k8s_service_uid is None:
            return None
        return cls.model_validate({
            "k8s.service.uid": k8s_service_uid,
            "k8s.service.name": string_value(attributes, "k8s.service.name"),
            "k8s.service.type": string_value(attributes, "k8s.service.type"),
            "k8s.service.traffic_distribution": string_value(attributes, "k8s.service.traffic_distribution"),
            "k8s.service.publish_not_ready_addresses": bool_value(attributes, "k8s.service.publish_not_ready_addresses"),
            "k8s.service.selector": object_value(attributes, "k8s.service.selector"),
            "k8s.service.label": object_value(attributes, "k8s.service.label"),
            "k8s.service.annotation": object_value(attributes, "k8s.service.annotation"),
        })


class K8sStatefulset(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.statefulset"

    k8s_statefulset_uid: str = Field(alias="k8s.statefulset.uid")
    k8s_statefulset_name: str | None = Field(default=None, alias="k8s.statefulset.name")
    k8s_statefulset_label: object | None = Field(default=None, alias="k8s.statefulset.label")
    k8s_statefulset_annotation: object | None = Field(default=None, alias="k8s.statefulset.annotation")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> str:
        return quoted_entity_id(
            self.entity_type,
            self.k8s_statefulset_uid,
        )

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        k8s_statefulset_uid = string_value(attributes, "k8s.statefulset.uid")
        if k8s_statefulset_uid is None:
            return None
        return cls.model_validate({
            "k8s.statefulset.uid": k8s_statefulset_uid,
            "k8s.statefulset.name": string_value(attributes, "k8s.statefulset.name"),
            "k8s.statefulset.label": object_value(attributes, "k8s.statefulset.label"),
            "k8s.statefulset.annotation": object_value(attributes, "k8s.statefulset.annotation"),
        })


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    for entity_class in (K8sCluster, K8sContainer, K8sCronjob, K8sDaemonset, K8sDeployment, K8sHpa, K8sJob, K8sNamespace, K8sNode, K8sNodeSystemContainer, K8sPersistentvolume, K8sPersistentvolumeclaim, K8sPod, K8sReplicaset, K8sReplicationcontroller, K8sResourcequota, K8sService, K8sStatefulset):
        entity = entity_class.from_attributes(attributes)
        if entity is not None:
            entities.append(entity)
    return entities
