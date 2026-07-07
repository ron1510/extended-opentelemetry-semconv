from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from extended_otel_semconv.k8s import K8sCluster, K8sContainer, K8sNamespace, K8sNode, K8sPod, entities_from_attributes


def test_raw_attributes_create_separate_semantic_entities() -> None:
    attributes = {
        "k8s.cluster.name": "prod-us-east-1",
        "k8s.namespace.name": "checkout",
        "k8s.node.name": "ip-10-0-12-34.ec2.internal",
        "k8s.pod.uid": "4e2b0bb9-4700-4f20-bb6f-c6e2b5975c6b",
        "k8s.pod.name": "checkout-api-7bc8c9c9cc-j62md",
        "container.id": "containerd://88f0c85b5e",
        "container.name": "app",
        "container.image.name": "registry.example.com/checkout-api",
        "container.image.tag": "1.8.3",
    }

    entities = entities_from_attributes(attributes)

    assert [entity.entity_type for entity in entities] == [
        "k8s.cluster",
        "k8s.namespace",
        "k8s.node",
        "k8s.pod",
        "k8s.container",
    ]
    assert isinstance(entities[0], K8sCluster)
    assert isinstance(entities[1], K8sNamespace)
    assert isinstance(entities[2], K8sNode)
    assert isinstance(entities[3], K8sPod)
    assert isinstance(entities[4], K8sContainer)
    assert entities[3].entity_id == "k8s.pod:prod-us-east-1:checkout:4e2b0bb9-4700-4f20-bb6f-c6e2b5975c6b"
    assert entities[4].entity_id == (
        "k8s.container:prod-us-east-1:checkout:"
        "4e2b0bb9-4700-4f20-bb6f-c6e2b5975c6b:containerd://88f0c85b5e"
    )


@given(
    cluster=st.text(min_size=1).filter(lambda value: ":" not in value),
    namespace=st.text(min_size=1).filter(lambda value: ":" not in value),
    node=st.text(min_size=1).filter(lambda value: ":" not in value),
    pod_uid=st.text(min_size=1).filter(lambda value: ":" not in value),
    container=st.text(min_size=1).filter(lambda value: ":" not in value),
)
def test_full_k8s_attribute_set_always_creates_stable_entity_ids(
    cluster: str,
    namespace: str,
    node: str,
    pod_uid: str,
    container: str,
) -> None:
    attributes = {
        "k8s.cluster.name": cluster,
        "k8s.namespace.name": namespace,
        "k8s.node.name": node,
        "k8s.pod.uid": pod_uid,
        "container.name": container,
    }

    entities = entities_from_attributes(attributes)

    assert [entity.entity_type for entity in entities] == [
        "k8s.cluster",
        "k8s.namespace",
        "k8s.node",
        "k8s.pod",
        "k8s.container",
    ]
    assert entities[0].entity_id == f"k8s.cluster:{cluster}"
    assert entities[1].entity_id == f"k8s.namespace:{cluster}:{namespace}"
    assert entities[2].entity_id == f"k8s.node:{cluster}:{node}"
    assert entities[3].entity_id == f"k8s.pod:{cluster}:{namespace}:{pod_uid}"
    assert entities[4].entity_id == f"k8s.container:{cluster}:{namespace}:{pod_uid}:{container}"


@given(st.dictionaries(st.text(min_size=1), st.one_of(st.text(), st.integers(), st.none()), max_size=20))
def test_unknown_attributes_do_not_create_entities(attributes: dict[str, object]) -> None:
    assume_no_supported_keys = not set(attributes).intersection(
        {
            "k8s.cluster.name",
            "k8s.namespace.name",
            "k8s.node.name",
            "k8s.pod.uid",
            "container.name",
            "k8s.container.name",
        }
    )
    if assume_no_supported_keys:
        assert entities_from_attributes(attributes) == []
