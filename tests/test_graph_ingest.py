from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue
from opentelemetry.proto.metrics.v1.metrics_pb2 import AGGREGATION_TEMPORALITY_CUMULATIVE
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import Span

from extended_otel_semconv.graph.app import create_app
from extended_otel_semconv.graph.metrics import SERVICE_GRAPH_REQUEST_TOTAL, parse_metrics_request
from extended_otel_semconv.graph.otlp import any_value_to_python, parse_trace_request
from extended_otel_semconv.graph.store import EntityGraph
from extended_otel_semconv.registry.model import AttributeDefinition
from extended_otel_semconv.registry.validation import load_model_registry

ROOT = Path(__file__).resolve().parents[1]


def test_any_value_to_python_converts_otlp_values() -> None:
    value = AnyValue()
    value.kvlist_value.values.add(key="name", value=AnyValue(string_value="checkout"))
    value.kvlist_value.values.add(key="count", value=AnyValue(int_value=3))

    assert any_value_to_python(value) == {"name": "checkout", "count": 3}


def test_parse_trace_request_merges_resource_and_span_attributes() -> None:
    request = _trace_request(
        resource_attributes={"service.name": "frontend"},
        spans=[
            _span(
                span_id=b"\x01" * 8,
                kind=Span.SPAN_KIND_SERVER,
                attributes={"http.request.method": "GET"},
            )
        ],
    )

    records = parse_trace_request(request.SerializeToString())

    assert len(records) == 1
    assert records[0].attributes["service.name"] == "frontend"
    assert records[0].attributes["http.request.method"] == "GET"


def test_graph_creates_server_endpoint_only() -> None:
    graph = EntityGraph(ttl_seconds=900, clock=_clock([100.0]))
    request = _trace_request(
        resource_attributes={
            "service.name": "checkout-api",
            "service.namespace": "payments",
        },
        spans=[
            _span(
                span_id=b"\x01" * 8,
                kind=Span.SPAN_KIND_CLIENT,
                attributes={"http.request.method": "POST", "http.route": "/checkout/{cart_id}"},
            )
        ],
    )

    graph.ingest_spans(parse_trace_request(request.SerializeToString()))

    assert "service:checkout-api" in {node.id for node in graph.snapshot().entities}
    assert not any(node.type == "app.endpoint" for node in graph.snapshot().entities)
    service = next(node for node in graph.snapshot().entities if node.id == "service:checkout-api")
    assert service.sources == {"trace": 1}


def test_graph_does_not_infer_dependency_edges_from_raw_traces() -> None:
    graph = EntityGraph(ttl_seconds=900, clock=_clock([100.0]))
    trace_id = b"\x09" * 16
    parent_span_id = b"\x01" * 8
    child_span_id = b"\x02" * 8

    request = _trace_request(
        trace_id=trace_id,
        resource_attributes={"service.name": "frontend", "service.namespace": "web"},
        spans=[
            _span(
                span_id=parent_span_id,
                kind=Span.SPAN_KIND_CLIENT,
                attributes={"http.request.method": "POST", "http.route": "/checkout/{cart_id}"},
            ),
            _span(
                span_id=child_span_id,
                parent_span_id=parent_span_id,
                kind=Span.SPAN_KIND_SERVER,
                attributes={"http.request.method": "POST", "http.route": "/checkout/{cart_id}"},
            )
        ],
    )

    graph.ingest_spans(parse_trace_request(request.SerializeToString()))

    edges = graph.snapshot().edges
    assert not any(edge.type == "calls" for edge in edges)


def test_parse_service_graph_metric_points() -> None:
    request = _metrics_request(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {
            "client": "frontend",
            "server": "checkout-api",
            "connection_type": "",
            "server_http.route": "/checkout/{cart_id}",
        },
        value=3,
    )

    points = parse_metrics_request(request.SerializeToString())

    assert len(points) == 1
    assert points[0].name == SERVICE_GRAPH_REQUEST_TOTAL
    assert points[0].attributes["client"] == "frontend"
    assert points[0].value == 3


