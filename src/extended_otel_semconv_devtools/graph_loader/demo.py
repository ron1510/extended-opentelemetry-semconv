"""Emit synthetic OTLP traces for the local Collector and graph demo."""

from __future__ import annotations

import os
import time
import urllib.request
import uuid
from typing import Any

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import Span


def main() -> int:
    endpoint = os.getenv("OTLP_HTTP_ENDPOINT", "http://localhost:4318/v1/traces")
    interval = float(os.getenv("DEMO_INTERVAL_SECONDS", "5"))
    while True:
        request = build_demo_request()
        try:
            http_request = urllib.request.Request(
                endpoint,
                data=request.SerializeToString(),
                headers={"content-type": "application/x-protobuf"},
                method="POST",
            )
            with urllib.request.urlopen(http_request, timeout=10) as response:
                response.read()
        except OSError as exc:
            print(f"failed to send demo trace to {endpoint}: {exc}", flush=True)
        else:
            print(f"sent demo trace to {endpoint}", flush=True)
        time.sleep(interval)


def build_demo_request() -> ExportTraceServiceRequest:
    trace_id = uuid.uuid4().bytes
    frontend_span_id = b"front001"
    checkout_span_id = b"check001"

    request = ExportTraceServiceRequest()
    _add_resource_span(
        request,
        {
            "service.name": "frontend",
            "service.namespace": "web",
            "service.instance.id": "frontend/demo",
            "k8s.namespace.name": "frontend",
            "k8s.pod.uid": "frontend-pod-demo",
        },
        [
            _span(
                trace_id=trace_id,
                span_id=frontend_span_id,
                kind=Span.SPAN_KIND_CLIENT,
                attributes={
                    "http.request.method": "POST",
                    "http.route": "/checkout/{cart_id}",
                },
            )
        ],
    )
    _add_resource_span(
        request,
        {
            "service.name": "checkout-api",
            "service.namespace": "payments",
            "service.instance.id": "checkout/demo",
            "k8s.namespace.name": "checkout",
            "k8s.pod.uid": "checkout-pod-demo",
        },
        [
            _span(
                trace_id=trace_id,
                span_id=checkout_span_id,
                parent_span_id=frontend_span_id,
                kind=Span.SPAN_KIND_SERVER,
                attributes={
                    "http.request.method": "POST",
                    "http.route": "/checkout/{cart_id}",
                },
            )
        ],
    )
    return request


def _add_resource_span(
    request: ExportTraceServiceRequest,
    resource_attributes: dict[str, str],
    spans: list[Span],
) -> None:
    resource_spans = request.resource_spans.add()
    resource_spans.resource.CopyFrom(_resource(resource_attributes))
    scope_spans = resource_spans.scope_spans.add()
    for span in spans:
        scope_spans.spans.append(span)


def _resource(attributes: dict[str, str]) -> Resource:
    resource = Resource()
    _set_attributes(resource.attributes, attributes)
    return resource


def _span(
    trace_id: bytes,
    span_id: bytes,
    kind: Any,
    attributes: dict[str, str],
    parent_span_id: bytes | None = None,
) -> Span:
    span = Span(trace_id=trace_id, span_id=span_id, kind=kind, name="demo-span")
    if parent_span_id is not None:
        span.parent_span_id = parent_span_id
    _set_attributes(span.attributes, attributes)
    return span


def _set_attributes(target: Any, attributes: dict[str, str]) -> None:
    for key, value in attributes.items():
        item = target.add()
        item.key = key
        item.value.string_value = value


if __name__ == "__main__":
    raise SystemExit(main())
