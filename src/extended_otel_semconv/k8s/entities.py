from __future__ import annotations

from types import MappingProxyType
from typing import Any, ClassVar, Mapping, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field

RawAttributes = Mapping[str, Any]


def _string_value(attributes: RawAttributes, key: str) -> str | None:
    value = attributes.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool | int | float):
        return str(value)
    return None


def _raw_snapshot(attributes: RawAttributes) -> Mapping[str, Any]:
    return MappingProxyType(dict(attributes))


class SemanticEntity(BaseModel):
    """Base class for a concrete semantic entity parsed from raw OTel attributes."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)

    raw_attributes: Mapping[str, Any] = Field(default_factory=dict, exclude=True)

    entity_type: ClassVar[str]

    @computed_field
    @property
    def entity_id(self) -> str:
        raise NotImplementedError


class K8sCluster(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.cluster"

    name: str

    @computed_field
    @property
    def entity_id(self) -> str:
        return f"k8s.cluster:{self.name}"

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        name = _string_value(attributes, "k8s.cluster.name")
        if name is None:
            return None
        return cls(name=name, raw_attributes=_raw_snapshot(attributes))


class K8sNamespace(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.namespace"

    cluster_name: str
    name: str

    @computed_field
    @property
    def entity_id(self) -> str:
        return f"k8s.namespace:{self.cluster_name}:{self.name}"

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        cluster_name = _string_value(attributes, "k8s.cluster.name")
        name = _string_value(attributes, "k8s.namespace.name")
        if cluster_name is None or name is None:
            return None
        return cls(cluster_name=cluster_name, name=name, raw_attributes=_raw_snapshot(attributes))


class K8sNode(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.node"

    cluster_name: str
    name: str
    uid: str | None = None

    @computed_field
    @property
    def entity_id(self) -> str:
        return f"k8s.node:{self.cluster_name}:{self.uid or self.name}"

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        cluster_name = _string_value(attributes, "k8s.cluster.name")
        name = _string_value(attributes, "k8s.node.name")
        if cluster_name is None or name is None:
            return None
        return cls(
            cluster_name=cluster_name,
            name=name,
            uid=_string_value(attributes, "k8s.node.uid"),
            raw_attributes=_raw_snapshot(attributes),
        )


class K8sPod(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.pod"

    cluster_name: str
    namespace_name: str
    uid: str
    name: str | None = None
    node_name: str | None = None

    @computed_field
    @property
    def entity_id(self) -> str:
        return f"k8s.pod:{self.cluster_name}:{self.namespace_name}:{self.uid}"

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        cluster_name = _string_value(attributes, "k8s.cluster.name")
        namespace_name = _string_value(attributes, "k8s.namespace.name")
        uid = _string_value(attributes, "k8s.pod.uid")
        if cluster_name is None or namespace_name is None or uid is None:
            return None
        return cls(
            cluster_name=cluster_name,
            namespace_name=namespace_name,
            uid=uid,
            name=_string_value(attributes, "k8s.pod.name"),
            node_name=_string_value(attributes, "k8s.node.name"),
            raw_attributes=_raw_snapshot(attributes),
        )


class K8sContainer(SemanticEntity):
    entity_type: ClassVar[str] = "k8s.container"

    cluster_name: str
    namespace_name: str
    pod_uid: str
    name: str
    runtime_id: str | None = None
    image_name: str | None = None
    image_tag: str | None = None

    @computed_field
    @property
    def entity_id(self) -> str:
        container_key = self.runtime_id or self.name
        return f"k8s.container:{self.cluster_name}:{self.namespace_name}:{self.pod_uid}:{container_key}"

    @classmethod
    def from_attributes(cls, attributes: RawAttributes) -> Self | None:
        cluster_name = _string_value(attributes, "k8s.cluster.name")
        namespace_name = _string_value(attributes, "k8s.namespace.name")
        pod_uid = _string_value(attributes, "k8s.pod.uid")
        name = _string_value(attributes, "k8s.container.name") or _string_value(attributes, "container.name")
        if cluster_name is None or namespace_name is None or pod_uid is None or name is None:
            return None
        return cls(
            cluster_name=cluster_name,
            namespace_name=namespace_name,
            pod_uid=pod_uid,
            name=name,
            runtime_id=_string_value(attributes, "container.id"),
            image_name=_string_value(attributes, "container.image.name"),
            image_tag=_string_value(attributes, "container.image.tag"),
            raw_attributes=_raw_snapshot(attributes),
        )


def entities_from_attributes(attributes: RawAttributes) -> list[SemanticEntity]:
    """Create every supported Kubernetes semantic entity from raw OTel attributes."""

    entities: list[SemanticEntity] = []
    for entity_class in (K8sCluster, K8sNamespace, K8sNode, K8sPod, K8sContainer):
        entity = entity_class.from_attributes(attributes)
        if entity is not None:
            entities.append(entity)
    return entities