def test_service_graph_metric_creates_dependency_edge_between_observed_services() -> None:
    graph = EntityGraph(ttl_seconds=900, clock=_clock([100.0, 101.0]))
    graph.ingest_spans(
        parse_trace_request(
            _trace_request(
                resource_attributes={"service.name": "frontend", "service.namespace": "web"},
                spans=[_span(span_id=b"\x01" * 8, kind=Span.SPAN_KIND_CLIENT, attributes={})],
            ).SerializeToString()
        )
    )
    graph.ingest_spans(
        parse_trace_request(
            _trace_request(
                resource_attributes={"service.name": "checkout-api", "service.namespace": "payments"},
                spans=[
                    _span(
                        span_id=b"\x02" * 8,
                        kind=Span.SPAN_KIND_SERVER,
                        attributes={"http.request.method": "POST", "http.route": "/checkout/{cart_id}"},
                    )
                ],
            ).SerializeToString()
        )
    )

    graph.ingest_metric_points(
        parse_metrics_request(
            _metrics_request(
                SERVICE_GRAPH_REQUEST_TOTAL,
                {
                    "client": "frontend",
                    "server": "checkout-api",
                    "connection_type": "",
                    "server_service.namespace": "payments",
                    "server_http.request.method": "POST",
                    "server_http.route": "/checkout/{cart_id}",
                },
                value=7,
            ).SerializeToString()
        )
    )

    edge = next(edge for edge in graph.snapshot().edges if edge.type == "calls")
    assert edge.source == "service:frontend"
    assert edge.target == "service:checkout-api"
    assert edge.sources == {"service_graph": 1}
    assert edge.attributes["service_graph.request.total"] == 7
    assert edge.attributes["target_endpoint.id"] == "app.endpoint:checkout-api:payments:POST:%2Fcheckout%2F%7Bcart_id%7D"


def test_service_graph_metric_materializes_entities_from_prefixed_dimensions() -> None:
    graph = EntityGraph(ttl_seconds=900, clock=_clock([100.0]))

    graph.ingest_metric_points(
        parse_metrics_request(
            _metrics_request(
                SERVICE_GRAPH_REQUEST_TOTAL,
                {
                    "client": "frontend",
                    "server": "checkout-api",
                    "connection_type": "",
                    "client_service.namespace": "web",
                    "client_k8s.namespace.name": "frontend",
                    "client_k8s.pod.uid": "frontend-pod-demo",
                    "server_service.namespace": "payments",
                    "server_service.instance.id": "checkout/demo",
                    "server_k8s.namespace.name": "checkout",
                    "server_k8s.pod.uid": "checkout-pod-demo",
                    "server_http.request.method": "POST",
                    "server_http.route": "/checkout/{cart_id}",
                },
                value=1,
            ).SerializeToString()
        )
    )

    snapshot = graph.snapshot()
    node_ids = {node.id for node in snapshot.entities}
    assert "service:frontend" in node_ids
    assert "service.namespace:web" in node_ids
    assert "k8s.pod:checkout-pod-demo" in node_ids
    assert "service.instance:checkout%2Fdemo" in node_ids
    assert "app.endpoint:checkout-api:payments:POST:%2Fcheckout%2F%7Bcart_id%7D" in node_ids
    assert all(node.attributes for node in snapshot.entities)
    assert next(node for node in snapshot.entities if node.id == "service:frontend").sources == {"service_graph": 1}
    assert any(edge.type == "runs" and edge.source == "k8s.pod:checkout-pod-demo" and edge.target == "service:checkout-api" for edge in snapshot.edges)
    assert any(edge.type == "calls" and edge.source == "service:frontend" and edge.target == "service:checkout-api" for edge in snapshot.edges)


def test_service_graph_metric_can_reinforce_all_generated_server_entities() -> None:
    graph = EntityGraph(ttl_seconds=900, clock=_clock([100.0]))
    raw_attributes = _maximal_entity_attributes(service_name="max-server")
    metric_attributes = {
        "client": "max-client",
        "server": "max-server",
        "connection_type": "",
        **{f"client_{key}": value for key, value in _maximal_entity_attributes(service_name="max-client").items()},
        **{f"server_{key}": value for key, value in raw_attributes.items()},
    }

    graph.ingest_metric_points(
        parse_metrics_request(
            _metrics_request(SERVICE_GRAPH_REQUEST_TOTAL, metric_attributes, value=1).SerializeToString()
        )
    )

    snapshot = graph.snapshot()
    node_types = {node.type for node in snapshot.entities}
    expected_server_types = _expected_identifiable_entity_types()
    assert expected_server_types <= node_types
    assert "app.endpoint" in node_types
    edge_keys = {(edge.source, edge.target, edge.type) for edge in snapshot.edges}
    assert ("service:max-client", "service:max-server", "calls") in edge_keys
    assert ("service:max-server", "service.instance:max-server%2Finstance", "contains") in edge_keys
    assert ("k8s.pod:max-server-pod-uid", "service.instance:max-server%2Finstance", "runs") in edge_keys
    assert any(edge.type == "instrumented_by" and edge.source == "service:max-server" for edge in snapshot.edges)
    assert any(edge.type == "built_from" and edge.source == "service:max-server" for edge in snapshot.edges)
    assert len(snapshot.edges) >= 20


