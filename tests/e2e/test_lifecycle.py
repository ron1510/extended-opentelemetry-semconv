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

EXPECTED_ENDPOINT_ID = "app.endpoint:checkout-api:payments:POST:%2Fcheckout%2F%7Bcart_id%7D"
FIXED_JOB_ID = "00000000000000000000000000000001"


@pytest.mark.e2e
def test_otlp_telemetry_becomes_entities_then_flink_deletes_them(e2e_environment: E2EEnvironment) -> None:
    collector_url = e2e_environment.start_port_forward("service/servicegraph-collector-router", 4318)
    ui_url = e2e_environment.start_port_forward("service/servicegraph-ui", 8080)
    flink_url = e2e_environment.start_port_forward("service/servicegraph-diff-rest", 8081)

    for seed in range(3):
        _send_trace(f"{collector_url}/v1/traces", seed)

    metric_record = wait_for(
        "service-graph metric in Kafka",
        180,
        lambda: _matching_metric(e2e_environment.kafka_records("otel.servicegraph.metrics")),
    )
    assert "traces_service_graph_request_total" in metric_record[1]

    upsert = wait_for(
        "interaction upsert in Kafka",
        180,
        lambda: _interaction_event(e2e_environment, "upsert"),
    )
    interaction_id = str(upsert[1]["interaction_id"])
    assert upsert[0] == interaction_id
    interaction = _object(upsert[1]["interaction"])
    assert interaction["client"] == "storefront"
    assert interaction["server"] == "checkout-api"

    jobs = _object(e2e_environment.get_json(f"{flink_url}/jobs/overview"))["jobs"]
    assert any(
        isinstance(job, dict) and job.get("jid") == FIXED_JOB_ID and job.get("state") == "RUNNING"
        for job in _array(jobs)
    )

    entities = wait_for(
        "projected entities in the UI",
        60,
        lambda: _expected_entities(e2e_environment.get_json(f"{ui_url}/api/v1/entities?limit=500")),
    )
    entity_ids = {str(_object(entity)["id"]) for entity in entities}
    assert {"service:storefront", "service:checkout-api", EXPECTED_ENDPOINT_ID} <= entity_ids

    graph = _object(e2e_environment.get_json(f"{ui_url}/api/v1/graph"))
    edges = [_object(edge) for edge in _array(graph["edges"])]
    assert any(
        edge.get("source") == "service:storefront"
        and edge.get("target") == "service:checkout-api"
        and edge.get("type") == "calls"
        for edge in edges
    )
    assert any(
        edge.get("source") == "service:checkout-api"
        and edge.get("target") == EXPECTED_ENDPOINT_ID
        and edge.get("type") == "exposes"
        for edge in edges
    )

    deleted = wait_for(
        "Flink interaction delete",
        120,
        lambda: _interaction_event(e2e_environment, "delete", interaction_id),
    )
    assert deleted[0] == interaction_id

    wait_for(
        "UI projection removal",
        60,
        lambda: _projection_is_empty(e2e_environment.get_json(f"{ui_url}/api/v1/status")),
    )
    remaining = _array(e2e_environment.get_json(f"{ui_url}/api/v1/entities?limit=500"))
    assert all(str(_object(entity)["id"]) not in entity_ids for entity in remaining)


def _send_trace(endpoint: str, seed: int) -> None:
    request = _trace_request(seed)
    http_request = urllib.request.Request(
        endpoint,
        data=request.SerializeToString(),
        headers={"content-type": "application/x-protobuf"},
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=10) as response:
        assert response.status == 200
        response.read()


def _trace_request(seed: int) -> ExportTraceServiceRequest:
    rng = random.Random(seed)
    trace_id = rng.randbytes(16)
    client_span_id = rng.randbytes(8)
    server_span_id = rng.randbytes(8)
    start = time.time_ns()
    attributes = (_attribute("http.request.method", "POST"), _attribute("http.route", "/checkout/{cart_id}"))
    client = Span(
        trace_id=trace_id,
        span_id=client_span_id,
        name="POST /checkout/{cart_id}",
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
        name="POST /checkout/{cart_id}",
        kind=Span.SPAN_KIND_SERVER,
        start_time_unix_nano=start + 1_000_000,
        end_time_unix_nano=start + 19_000_000,
        attributes=attributes,
        status=Status(code=Status.STATUS_CODE_OK),
    )
    return ExportTraceServiceRequest(
        resource_spans=(
            _resource_spans("storefront", "shop", "storefront/e2e", client),
            _resource_spans("checkout-api", "payments", "checkout-api/e2e", server),
        )
    )


def _resource_spans(service: str, namespace: str, instance_id: str, span: Span) -> ResourceSpans:
    return ResourceSpans(
        resource=Resource(
            attributes=(
                _attribute("service.name", service),
                _attribute("service.namespace", namespace),
                _attribute("service.instance.id", instance_id),
            )
        ),
        scope_spans=(
            ScopeSpans(
                scope=InstrumentationScope(name="servicegraph-e2e", version="1.0.0"),
                spans=(span,),
            ),
        ),
    )


def _attribute(key: str, value: str) -> KeyValue:
    return KeyValue(key=key, value=AnyValue(string_value=value))


def _matching_metric(records: list[tuple[str, str]]) -> tuple[str, str] | None:
    return next(
        (
            record
            for record in records
            if "traces_service_graph_request_total" in record[1]
            and "storefront" in record[1]
            and "checkout-api" in record[1]
        ),
        None,
    )


def _interaction_event(
    environment: E2EEnvironment,
    operation: str,
    interaction_id: str | None = None,
) -> tuple[str, dict[str, JsonValue]] | None:
    for key, value in environment.kafka_records("graph.interactions.events"):
        try:
            event = json.loads(value)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        typed_event = cast(dict[str, JsonValue], event)
        if typed_event.get("operation") != operation:
            continue
        if interaction_id is not None and typed_event.get("interaction_id") != interaction_id:
            continue
        return key, typed_event
    return None


def _expected_entities(value: JsonValue) -> list[JsonValue] | None:
    entities = _array(value)
    ids = {str(_object(entity)["id"]) for entity in entities}
    expected = {"service:storefront", "service:checkout-api", EXPECTED_ENDPOINT_ID}
    return entities if expected <= ids else None


def _projection_is_empty(value: JsonValue) -> bool:
    status = _object(value)
    return status.get("interactions") == 0 and status.get("entities") == 0 and status.get("edges") == 0


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value
