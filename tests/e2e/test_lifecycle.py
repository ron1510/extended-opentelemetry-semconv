from __future__ import annotations

import json
import random
import time
import urllib.request
from typing import cast

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, InstrumentationScope, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span, Status

from tests.e2e.environment import E2EEnvironment, JsonValue, wait_for

ROUTE_A = "/checkout/{cart_id}"
ROUTE_B = "/checkout/{cart_id}/confirm"
ENDPOINT_A = "app.endpoint:checkout-api:payments:POST:%2Fcheckout%2F%7Bcart_id%7D"
ENDPOINT_B = "app.endpoint:checkout-api:payments:POST:%2Fcheckout%2F%7Bcart_id%7D%2Fconfirm"
FIXED_JOB_ID = "00000000000000000000000000000001"


@pytest.mark.e2e
def test_telemetry_becomes_shared_elements_then_expires_by_contributor(
    e2e_environment: E2EEnvironment,
) -> None:
    collector_url = e2e_environment.start_port_forward("service/servicegraph-collector-router", 4318)
    ui_url = e2e_environment.start_port_forward("service/servicegraph-ui", 8080)
    flink_url = e2e_environment.start_port_forward("service/servicegraph-diff-rest", 8081)

    for seed in range(3):
        _send_trace(f"{collector_url}/v1/traces", seed, ROUTE_A, {"service.version": "2.4"})
        _send_trace(f"{collector_url}/v1/traces", seed + 10, ROUTE_B, {"service.criticality": "tier-1"})

    wait_for(
        "both route metrics in Kafka",
        180,
        lambda: _both_metrics(e2e_environment.kafka_records("otel.servicegraph.metrics")),
    )
    checkout = wait_for(
        "merged checkout service element",
        180,
        lambda: _node_upsert_with_attributes(
            e2e_environment,
            "service:checkout-api",
            {"service.version": "2.4", "service.criticality": "tier-1"},
        ),
    )
    assert checkout[0] == "service:checkout-api"
    dependency = wait_for(
        "shared dependency edge",
        180,
        lambda: _dependency_upsert(e2e_environment),
    )
    assert dependency[0] == _object(dependency[1]["element"])["id"]

    jobs = _array(_object(e2e_environment.get_json(f"{flink_url}/jobs/overview"))["jobs"])
    assert any(
        isinstance(job, dict) and job.get("jid") == FIXED_JOB_ID and job.get("state") == "RUNNING"
        for job in jobs
    )

    elements = wait_for(
        "projected graph elements",
        60,
        lambda: _expected_elements(e2e_environment.get_json(f"{ui_url}/api/v1/elements?limit=500")),
    )
    element_ids = {str(_object(element)["id"]) for element in elements}
    assert {"service:storefront", "service:checkout-api", ENDPOINT_A, ENDPOINT_B} <= element_ids
    _assert_expected_edges(e2e_environment.get_json(f"{ui_url}/api/v1/graph"))

    deadline = time.monotonic() + 30
    seed = 100
    while time.monotonic() < deadline:
        _send_trace(f"{collector_url}/v1/traces", seed, ROUTE_B, {"service.criticality": "tier-1"})
        seed += 1
        time.sleep(3)

    remaining = wait_for(
        "route A expires while shared elements remain",
        90,
        lambda: _partial_projection(e2e_environment.get_json(f"{ui_url}/api/v1/elements?limit=500")),
    )
    remaining_by_id = {str(_object(item)["id"]): _object(item) for item in remaining}
    assert ENDPOINT_A not in remaining_by_id
    assert ENDPOINT_B in remaining_by_id
    checkout_attributes = _object(remaining_by_id["service:checkout-api"]["attributes"])
    assert checkout_attributes.get("service.criticality") == "tier-1"
    assert "service.version" not in checkout_attributes
    _assert_expected_edges(e2e_environment.get_json(f"{ui_url}/api/v1/graph"))

    wait_for(
        "final contributor expiry removes the projection",
        120,
        lambda: _projection_is_empty(e2e_environment.get_json(f"{ui_url}/api/v1/status")),
    )
    assert _element_event(e2e_environment, "delete", "service:checkout-api") is not None


def _send_trace(endpoint: str, seed: int, route: str, server_attributes: dict[str, str]) -> None:
    request = _trace_request(seed, route, server_attributes)
    http_request = urllib.request.Request(
        endpoint,
        data=request.SerializeToString(),
        headers={"content-type": "application/x-protobuf"},
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=10) as response:
        assert response.status == 200
        response.read()


