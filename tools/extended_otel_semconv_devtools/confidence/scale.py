"""Rate-controlled service-graph load stage with output validation."""

from __future__ import annotations

import argparse
import math
import re
import threading
import time
import urllib.request
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from confluent_kafka import Consumer, Message, TopicPartition  # type: ignore[import-untyped]
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ScopeSpans, Span
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from extended_otel_semconv.graph.interaction import (
    InteractionDeleteEvent,
    InteractionUpsertEvent,
)

EVENT_TOPIC = "graph.interactions.events"
DLQ_TOPIC = "graph.interactions.dlq"
INPUT_TOPIC = "otel.servicegraph.metrics"
type Event = InteractionUpsertEvent | InteractionDeleteEvent
EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(InteractionUpsertEvent | InteractionDeleteEvent)
PROMETHEUS_SAMPLE = re.compile(r"^(?P<name>[A-Za-z_:][A-Za-z0-9_:]*)(?:\{[^}]*\})?\s+(?P<value>[-+0-9.eE]+)$")


class ScaleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    bootstrap: str = Field(min_length=1)
    flink_url: str = Field(min_length=1)
    collector_metrics_url: str = Field(min_length=1)
    paired_traces_per_second: int = Field(gt=0)
    duration_seconds: int = Field(gt=0)
    batch_size: int = Field(gt=0)
    interaction_cardinality: int = Field(gt=0)
    concurrency: int = Field(gt=0)
    error_ratio: float = Field(ge=0, le=1)
    drain_timeout_seconds: int = Field(gt=0)


class FlinkSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str | None = None
    state: str | None = None
    completed_checkpoints: int = Field(default=0, ge=0)
    failed_checkpoints: int = Field(default=0, ge=0)
    latest_checkpoint_size_bytes: int = Field(default=0, ge=0)
    latest_checkpoint_duration_ms: int = Field(default=0, ge=0)


class CollectorSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    available: bool = True
    refused_or_dropped: float = Field(default=0, ge=0)
    export_failed: float = Field(default=0, ge=0)


class ScaleStageReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    config: ScaleConfig
    started_at_unix_ms: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0)
    attempted_pairs: int = Field(ge=0)
    successful_pairs: int = Field(ge=0)
    producer_errors: int = Field(ge=0)
    expected_interactions: int = Field(ge=0)
    observed_interactions: int = Field(ge=0)
    arrival_ratio: float = Field(ge=0, le=1)
    p50_latency_seconds: float | None = Field(default=None, ge=0)
    p95_latency_seconds: float | None = Field(default=None, ge=0)
    p99_latency_seconds: float | None = Field(default=None, ge=0)
    output_events: int = Field(ge=0)
    duplicate_event_ids: int = Field(ge=0)
    conflicting_event_ids: int = Field(ge=0)
    unexpected_dlq_records: int = Field(ge=0)
    kafka_lag_after_drain: int | None = Field(default=None, ge=0)
    kafka_lag_drain_seconds: float | None = Field(default=None, ge=0)
    flink: FlinkSnapshot
    collector_delta: CollectorSnapshot
    passed: bool
    failures: tuple[str, ...] = ()


class _FlinkJob(BaseModel):
    model_config = ConfigDict(extra="ignore")

    jid: str
    state: str


class _FlinkJobs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    jobs: tuple[_FlinkJob, ...] = ()


class _CheckpointCounts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    completed: int = 0
    failed: int = 0


class _CheckpointLatestCompleted(BaseModel):
    model_config = ConfigDict(extra="ignore")

    checkpointed_size: int = 0
    end_to_end_duration: int = 0


class _CheckpointLatest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    completed: _CheckpointLatestCompleted | None = None


class _CheckpointOverview(BaseModel):
    model_config = ConfigDict(extra="ignore")

    counts: _CheckpointCounts = Field(default_factory=_CheckpointCounts)
    latest: _CheckpointLatest = Field(default_factory=_CheckpointLatest)


