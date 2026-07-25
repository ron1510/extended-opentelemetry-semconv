from __future__ import annotations

import os
import random
import time
import urllib.request
from dataclasses import dataclass
from typing import Final

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, InstrumentationScope, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span, Status


@dataclass(frozen=True, slots=True)
class Edge:
    client: str
    server: str
    method: str
    route: str


EDGES: Final[tuple[Edge, ...]] = (
    Edge("storefront", "catalog-api", "GET", "/products/{product_id}"),
    Edge("storefront", "identity-api", "POST", "/sessions"),
    Edge("storefront", "checkout-api", "POST", "/checkout"),
    Edge("checkout-api", "inventory-api", "POST", "/reservations"),
    Edge("checkout-api", "payments-api", "POST", "/payments"),
    Edge("checkout-api", "shipping-api", "POST", "/shipments"),
    Edge("orders-worker", "inventory-api", "PATCH", "/stock/{sku}"),
    Edge("payments-api", "fraud-api", "POST", "/checks"),
    Edge("shipping-api", "notifications-api", "POST", "/notifications"),
    Edge("catalog-worker", "catalog-api", "PUT", "/products/{product_id}"),
)


@dataclass(frozen=True, slots=True)
class Config:
    endpoint: str
    emit_interval_seconds: float
    topology_change_interval_seconds: float
    initial_edges: int
    max_active_edges: int
    requests_per_tick: int
    error_rate: float
    namespace: str
    instance_id: str
    random_seed: int | None

    @classmethod
    def from_env(cls) -> Config:
        seed_value = os.getenv("DEMO_RANDOM_SEED", "").strip()
        config = cls(
            endpoint=os.getenv(
                "OTLP_HTTP_ENDPOINT",
                "http://servicegraph-collector-router:4318/v1/traces",
            ),
            emit_interval_seconds=float(os.getenv("DEMO_EMIT_INTERVAL_SECONDS", "2")),
            topology_change_interval_seconds=float(
                os.getenv("DEMO_TOPOLOGY_CHANGE_INTERVAL_SECONDS", "20")
            ),
            initial_edges=int(os.getenv("DEMO_INITIAL_EDGES", "2")),
            max_active_edges=int(os.getenv("DEMO_MAX_ACTIVE_EDGES", "6")),
            requests_per_tick=int(os.getenv("DEMO_REQUESTS_PER_TICK", "3")),
            error_rate=float(os.getenv("DEMO_ERROR_RATE", "0.08")),
            namespace=os.getenv("DEMO_SERVICE_NAMESPACE", "shop"),
            instance_id=os.getenv("DEMO_INSTANCE_ID", "live-demo"),
            random_seed=int(seed_value) if seed_value else None,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.endpoint.startswith(("http://", "https://")):
            raise ValueError("OTLP_HTTP_ENDPOINT must use http:// or https://")
        if self.emit_interval_seconds <= 0 or self.topology_change_interval_seconds <= 0:
            raise ValueError("demo intervals must be positive")
        if not 1 <= self.initial_edges <= self.max_active_edges < len(EDGES):
            raise ValueError("edge counts must satisfy 1 <= initial <= max < available")
        if self.requests_per_tick < 1:
            raise ValueError("DEMO_REQUESTS_PER_TICK must be positive")
        if not 0 <= self.error_rate <= 1:
            raise ValueError("DEMO_ERROR_RATE must be between 0 and 1")


class Topology:
    def __init__(
        self,
        edges: tuple[Edge, ...],
        initial_edges: int,
        max_active_edges: int,
        rng: random.Random,
    ) -> None:
        shuffled = list(edges)
        rng.shuffle(shuffled)
        self._rng = rng
        self._max_active_edges = max_active_edges
        self._active = shuffled[:initial_edges]
        self._inactive = shuffled[initial_edges:]
        self._pending = list(self._active)

    @property
    def active(self) -> tuple[Edge, ...]:
        return tuple(self._active)

    def advance(self) -> tuple[Edge | None, Edge]:
        introduced = self._inactive.pop(0)
        retired: Edge | None = None
        if len(self._active) >= self._max_active_edges:
            retired = self._rng.choice(self._active)
            self._active.remove(retired)
            self._inactive.append(retired)

        self._active.append(introduced)
        self._pending.append(introduced)
        return retired, introduced

    def sample(self, count: int) -> tuple[Edge, ...]:
        selected: list[Edge] = []
        while self._pending and len(selected) < count:
            selected.append(self._pending.pop(0))
        selected.extend(self._rng.choice(self._active) for _ in range(count - len(selected)))
        return tuple(selected)


def build_request(
    edges: tuple[Edge, ...],
    *,
    namespace: str,
    instance_id: str,
    error_rate: float,
    rng: random.Random,
) -> ExportTraceServiceRequest:
    request = ExportTraceServiceRequest()
    for edge in edges:
        _add_trace(request, edge, namespace, instance_id, error_rate, rng)
    return request


def _add_trace(
    request: ExportTraceServiceRequest,
    edge: Edge,
    namespace: str,
    instance_id: str,
    error_rate: float,
    rng: random.Random,
) -> None:
    trace_id = rng.randbytes(16)
    client_span_id = rng.randbytes(8)
    server_span_id = rng.randbytes(8)
    start = time.time_ns()
    duration = rng.randint(5, 250) * 1_000_000
    failed = rng.random() < error_rate
    status = Status.STATUS_CODE_ERROR if failed else Status.STATUS_CODE_OK
    attributes = (_attribute("http.request.method", edge.method), _attribute("http.route", edge.route))

    client_span = Span(
        trace_id=trace_id,
        span_id=client_span_id,
        name=f"{edge.method} {edge.route}",
        kind=Span.SPAN_KIND_CLIENT,
        start_time_unix_nano=start,
        end_time_unix_nano=start + duration,
        attributes=attributes,
        status=Status(code=status),
    )
    server_span = Span(
        trace_id=trace_id,
        span_id=server_span_id,
        parent_span_id=client_span_id,
        name=f"{edge.method} {edge.route}",
        kind=Span.SPAN_KIND_SERVER,
        start_time_unix_nano=start + 1_000_000,
        end_time_unix_nano=start + max(duration - 1_000_000, 1),
        attributes=attributes,
        status=Status(code=status),
    )
    request.resource_spans.extend(
        (
            _resource_spans(edge.client, namespace, instance_id, client_span),
            _resource_spans(edge.server, namespace, instance_id, server_span),
        )
    )


def _resource_spans(service: str, namespace: str, instance_id: str, span: Span) -> ResourceSpans:
    return ResourceSpans(
        resource=Resource(
            attributes=(
                _attribute("service.name", service),
                _attribute("service.namespace", namespace),
                _attribute("service.instance.id", f"{service}/{instance_id}"),
            )
        ),
        scope_spans=(
            ScopeSpans(
                scope=InstrumentationScope(name="extended-otel-servicegraph-demo", version="0.1.1"),
                spans=(span,),
            ),
        ),
    )


def _attribute(key: str, value: str) -> KeyValue:
    return KeyValue(key=key, value=AnyValue(string_value=value))


def _send(endpoint: str, request: ExportTraceServiceRequest) -> None:
    http_request = urllib.request.Request(
        endpoint,
        data=request.SerializeToString(),
        headers={"content-type": "application/x-protobuf"},
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=10) as response:
        response.read()


def _edge_name(edge: Edge) -> str:
    return f"{edge.client}->{edge.server}"


def run(config: Config) -> None:
    rng = random.Random(config.random_seed)
    topology = Topology(EDGES, config.initial_edges, config.max_active_edges, rng)
    next_change = time.monotonic() + config.topology_change_interval_seconds
    print(f"active topology: {', '.join(_edge_name(edge) for edge in topology.active)}", flush=True)

    while True:
        now = time.monotonic()
        if now >= next_change:
            retired, introduced = topology.advance()
            change = f"introduced {_edge_name(introduced)}"
            if retired is not None:
                change += f"; retired {_edge_name(retired)}"
            print(f"{change}; active edges={len(topology.active)}", flush=True)
            next_change = now + config.topology_change_interval_seconds

        edges = topology.sample(config.requests_per_tick)
        request = build_request(
            edges,
            namespace=config.namespace,
            instance_id=config.instance_id,
            error_rate=config.error_rate,
            rng=rng,
        )
        try:
            _send(config.endpoint, request)
        except OSError as exc:
            print(f"failed to export traces to {config.endpoint}: {exc}", flush=True)
        else:
            print(f"exported {len(edges)} traces", flush=True)
        time.sleep(config.emit_interval_seconds)


def main() -> int:
    run(Config.from_env())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