def _trace_request(seed: int, route: str, server_attributes: dict[str, str]) -> ExportTraceServiceRequest:
    rng = random.Random(seed)
    trace_id = rng.randbytes(16)
    client_span_id = rng.randbytes(8)
    server_span_id = rng.randbytes(8)
    start = time.time_ns()
    attributes = (_attribute("http.request.method", "POST"), _attribute("http.route", route))
    client = Span(
        trace_id=trace_id,
        span_id=client_span_id,
        name=f"POST {route}",
        kind=Span.SPAN_KIND_CLIENT,
        start_time_unix_nano=start,
        end_time_unix_nano=start + 20_000_000,
        attributes=attributes,
        status=Status(code=Status.STATUS_CODE_OK),
    )
    server = Span(
        trace_id=trace_id,
        span_id=server_span_id,
        parent_span_id=client_span_id,
        name=f"POST {route}",
        kind=Span.SPAN_KIND_SERVER,
        start_time_unix_nano=start + 1_000_000,
        end_time_unix_nano=start + 19_000_000,
        attributes=attributes,
        status=Status(code=Status.STATUS_CODE_OK),
    )
    return ExportTraceServiceRequest(
        resource_spans=(
            _resource_spans("storefront", "shop", "storefront/e2e", client, {}),
            _resource_spans("checkout-api", "payments", "checkout-api/e2e", server, server_attributes),
        )
    )


def _resource_spans(
    service: str,
    namespace: str,
    instance_id: str,
    span: Span,
    extra: dict[str, str],
) -> ResourceSpans:
    attributes = [
        _attribute("service.name", service),
        _attribute("service.namespace", namespace),
        _attribute("service.instance.id", instance_id),
    ]
    attributes.extend(_attribute(key, value) for key, value in extra.items())
    return ResourceSpans(
        resource=Resource(attributes=attributes),
        scope_spans=(
            ScopeSpans(
                scope=InstrumentationScope(name="servicegraph-e2e", version="1.0.0"),
                spans=(span,),
            ),
        ),
    )


def _attribute(key: str, value: str) -> KeyValue:
    return KeyValue(key=key, value=AnyValue(string_value=value))


def _both_metrics(records: list[tuple[str, str]]) -> bool:
    values = [value for _, value in records if "traces_service_graph_request_total" in value]
    return any(ROUTE_A in value for value in values) and any(ROUTE_B in value for value in values)


def _node_upsert_with_attributes(
    environment: E2EEnvironment,
    element_id: str,
    expected: dict[str, str],
) -> tuple[str, dict[str, JsonValue]] | None:
    for record in reversed(environment.kafka_records("graph.elements.events")):
        event = _event(record)
        if event is None or event.get("operation") != "upsert" or event.get("element_id") != element_id:
            continue
        element = _object(event["element"])
        attributes = _object(element["attributes"])
        if all(attributes.get(key) == value for key, value in expected.items()):
            return record[0], event
    return None


def _dependency_upsert(environment: E2EEnvironment) -> tuple[str, dict[str, JsonValue]] | None:
    for record in reversed(environment.kafka_records("graph.elements.events")):
        event = _event(record)
        if event is None or event.get("operation") != "upsert":
            continue
        element = _object(event["element"])
        if (
            element.get("kind") == "edge"
            and element.get("type") == "calls"
            and element.get("source_id") == "service:storefront"
            and element.get("target_id") == "service:checkout-api"
        ):
            return record[0], event
    return None


def _element_event(
    environment: E2EEnvironment,
    operation: str,
    element_id: str,
) -> tuple[str, dict[str, JsonValue]] | None:
    for record in reversed(environment.kafka_records("graph.elements.events")):
        event = _event(record)
        if event is not None and event.get("operation") == operation and event.get("element_id") == element_id:
            return record[0], event
    return None


def _event(record: tuple[str, str]) -> dict[str, JsonValue] | None:
    try:
        value = json.loads(record[1])
    except json.JSONDecodeError:
        return None
    return cast(dict[str, JsonValue], value) if isinstance(value, dict) else None


def _expected_elements(value: JsonValue) -> list[JsonValue] | None:
    elements = _array(value)
    ids = {str(_object(item)["id"]) for item in elements}
    return elements if {"service:storefront", "service:checkout-api", ENDPOINT_A, ENDPOINT_B} <= ids else None


def _partial_projection(value: JsonValue) -> list[JsonValue] | None:
    elements = _array(value)
    ids = {str(_object(item)["id"]) for item in elements}
    return elements if ENDPOINT_A not in ids and {"service:checkout-api", ENDPOINT_B} <= ids else None


def _assert_expected_edges(value: JsonValue) -> None:
    edges = [_object(edge) for edge in _array(_object(value)["edges"])]
    assert any(
        edge.get("source") == "service:storefront"
        and edge.get("target") == "service:checkout-api"
        and edge.get("type") == "calls"
        for edge in edges
    )
    assert any(
        edge.get("source") == "service:checkout-api"
        and edge.get("target") == ENDPOINT_B
        and edge.get("type") == "exposes"
        for edge in edges
    )


def _projection_is_empty(value: JsonValue) -> bool:
    status = _object(value)
    return status.get("elements") == 0 and status.get("nodes") == 0 and status.get("edges") == 0


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value
