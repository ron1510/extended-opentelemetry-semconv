"""Send stress OTLP traces through the local Collector."""

from __future__ import annotations

import argparse
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import Span


def main() -> int:
    parser = argparse.ArgumentParser(description="Send synthetic stress telemetry to an OTLP HTTP trace endpoint.")
    parser.add_argument("--endpoint", default="http://localhost:4318/v1/traces")
    parser.add_argument("--run-id", default=uuid.uuid4().hex[:12])
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(send_request, args.endpoint, build_stress_request(args.run_id, index))
            for index in range(args.requests)
        ]
        for future in as_completed(futures):
            future.result()
    elapsed = time.monotonic() - started
    print(f"run_id={args.run_id} requests={args.requests} workers={args.workers} elapsed_seconds={elapsed:.2f}")
    return 0


def send_request(endpoint: str, request: ExportTraceServiceRequest) -> None:
    http_request = urllib.request.Request(
        endpoint,
        data=request.SerializeToString(),
        headers={"content-type": "application/x-protobuf"},
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=15) as response:
        response.read()


def build_stress_request(run_id: str, index: int) -> ExportTraceServiceRequest:
    scenario = index % 6
    request = ExportTraceServiceRequest()
    if scenario == 0:
        _add_http_pair(request, run_id, index, "frontend", "checkout", "/checkout/{cart_id}")
    elif scenario == 1:
        _add_http_pair(request, run_id, index, "frontend", "inventory", "/inventory/{sku}")
    elif scenario == 2:
        _add_http_pair(request, run_id, index, "worker", "queue-api", "/jobs/{job_id}", include_k8s=False)
    elif scenario == 3:
        _add_http_pair(request, run_id, index, "same-service", "same-service", "/loop")
    elif scenario == 4:
        _add_orphan_client_span(request, run_id, index)
    else:
        _add_http_pair(request, run_id, index, "frontend", "checkout", "/checkout/{cart_id}", noisy=True)
    return request


def _add_http_pair(
    request: ExportTraceServiceRequest,
    run_id: str,
    index: int,
    client_role: str,
    server_role: str,
    route: str,
    *,
    include_k8s: bool = True,
    noisy: bool = False,
) -> None:
    trace_id = _trace_id(index)
    client_span_id = _span_id(index, 1)
    server_span_id = _span_id(index, 2)
    client_service = f"stress-{run_id}-{client_role}"
    server_service = f"stress-{run_id}-{server_role}"
    client_resource = _resource_attributes(run_id, client_role, client_service, index, include_k8s)
    server_resource = _resource_attributes(run_id, server_role, server_service, index, include_k8s)
    client_attributes = {
        "http.request.method": "POST",
        "http.route": route,
    }
    server_attributes = {
        "http.request.method": "POST",
        "http.route": route,
    }
    if noisy:
        client_attributes.update(
            {
                "user.id": f"user-{run_id}-{index}",
                "session.id": f"session-{uuid.uuid4().hex}",
                "feature_flag.key": f"flag-{index % 50}",
                "app.jank.frame_count": str(index),
            }
        )
    _add_resource_span(
        request,
        client_resource,
        [
            _span(
                trace_id=trace_id,
                span_id=client_span_id,
                kind=Span.SPAN_KIND_CLIENT,
                attributes=client_attributes,
                start_unix_nano=_time_unix_nano(index),
            )
        ],
    )
    _add_resource_span(
        request,
        server_resource,
        [
            _span(
                trace_id=trace_id,
                span_id=server_span_id,
                parent_span_id=client_span_id,
                kind=Span.SPAN_KIND_SERVER,
                attributes=server_attributes,
                start_unix_nano=_time_unix_nano(index) + 1_000_000,
            )
        ],
    )


def _add_orphan_client_span(request: ExportTraceServiceRequest, run_id: str, index: int) -> None:
    service = f"stress-{run_id}-orphan"
    _add_resource_span(
        request,
        _resource_attributes(run_id, "orphan", service, index, include_k8s=True),
        [
            _span(
                trace_id=_trace_id(index),
                span_id=_span_id(index, 3),
                kind=Span.SPAN_KIND_CLIENT,
                attributes={"http.request.method": "GET", "http.route": "/orphan"},
                start_unix_nano=_time_unix_nano(index),
            )
        ],
    )


def _resource_attributes(run_id: str, role: str, service: str, index: int, include_k8s: bool) -> dict[str, str]:
    attributes = {
        "service.name": service,
        "service.namespace": f"stress-{run_id}",
        "service.instance.id": f"{service}/instance-{index % 10}",
    }
    if include_k8s:
        attributes.update(
            {
                "k8s.namespace.name": f"stress-{run_id}",
                "k8s.pod.uid": f"stress-{run_id}-{role}-pod-{index % 20}",
            }
        )
    return attributes


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
    start_unix_nano: int,
    parent_span_id: bytes | None = None,
) -> Span:
    span = Span(
        trace_id=trace_id,
        span_id=span_id,
        kind=kind,
        name="stress-span",
        start_time_unix_nano=start_unix_nano,
        end_time_unix_nano=start_unix_nano + 50_000_000,
    )
    if parent_span_id is not None:
        span.parent_span_id = parent_span_id
    _set_attributes(span.attributes, attributes)
    return span


def _set_attributes(target: Any, attributes: dict[str, str]) -> None:
    for key, value in attributes.items():
        item = target.add()
        item.key = key
        item.value.string_value = value


def _trace_id(index: int) -> bytes:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"stress-trace-{index}").bytes


def _span_id(index: int, salt: int) -> bytes:
    return ((index << 8) + salt).to_bytes(8, "big", signed=False)


def _time_unix_nano(index: int) -> int:
    return 1_784_300_000_000_000_000 + (index * 100_000_000)


if __name__ == "__main__":
    raise SystemExit(main())