def test_service_graph_connection_types_map_to_typed_edges() -> None:
    graph = EntityGraph(ttl_seconds=900, clock=_clock([100.0, 101.0, 102.0]))
    for name in ("producer", "consumer", "database"):
        graph.ingest_spans(
            parse_trace_request(
                _trace_request(
                    resource_attributes={"service.name": name},
                    spans=[_span(span_id=name.encode().ljust(8, b"0")[:8], kind=Span.SPAN_KIND_INTERNAL, attributes={})],
                ).SerializeToString()
            )
        )

    graph.ingest_metric_points(
        parse_metrics_request(
            _metrics_request(
                SERVICE_GRAPH_REQUEST_TOTAL,
                {"client": "producer", "server": "consumer", "connection_type": "messaging_system"},
                value=2,
            ).SerializeToString()
        )
    )
    graph.ingest_metric_points(
        parse_metrics_request(
            _metrics_request(
                SERVICE_GRAPH_REQUEST_TOTAL,
                {"client": "producer", "server": "database", "connection_type": "database"},
                value=2,
            ).SerializeToString()
        )
    )

    edge_types = {edge.type for edge in graph.snapshot().edges}
    assert "publishes_to" in edge_types
    assert "queries" in edge_types


def test_graph_prunes_stale_entities_and_edges() -> None:
    graph = EntityGraph(ttl_seconds=10, clock=_clock([100.0, 111.0]))
    request = _trace_request(
        resource_attributes={"service.name": "checkout-api", "service.namespace": "payments"},
        spans=[
            _span(
                span_id=b"\x01" * 8,
                kind=Span.SPAN_KIND_SERVER,
                attributes={"http.request.method": "GET", "http.route": "/health"},
            )
        ],
    )

    graph.ingest_spans(parse_trace_request(request.SerializeToString()))

    assert graph.snapshot().entities == []
    assert graph.snapshot().edges == []


def test_fastapi_otlp_endpoint_updates_graph() -> None:
    graph = EntityGraph(ttl_seconds=900, clock=_clock([100.0, 100.0]))
    client = TestClient(create_app(graph))
    request = _trace_request(
        resource_attributes={"service.name": "checkout-api", "service.namespace": "payments"},
        spans=[
            _span(
                span_id=b"\x01" * 8,
                kind=Span.SPAN_KIND_SERVER,
                attributes={"http.request.method": "POST", "http.route": "/checkout/{cart_id}"},
            )
        ],
    )

    response = client.post(
        "/v1/traces",
        content=request.SerializeToString(),
        headers={"content-type": "application/x-protobuf"},
    )

    assert response.status_code == 200
    graph_response = client.get("/graph")
    assert graph_response.status_code == 200
    assert any(entity["type"] == "app.endpoint" for entity in graph_response.json()["entities"])


def test_fastapi_otlp_endpoint_accepts_gzip_encoded_body() -> None:
    graph = EntityGraph(ttl_seconds=900, clock=_clock([100.0, 100.0]))
    client = TestClient(create_app(graph))
    request = _trace_request(
        resource_attributes={"service.name": "checkout-api", "service.namespace": "payments"},
        spans=[
            _span(
                span_id=b"\x01" * 8,
                kind=Span.SPAN_KIND_SERVER,
                attributes={"http.request.method": "POST", "http.route": "/checkout/{cart_id}"},
            )
        ],
    )

    response = client.post(
        "/v1/traces",
        content=gzip.compress(request.SerializeToString()),
        headers={"content-type": "application/x-protobuf", "content-encoding": "gzip"},
    )

    assert response.status_code == 200
    assert any(entity.type == "app.endpoint" for entity in graph.snapshot().entities)


def test_fastapi_otlp_endpoint_rejects_invalid_gzip_body() -> None:
    client = TestClient(create_app(EntityGraph()))

    response = client.post(
        "/v1/traces",
        content=b"not-gzip",
        headers={"content-type": "application/x-protobuf", "content-encoding": "gzip"},
    )

    assert response.status_code == 400


