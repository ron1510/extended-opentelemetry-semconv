from __future__ import annotations

import gzip

from fastapi import FastAPI, Request, Response
from google.protobuf.message import DecodeError  # type: ignore[import-untyped]
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceResponse
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse
from starlette import status

from extended_otel_semconv.graph.metrics import parse_metrics_request
from extended_otel_semconv.graph.otlp import parse_trace_request
from extended_otel_semconv.graph.store import DEFAULT_TTL_SECONDS, EntityGraph


def create_app(graph_state: EntityGraph | None = None) -> FastAPI:
    entity_graph = graph_state or EntityGraph(ttl_seconds=DEFAULT_TTL_SECONDS)
    app = FastAPI(title="Extended OpenTelemetry Entity Graph")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/traces")
    async def ingest_traces(request: Request) -> Response:
        body = await _request_body(request)
        if body is None:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        try:
            spans = parse_trace_request(body)
        except DecodeError:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        entity_graph.ingest_spans(spans)
        response = ExportTraceServiceResponse()
        return Response(
            content=response.SerializeToString(),
            media_type="application/x-protobuf",
        )

    @app.post("/v1/metrics")
    async def ingest_metrics(request: Request) -> Response:
        body = await _request_body(request)
        if body is None:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        try:
            points = parse_metrics_request(body)
        except DecodeError:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        entity_graph.ingest_metric_points(points)
        response = ExportMetricsServiceResponse()
        return Response(
            content=response.SerializeToString(),
            media_type="application/x-protobuf",
        )

    @app.get("/entities")
    def entities() -> list[dict[str, object]]:
        return [node.model_dump(mode="json") for node in entity_graph.snapshot().entities]

    @app.get("/edges")
    def edges() -> list[dict[str, object]]:
        return [edge.model_dump(mode="json") for edge in entity_graph.snapshot().edges]

    @app.get("/graph")
    def graph_snapshot() -> dict[str, object]:
        return entity_graph.snapshot().model_dump(mode="json")

    return app


app = create_app()


async def _request_body(request: Request) -> bytes | None:
    body = await request.body()
    try:
        if request.headers.get("content-encoding", "").lower() == "gzip":
            return gzip.decompress(body)
    except gzip.BadGzipFile:
        return None
    return body
