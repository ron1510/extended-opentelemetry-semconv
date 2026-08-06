from __future__ import annotations

import random

from opentelemetry.proto.trace.v1.trace_pb2 import Span

from servicegraph_demo.main import EDGES, Topology, build_request, service_resource_attributes


def test_topology_grows_then_rotates_and_prioritizes_new_edges() -> None:
    topology = Topology(EDGES, initial_edges=2, max_active_edges=3, rng=random.Random(7))

    assert set(topology.sample(2)) == set(topology.active)
    retired, introduced = topology.advance()
    assert retired is None
    assert len(topology.active) == 3
    assert topology.sample(1) == (introduced,)

    retired, introduced = topology.advance()
    assert retired is not None
    assert retired not in topology.active
    assert introduced in topology.active
    assert len(topology.active) == 3

    _, next_introduced = topology.advance()
    assert next_introduced != retired


def test_request_contains_colocated_client_server_span_pairs() -> None:
    request = build_request(
        (EDGES[0], EDGES[1]),
        namespace="shop",
        instance_id="test",
        error_rate=0,
        rng=random.Random(11),
    )

    assert len(request.resource_spans) == 4
    for index in range(0, len(request.resource_spans), 2):
        client = request.resource_spans[index].scope_spans[0].spans[0]
        server = request.resource_spans[index + 1].scope_spans[0].spans[0]
        assert client.kind == Span.SPAN_KIND_CLIENT
        assert server.kind == Span.SPAN_KIND_SERVER
        assert client.trace_id == server.trace_id
        assert server.parent_span_id == client.span_id


def test_resource_profiles_are_rich_stable_and_service_specific() -> None:
    first = dict(service_resource_attributes("checkout-api", "shop", "test"))
    repeated = dict(service_resource_attributes("checkout-api", "shop", "test"))
    other = dict(service_resource_attributes("payments-api", "shop", "test"))

    assert first == repeated
    assert len(first) >= 35
    assert first["service.name"] == "checkout-api"
    assert first["service.namespace"] == "shop"
    assert first["k8s.namespace.name"] == "commerce"
    assert first["k8s.cluster.uid"] == other["k8s.cluster.uid"]
    assert first["k8s.pod.uid"] != other["k8s.pod.uid"]
    assert first["vcs.repository.url.full"] != other["vcs.repository.url.full"]
    assert isinstance(first["process.pid"], int)


def test_request_encodes_rich_resource_attribute_types() -> None:
    request = build_request(
        (EDGES[0],),
        namespace="shop",
        instance_id="test",
        error_rate=0,
        rng=random.Random(13),
    )

    attributes = {attribute.key: attribute.value for attribute in request.resource_spans[0].resource.attributes}
    assert attributes["service.version"].string_value
    assert attributes["k8s.cluster.uid"].string_value == "cluster-demo-production"
    assert attributes["process.pid"].WhichOneof("value") == "int_value"
    assert attributes["telemetry.sdk.language"].string_value
    assert attributes["vcs.ref.head.revision"].string_value