def test_fastapi_otlp_metrics_endpoint_updates_graph() -> None:
    graph = EntityGraph(ttl_seconds=900, clock=_clock([100.0, 101.0, 102.0]))
    client = TestClient(create_app(graph))
    for service_name in ("frontend", "checkout-api"):
        graph.ingest_spans(
            parse_trace_request(
                _trace_request(
                    resource_attributes={"service.name": service_name},
                    spans=[_span(span_id=service_name.encode().ljust(8, b"0")[:8], kind=Span.SPAN_KIND_INTERNAL, attributes={})],
                ).SerializeToString()
            )
        )
    request = _metrics_request(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {"client": "frontend", "server": "checkout-api", "connection_type": ""},
        value=1,
    )

    response = client.post(
        "/v1/metrics",
        content=request.SerializeToString(),
        headers={"content-type": "application/x-protobuf"},
    )

    assert response.status_code == 200
    assert any(edge["type"] == "calls" for edge in client.get("/graph").json()["edges"])


def _trace_request(
    resource_attributes: dict[str, object],
    spans: list[Span],
    trace_id: bytes = b"\x01" * 16,
) -> ExportTraceServiceRequest:
    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    resource_spans.resource.CopyFrom(_resource(resource_attributes))
    scope_spans = resource_spans.scope_spans.add()
    for span in spans:
        span.trace_id = trace_id
        scope_spans.spans.append(span)
    return request


def _metrics_request(metric_name: str, attributes: dict[str, object], value: int) -> ExportMetricsServiceRequest:
    request = ExportMetricsServiceRequest()
    metric = request.resource_metrics.add().scope_metrics.add().metrics.add()
    metric.name = metric_name
    metric.sum.aggregation_temporality = AGGREGATION_TEMPORALITY_CUMULATIVE
    point = metric.sum.data_points.add()
    point.as_int = value
    _set_attributes(point.attributes, attributes)
    return request


def _resource(attributes: dict[str, object]) -> Resource:
    resource = Resource()
    _set_attributes(resource.attributes, attributes)
    return resource


def _span(
    span_id: bytes,
    kind: Any,
    attributes: dict[str, object],
    parent_span_id: bytes | None = None,
) -> Span:
    span = Span(span_id=span_id, kind=kind, name="test-span")
    if parent_span_id is not None:
        span.parent_span_id = parent_span_id
    _set_attributes(span.attributes, attributes)
    return span


def _set_attributes(target: Any, attributes: dict[str, object]) -> None:
    for key, value in attributes.items():
        item = target.add()
        item.key = key
        if isinstance(value, str):
            item.value.string_value = value
        elif isinstance(value, bool):
            item.value.bool_value = value
        elif isinstance(value, int):
            item.value.int_value = value
        else:
            raise TypeError(value)


def _maximal_entity_attributes(service_name: str) -> dict[str, object]:
    registry = _merged_registry()
    return {
        attribute_id: _example_attribute_value(attribute)
        for attribute_id, attribute in registry.attributes_by_id.items()
    } | {
        "service.name": service_name,
        "service.namespace": f"{service_name}-namespace",
        "http.request.method": "POST",
        "http.route": f"/{service_name}/{{id}}",
        "k8s.namespace.name": f"{service_name}-namespace",
        "k8s.pod.uid": f"{service_name}-pod-uid",
        "service.instance.id": f"{service_name}/instance",
    }


def _expected_identifiable_entity_types() -> set[str]:
    registry = _merged_registry()
    return {
        entity.name
        for entity in registry.entities_by_name.values()
        if any(getattr(ref, "role", None) == "identifying" for ref in entity.attributes)
    }


def _merged_registry():
    upstream = load_model_registry(ROOT / "upstream" / "otel-semconv" / "v1.43.0" / "model")
    extension = load_model_registry(ROOT / "model" / "extensions")
    return upstream.model_copy(
        update={
            "groups": (*upstream.groups, *extension.groups),
        }
    )


def _example_attribute_value(attribute: AttributeDefinition) -> object:
    attribute_type = attribute.type
    if attribute_type == "int":
        return 1
    if attribute_type == "boolean":
        return True
    if isinstance(attribute_type, dict):
        members = attribute_type.get("members")
        if isinstance(members, list) and members:
            first_member = members[0]
            if isinstance(first_member, dict) and isinstance(first_member.get("id"), str):
                return first_member["id"]
        return {"value": attribute.id}
    return f"{attribute.id}-value"


def _clock(values: list[float]):
    state = {"index": 0}

    def clock() -> float:
        index = min(state["index"], len(values) - 1)
        state["index"] += 1
        return values[index]

    return clock
