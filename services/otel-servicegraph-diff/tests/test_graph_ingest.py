from __future__ import annotations

from pathlib import Path
from typing import Any

from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue
from opentelemetry.proto.metrics.v1.metrics_pb2 import AGGREGATION_TEMPORALITY_CUMULATIVE

from extended_otel_semconv.relationships import service_graph_relationships
from otel_servicegraph_diff.engine.metrics import SERVICE_GRAPH_REQUEST_TOTAL
from otel_servicegraph_diff.engine.observation import EdgeObservation, EntityObservation
from otel_servicegraph_diff.ingest.metrics import parse_metrics_request
from otel_servicegraph_diff.ingest.otlp import any_value_to_python
from otel_servicegraph_diff.ingest.service_graph import observations_from_service_graph_datapoint
from tools.semconv_codegen.registry.model import AttributeDefinition, EnumAttributeType
from tools.semconv_codegen.registry.validation import load_model_registry

CODEGEN_ROOT = Path(__file__).resolve().parents[3] / "tools" / "semconv_codegen"


def test_any_value_to_python_converts_otlp_values() -> None:
    value = AnyValue()
    value.kvlist_value.values.add(key="name", value=AnyValue(string_value="checkout"))
    value.kvlist_value.values.add(key="count", value=AnyValue(int_value=3))

    assert any_value_to_python(value) == {"name": "checkout", "count": 3}


def test_parse_service_graph_metric_points() -> None:
    request = _metrics_request(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {
            "client": "frontend",
            "server": "checkout-api",
            "connection_type": "http",
            "server_http.route": "/checkout/{cart_id}",
        },
        value=3,
    )

    points = parse_metrics_request(request.SerializeToString())

    assert len(points) == 1
    assert points[0].name == SERVICE_GRAPH_REQUEST_TOTAL
    assert points[0].attributes["client"] == "frontend"
    assert points[0].value == 3


def test_service_graph_datapoint_formats_entity_and_edge_observations() -> None:
    observations = observations_from_service_graph_datapoint(
        metric_name=SERVICE_GRAPH_REQUEST_TOTAL,
        attributes={
            "client": "frontend",
            "server": "checkout-api",
            "connection_type": "http",
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
        value=7,
        observed_at_unix_nano=1784215260000000000,
        relationships=_relationships(),
    )

    entities = [observation for observation in observations if isinstance(observation, EntityObservation)]
    edges = [observation for observation in observations if isinstance(observation, EdgeObservation)]
    entity_ids = {observation.entity.id for observation in entities}
    edge_keys = {(observation.edge.source, observation.edge.target, observation.edge.type) for observation in edges}

    assert "service:frontend" in entity_ids
    assert "service:checkout-api" in entity_ids
    assert "app.endpoint:checkout-api:payments:POST:%2Fcheckout%2F%7Bcart_id%7D" in entity_ids
    assert ("service:frontend", "service:checkout-api", "calls") in edge_keys
    assert ("k8s.pod:checkout-pod-demo", "service:checkout-api", "runs") in edge_keys
    assert all(observation.source_signal == "service_graph" for observation in observations)


def test_service_graph_datapoint_can_reinforce_all_generated_server_entities() -> None:
    raw_attributes = _maximal_entity_attributes(service_name="max-server")
    metric_attributes = {
        "client": "max-client",
        "server": "max-server",
        "connection_type": "http",
        **{f"client_{key}": value for key, value in _maximal_entity_attributes(service_name="max-client").items()},
        **{f"server_{key}": value for key, value in raw_attributes.items()},
    }

    observations = observations_from_service_graph_datapoint(
        metric_name=SERVICE_GRAPH_REQUEST_TOTAL,
        attributes=metric_attributes,
        value=1,
        observed_at_unix_nano=1784215260000000000,
        relationships=_relationships(),
    )

    entity_types = {
        observation.entity.type
        for observation in observations
        if isinstance(observation, EntityObservation)
    }
    edge_keys = {
        (observation.edge.source, observation.edge.target, observation.edge.type)
        for observation in observations
        if isinstance(observation, EdgeObservation)
    }

    assert _expected_identifiable_entity_types() <= entity_types
    assert ("service:max-client", "service:max-server", "calls") in edge_keys
    assert ("service:max-server", "service.instance:max-server%2Finstance", "contains") in edge_keys
    assert ("k8s.pod:max-server-pod-uid", "service.instance:max-server%2Finstance", "runs") in edge_keys


def test_service_graph_connection_types_map_to_typed_edges() -> None:
    messaging_observations = observations_from_service_graph_datapoint(
        metric_name=SERVICE_GRAPH_REQUEST_TOTAL,
        attributes={"client": "producer", "server": "consumer", "connection_type": "messaging_system"},
        value=2,
        observed_at_unix_nano=1784215260000000000,
        relationships=_relationships(),
    )
    database_observations = observations_from_service_graph_datapoint(
        metric_name=SERVICE_GRAPH_REQUEST_TOTAL,
        attributes={"client": "producer", "server": "database", "connection_type": "database"},
        value=2,
        observed_at_unix_nano=1784215260000000000,
        relationships=_relationships(),
    )

    edge_types = {
        observation.edge.type
        for observation in (*messaging_observations, *database_observations)
        if isinstance(observation, EdgeObservation)
    }
    assert "publishes_to" in edge_types
    assert "queries" in edge_types


def _metrics_request(metric_name: str, attributes: dict[str, object], value: int) -> ExportMetricsServiceRequest:
    request = ExportMetricsServiceRequest()
    metric = request.resource_metrics.add().scope_metrics.add().metrics.add()
    metric.name = metric_name
    metric.sum.aggregation_temporality = AGGREGATION_TEMPORALITY_CUMULATIVE
    point = metric.sum.data_points.add()
    point.as_int = value
    point.start_time_unix_nano = 1
    point.time_unix_nano = 2
    _set_attributes(point.attributes, attributes)
    return request


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


def _relationships():
    return service_graph_relationships()


def _merged_registry():
    upstream = load_model_registry(CODEGEN_ROOT / "upstream" / "otel-semconv" / "v1.43.0" / "model")
    extension = load_model_registry(CODEGEN_ROOT / "model" / "extensions")
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
    if isinstance(attribute_type, str) and attribute_type.endswith("[]"):
        item_type = attribute_type.removesuffix("[]")
        return [1 if item_type == "int" else True if item_type == "boolean" else f"{attribute.id}-value"]
    if isinstance(attribute_type, EnumAttributeType):
        return attribute_type.members[0].value
    return f"{attribute.id}-value"