class _FlinkVertex(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    parallelism: int = Field(gt=0)


class _FlinkJobDetails(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vertices: tuple[_FlinkVertex, ...] = ()


class _FlinkMetric(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    value: str | None = None


FLINK_METRICS_ADAPTER = TypeAdapter(tuple[_FlinkMetric, ...])


class OutputObserver:
    def __init__(self, bootstrap: str, run_id: str) -> None:
        self._client = f"scale-{run_id}-client"
        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap,
                "group.id": f"scale-observer-{uuid.uuid4().hex}",
                "auto.offset.reset": "latest",
                "enable.auto.commit": False,
            }
        )
        self._consumer.subscribe([EVENT_TOPIC, DLQ_TOPIC])
        self._first_sent: dict[str, float] = {}
        self._first_latency: dict[str, float] = {}
        self._event_payloads: dict[str, str] = {}
        self._seen_event_ids: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._consume, name="scale-output-observer", daemon=True)
        self.output_events = 0
        self.duplicate_event_ids = 0
        self.conflicting_event_ids = 0
        self.unexpected_dlq_records = 0

    def start(self) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self._consumer.poll(0.2)
            if self._consumer.assignment():
                self._thread.start()
                return
        raise RuntimeError("scale output consumer did not receive a partition assignment")

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)
        self._consumer.close()

    def mark_sent(self, server: str, sent_at: float) -> None:
        with self._lock:
            self._first_sent.setdefault(server, sent_at)

    @property
    def expected(self) -> int:
        with self._lock:
            return len(self._first_sent)

    @property
    def observed(self) -> int:
        with self._lock:
            return len(self._first_latency)

    @property
    def latencies(self) -> tuple[float, ...]:
        with self._lock:
            return tuple(self._first_latency.values())

    def _consume(self) -> None:
        while not self._stop.is_set():
            message: Message | None = self._consumer.poll(0.2)
            if message is None:
                continue
            if message.error():
                self.conflicting_event_ids += 1
                continue
            if message.topic() == DLQ_TOPIC:
                self.unexpected_dlq_records += 1
                continue
            raw = message.value()
            key = message.key()
            if not isinstance(raw, bytes) or not isinstance(key, bytes):
                self.conflicting_event_ids += 1
                continue
            payload = raw.decode("utf-8")
            try:
                event = EVENT_ADAPTER.validate_json(payload)
            except ValueError:
                self.conflicting_event_ids += 1
                continue
            if key.decode("utf-8") != event.interaction_id:
                self.conflicting_event_ids += 1
                continue
            with self._lock:
                previous = self._event_payloads.setdefault(event.event_id, payload)
                if previous != payload:
                    self.conflicting_event_ids += 1
                    continue
                if event.event_id in self._seen_event_ids:
                    self.duplicate_event_ids += 1
                else:
                    self._seen_event_ids.add(event.event_id)
                self.output_events += 1
                if not isinstance(event, InteractionUpsertEvent) or event.interaction.client != self._client:
                    continue
                sent_at = self._first_sent.get(event.interaction.server)
                if sent_at is not None:
                    self._first_latency.setdefault(event.interaction.server, max(time.monotonic() - sent_at, 0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://localhost:4318/v1/traces")
    parser.add_argument("--bootstrap", default="localhost:9092")
    parser.add_argument("--flink-url", default="http://localhost:8081")
    parser.add_argument("--collector-metrics-url", default="http://localhost:8888/metrics")
    parser.add_argument("--run-id", default=uuid.uuid4().hex[:12])
    parser.add_argument("--rate", type=int, required=True)
    parser.add_argument("--duration", type=int, required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--cardinality", type=int, default=1_000)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--error-ratio", type=float, default=0.05)
    parser.add_argument("--drain-timeout", type=int, default=120)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    config = ScaleConfig(
        run_id=args.run_id,
        endpoint=args.endpoint,
        bootstrap=args.bootstrap,
        flink_url=args.flink_url,
        collector_metrics_url=args.collector_metrics_url,
        paired_traces_per_second=args.rate,
        duration_seconds=args.duration,
        batch_size=args.batch_size,
        interaction_cardinality=args.cardinality,
        concurrency=args.concurrency,
        error_ratio=args.error_ratio,
        drain_timeout_seconds=args.drain_timeout,
    )
    report = run_stage(config)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(report.model_dump_json(indent=2))
    return 0 if report.passed else 1


def run_stage(config: ScaleConfig) -> ScaleStageReport:
    started_at_unix_ms = int(time.time() * 1_000)
    started = time.monotonic()
    before_collector = collector_snapshot(config.collector_metrics_url)
    observer = OutputObserver(config.bootstrap, config.run_id)
    observer.start()
    total_pairs = config.paired_traces_per_second * config.duration_seconds
    producer_errors = 0
    successful_pairs = 0
    futures: set[Future[int]] = set()
    try:
        with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
            next_index = 0
            while next_index < total_pairs:
                while len(futures) >= config.concurrency * 2:
                    done, futures = wait(futures, return_when="FIRST_COMPLETED")
                    for future in done:
                        try:
                            successful_pairs += future.result()
                        except OSError:
                            producer_errors += config.batch_size
                batch_count = min(config.batch_size, total_pairs - next_index)
                target_time = started + next_index / config.paired_traces_per_second
                delay = target_time - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                request, servers = build_trace_batch(config, next_index, batch_count)
                sent_at = time.monotonic()
                for server in servers:
                    observer.mark_sent(server, sent_at)
                futures.add(executor.submit(send_request, config.endpoint, request, batch_count))
                next_index += batch_count
            done, _ = wait(futures)
            for future in done:
                try:
                    successful_pairs += future.result()
                except OSError:
                    producer_errors += config.batch_size

        drain_started = time.monotonic()
        drain_deadline = drain_started + config.drain_timeout_seconds
        required = math.ceil(observer.expected * 0.999)
        while observer.observed < required and time.monotonic() < drain_deadline:
            time.sleep(0.25)
        remaining_drain_seconds = max(math.ceil(drain_deadline - time.monotonic()), 1)
        lag, lag_wait_seconds = wait_for_kafka_lag(
            config.bootstrap,
            config.flink_url,
            remaining_drain_seconds,
        )
        lag_drain_seconds = time.monotonic() - drain_started if lag == 0 else lag_wait_seconds
    finally:
        observer.stop()
    flink = flink_snapshot(config.flink_url)
    after_collector = collector_snapshot(config.collector_metrics_url)
    collector_delta = CollectorSnapshot(
        available=before_collector.available and after_collector.available,
        refused_or_dropped=max(after_collector.refused_or_dropped - before_collector.refused_or_dropped, 0),
        export_failed=max(after_collector.export_failed - before_collector.export_failed, 0),
    )
    latencies = observer.latencies
    arrival_ratio = observer.observed / observer.expected if observer.expected else 0
    failures = _stage_failures(
        total_pairs,
        producer_errors,
        arrival_ratio,
        _percentile(latencies, 0.95),
        observer,
        lag,
        lag_drain_seconds,
        flink,
        collector_delta,
    )
    return ScaleStageReport(
        config=config,
        started_at_unix_ms=started_at_unix_ms,
        elapsed_seconds=time.monotonic() - started,
        attempted_pairs=total_pairs,
        successful_pairs=successful_pairs,
        producer_errors=producer_errors,
        expected_interactions=observer.expected,
        observed_interactions=observer.observed,
        arrival_ratio=min(arrival_ratio, 1),
        p50_latency_seconds=_percentile(latencies, 0.50),
        p95_latency_seconds=_percentile(latencies, 0.95),
        p99_latency_seconds=_percentile(latencies, 0.99),
        output_events=observer.output_events,
        duplicate_event_ids=observer.duplicate_event_ids,
        conflicting_event_ids=observer.conflicting_event_ids,
        unexpected_dlq_records=observer.unexpected_dlq_records,
        kafka_lag_after_drain=lag,
        kafka_lag_drain_seconds=lag_drain_seconds,
        flink=flink,
        collector_delta=collector_delta,
        passed=not failures,
        failures=failures,
    )


def build_trace_batch(
    config: ScaleConfig,
    start_index: int,
    count: int,
) -> tuple[ExportTraceServiceRequest, tuple[str, ...]]:
    request = ExportTraceServiceRequest()
    servers: set[str] = set()
    scopes: dict[tuple[tuple[str, str], ...], ScopeSpans] = {}
    for sequence in range(start_index, start_index + count):
        identity = sequence % config.interaction_cardinality
        client = f"scale-{config.run_id}-client"
        server = f"scale-{config.run_id}-server-{identity}"
        servers.add(server)
        trace_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{config.run_id}:{sequence}").bytes
        client_span_id = _span_id(config.run_id, sequence, "client")
        timestamp = time.time_ns()
        client_scope = _scope_for_resource(request, scopes, _resource_attributes(config.run_id, client, identity))
        server_scope = _scope_for_resource(request, scopes, _resource_attributes(config.run_id, server, identity))
        client_scope.spans.append(
            _span(trace_id, client_span_id, "client", timestamp, None, False)
        )
        is_error = (sequence % 10_000) < int(config.error_ratio * 10_000)
        server_scope.spans.append(
            _span(
                trace_id,
                _span_id(config.run_id, sequence, "server"),
                "server",
                timestamp + 1_000_000,
                client_span_id,
                is_error,
            )
        )
    return request, tuple(servers)


def send_request(endpoint: str, request: ExportTraceServiceRequest, pair_count: int) -> int:
    http_request = urllib.request.Request(
        endpoint,
        data=request.SerializeToString(),
        headers={"content-type": "application/x-protobuf"},
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=30) as response:
        response.read()
    return pair_count


def wait_for_kafka_lag(
    bootstrap: str,
    flink_url: str,
    timeout_seconds: int,
) -> tuple[int | None, float | None]:
    consumer = Consumer({"bootstrap.servers": bootstrap, "group.id": f"lag-reader-{uuid.uuid4().hex}"})
    started = time.monotonic()
    last_lag: int | None = None
    try:
        while time.monotonic() - started < timeout_seconds:
            offsets = flink_source_offsets(flink_url)
            partitions = consumer.list_topics(INPUT_TOPIC, timeout=10).topics[INPUT_TOPIC].partitions
            lag = 0
            known = len(offsets) == len(partitions)
            for partition_id in partitions:
                current_offset = offsets.get(partition_id)
                if current_offset is None:
                    known = False
                    break
                _, high = consumer.get_watermark_offsets(
                    TopicPartition(INPUT_TOPIC, partition_id),
                    timeout=10,
                    cached=False,
                )
                lag += max(high - current_offset - 1, 0)
            if known and lag == 0:
                return 0, time.monotonic() - started
            last_lag = lag if known else None
            time.sleep(1)
        return last_lag, time.monotonic() - started
    finally:
        consumer.close()


def flink_source_offsets(base_url: str) -> dict[int, int]:
    try:
        jobs = _FlinkJobs.model_validate_json(_http_text(f"{base_url}/jobs/overview"))
        running = next((job for job in jobs.jobs if job.state == "RUNNING"), None)
        if running is None:
            return {}
        details = _FlinkJobDetails.model_validate_json(_http_text(f"{base_url}/jobs/{running.jid}"))
        source = next((vertex for vertex in details.vertices if vertex.name.startswith("Source:")), None)
        if source is None:
            return {}
        offsets: dict[int, int] = {}
        for subtask in range(source.parallelism):
            metrics_url = f"{base_url}/jobs/{running.jid}/vertices/{source.id}/subtasks/{subtask}/metrics"
            metrics = FLINK_METRICS_ADAPTER.validate_json(_http_text(metrics_url))
            for metric in metrics:
                partition = _partition_from_metric_id(metric.id)
                if partition is None:
                    continue
                values = FLINK_METRICS_ADAPTER.validate_json(
                    _http_text(f"{metrics_url}?get={quote(metric.id, safe='')}")
                )
                if values and values[0].value is not None:
                    offsets[partition] = int(values[0].value)
        return offsets
    except (OSError, ValueError):
        return {}


def flink_snapshot(base_url: str) -> FlinkSnapshot:
    try:
        jobs = _FlinkJobs.model_validate_json(_http_text(f"{base_url}/jobs/overview"))
        running = next((job for job in jobs.jobs if job.state == "RUNNING"), jobs.jobs[0] if jobs.jobs else None)
        if running is None:
            return FlinkSnapshot()
        checkpoints = _CheckpointOverview.model_validate_json(
            _http_text(f"{base_url}/jobs/{running.jid}/checkpoints")
        )
        latest = checkpoints.latest.completed
        return FlinkSnapshot(
            job_id=running.jid,
            state=running.state,
            completed_checkpoints=checkpoints.counts.completed,
            failed_checkpoints=checkpoints.counts.failed,
            latest_checkpoint_size_bytes=latest.checkpointed_size if latest else 0,
            latest_checkpoint_duration_ms=latest.end_to_end_duration if latest else 0,
        )
    except (OSError, ValueError):
        return FlinkSnapshot()


def collector_snapshot(url: str) -> CollectorSnapshot:
    try:
        samples = _prometheus_totals(_http_text(url))
    except OSError:
        return CollectorSnapshot(available=False)
    refused_or_dropped = sum(
        value for name, value in samples.items() if "refused" in name or "dropped" in name
    )
    export_failed = sum(value for name, value in samples.items() if "send_failed" in name or "export_failed" in name)
    return CollectorSnapshot(refused_or_dropped=refused_or_dropped, export_failed=export_failed)


def _prometheus_totals(document: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for line in document.splitlines():
        match = PROMETHEUS_SAMPLE.match(line)
        if match is None:
            continue
        name = match.group("name")
        totals[name] = totals.get(name, 0) + float(match.group("value"))
    return totals


def _stage_failures(
    attempted_pairs: int,
    producer_errors: int,
    arrival_ratio: float,
    p95_latency: float | None,
    observer: OutputObserver,
    lag: int | None,
    lag_drain_seconds: float | None,
    flink: FlinkSnapshot,
    collector: CollectorSnapshot,
) -> tuple[str, ...]:
    failures: list[str] = []
    if attempted_pairs and producer_errors / attempted_pairs > 0.001:
        failures.append("producer error rate exceeded 0.1%")
    if arrival_ratio < 0.999:
        failures.append("fewer than 99.9% of expected interactions arrived")
    if p95_latency is None or p95_latency >= 10:
        failures.append("p95 trace-to-first-upsert latency was not below 10 seconds")
    if observer.unexpected_dlq_records:
        failures.append("unexpected DLQ records were emitted")
    if observer.conflicting_event_ids:
        failures.append("conflicting deterministic event IDs were emitted")
    if lag != 0 or lag_drain_seconds is None or lag_drain_seconds > 120:
        failures.append("Kafka lag did not drain within 120 seconds")
    if flink.state != "RUNNING" or flink.failed_checkpoints:
        failures.append("Flink job/checkpoint health failed")
    if collector.refused_or_dropped or collector.export_failed:
        failures.append("Collector refused, dropped, or failed to export telemetry")
    if not collector.available:
        failures.append("Collector self-metrics endpoint was unavailable")
    return tuple(failures)


def _resource_attributes(run_id: str, service: str, identity: int) -> dict[str, str]:
    return {
        "service.name": service,
        "service.namespace": f"scale-{run_id}",
        "service.instance.id": f"{service}/instance-{identity}",
        "k8s.namespace.name": f"scale-{run_id}",
        "k8s.pod.uid": f"scale-{run_id}-pod-{identity}",
    }


def _scope_for_resource(
    request: ExportTraceServiceRequest,
    scopes: dict[tuple[tuple[str, str], ...], ScopeSpans],
    attributes: dict[str, str],
) -> ScopeSpans:
    key = tuple(sorted(attributes.items()))
    existing = scopes.get(key)
    if existing is not None:
        return existing
    resource_spans = request.resource_spans.add()
    resource_spans.resource.CopyFrom(_resource(attributes))
    scope = resource_spans.scope_spans.add()
    scopes[key] = scope
    return scope


def _resource(attributes: dict[str, str]) -> Resource:
    resource = Resource()
    for key, value in attributes.items():
        item = resource.attributes.add()
        item.key = key
        item.value.string_value = value
    return resource


def _span(
    trace_id: bytes,
    span_id: bytes,
    kind: Literal["client", "server"],
    timestamp: int,
    parent_span_id: bytes | None,
    is_error: bool,
) -> Span:
    span = Span(  # pyright: ignore[reportArgumentType]
        trace_id=trace_id,
        span_id=span_id,
        kind=Span.SPAN_KIND_CLIENT if kind == "client" else Span.SPAN_KIND_SERVER,
        name="confidence-request",
        start_time_unix_nano=timestamp,
        end_time_unix_nano=timestamp + 50_000_000,
    )
    if parent_span_id is not None:
        span.parent_span_id = parent_span_id
    if is_error:
        span.status.code = 2  # pyright: ignore[reportAttributeAccessIssue]
    return span


def _span_id(run_id: str, sequence: int, side: str) -> bytes:
    return uuid.uuid5(uuid.NAMESPACE_OID, f"{run_id}:{sequence}:{side}").bytes[:8]


def _percentile(values: tuple[float, ...], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(math.ceil(len(ordered) * quantile) - 1, len(ordered) - 1)
    return ordered[max(index, 0)]


def _partition_from_metric_id(metric_id: str) -> int | None:
    match = re.search(r"\.partition\.(\d+)\.currentOffset$", metric_id)
    return int(match.group(1)) if match is not None else None


def _http_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
