"""Exercise the real Collector, Kafka, and Flink interaction lifecycle."""

from __future__ import annotations

import argparse
import time
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path

from confluent_kafka import Consumer, Message, Producer  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from extended_otel_semconv.graph.interaction import (
    InteractionDeleteEvent,
    InteractionDlqEvent,
    InteractionUpsertEvent,
    TelemetryScalar,
    build_interaction_id,
)
from extended_otel_semconv.graph.metrics import (
    SERVICE_GRAPH_REQUEST_FAILED_TOTAL,
    SERVICE_GRAPH_REQUEST_TOTAL,
)
from extended_otel_semconv_devtools.confidence.otlp_metrics import MetricSample, metrics_json
from extended_otel_semconv_devtools.telemetry.demo import build_demo_request

INPUT_TOPIC = "otel.servicegraph.metrics"
EVENT_TOPIC = "graph.interactions.events"
DLQ_TOPIC = "graph.interactions.dlq"
UNSUPPORTED_METRIC = "not_a_service_graph_metric"

type Event = InteractionUpsertEvent | InteractionDeleteEvent
EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(InteractionUpsertEvent | InteractionDeleteEvent)


class ConsumedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    event: Event


class LifecycleReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    interaction_events: int = Field(ge=1)
    dlq_events: int = Field(ge=3)
    duplicate_event_ids: int = Field(ge=0)
    validated_interactions: tuple[str, ...]


class LifecycleHarness:
    def __init__(self, bootstrap: str, timeout_seconds: int) -> None:
        self._producer = Producer({"bootstrap.servers": bootstrap})
        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap,
                "group.id": f"interaction-confidence-{uuid.uuid4().hex}",
                "auto.offset.reset": "latest",
                "enable.auto.commit": False,
            }
        )
        self._consumer.subscribe([EVENT_TOPIC, DLQ_TOPIC])
        self._timeout_seconds = timeout_seconds
        self.events: list[ConsumedEvent] = []
        self.dlq: list[InteractionDlqEvent] = []
        self._event_payloads: dict[str, str] = {}
        self.duplicate_event_ids = 0
        self._await_assignment()

    def close(self) -> None:
        self._consumer.close()

    def produce_input(self, payload: str, key: str) -> None:
        self._producer.produce(INPUT_TOPIC, key=key, value=payload)
        remaining = self._producer.flush(10)
        if remaining:
            raise RuntimeError(f"Kafka producer did not flush {remaining} records")

    def wait_for(self, predicate: Callable[[LifecycleHarness], bool], label: str, timeout: float | None = None) -> None:
        deadline = time.monotonic() + (timeout or self._timeout_seconds)
        while time.monotonic() < deadline:
            self._poll_once(0.5)
            if predicate(self):
                return
        raise RuntimeError(f"timed out waiting for {label}; events={len(self.events)} dlq={len(self.dlq)}")

    def upserts(self, interaction_id: str) -> list[InteractionUpsertEvent]:
        return [
            item.event
            for item in self.events
            if item.event.interaction_id == interaction_id and isinstance(item.event, InteractionUpsertEvent)
        ]

    def deletes(self, interaction_id: str) -> list[InteractionDeleteEvent]:
        return [
            item.event
            for item in self.events
            if item.event.interaction_id == interaction_id and isinstance(item.event, InteractionDeleteEvent)
        ]

    def _await_assignment(self) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            self._consumer.poll(0.2)
            if self._consumer.assignment():
                return
        raise RuntimeError("Kafka consumer did not receive a partition assignment")

    def _poll_once(self, timeout: float) -> None:
        message: Message | None = self._consumer.poll(timeout)
        if message is None:
            return
        if message.error():
            raise RuntimeError(str(message.error()))
        raw_value = message.value()
        if not isinstance(raw_value, bytes):
            raise RuntimeError("Kafka output had no byte payload")
        payload = raw_value.decode("utf-8")
        if message.topic() == DLQ_TOPIC:
            self.dlq.append(InteractionDlqEvent.model_validate_json(payload))
            return
        event = EVENT_ADAPTER.validate_json(payload)
        key_bytes = message.key()
        if not isinstance(key_bytes, bytes):
            raise RuntimeError("interaction event had no Kafka key")
        key = key_bytes.decode("utf-8")
        if key != event.interaction_id:
            raise RuntimeError(f"Kafka key {key!r} does not match interaction_id {event.interaction_id!r}")
        previous_payload = self._event_payloads.setdefault(event.event_id, payload)
        if previous_payload != payload:
            raise RuntimeError(f"event_id {event.event_id} was reused with a conflicting payload")
        if any(item.event.event_id == event.event_id for item in self.events):
            self.duplicate_event_ids += 1
        self.events.append(ConsumedEvent(key=key, event=event))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", default="localhost:9092")
    parser.add_argument("--otlp-endpoint", default="http://localhost:4318/v1/traces")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = run_lifecycle(args.bootstrap, args.otlp_endpoint, args.timeout_seconds)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(report.model_dump_json(indent=2))
    return 0


def run_lifecycle(bootstrap: str, otlp_endpoint: str, timeout_seconds: int) -> LifecycleReport:
    run_id = uuid.uuid4().hex[:12]
    harness = LifecycleHarness(bootstrap, timeout_seconds)
    validated: list[str] = []
    now = time.time_ns()
    try:
        _verify_real_trace(harness, otlp_endpoint, run_id)
        validated.append("collector_pairing")

        merge_id = _verify_metric_merge(harness, run_id, now)
        validated.append(merge_id)
        duplicate_id = _verify_duplicate_expiry_and_recreation(harness, run_id, now + 10_000_000)
        validated.append(duplicate_id)
        reset_id = _verify_advance_reset_and_out_of_order(harness, run_id, now + 20_000_000)
        validated.append(reset_id)
        _verify_identity_and_multiple_points(harness, run_id, now + 30_000_000)
        validated.append("identity_and_batch")
        _verify_rejections_and_unsupported_metrics(harness, run_id, now + 40_000_000)
        validated.append("dlq_and_ignored_metrics")
    finally:
        harness.close()
    return LifecycleReport(
        run_id=run_id,
        interaction_events=len(harness.events),
        dlq_events=len(harness.dlq),
        duplicate_event_ids=harness.duplicate_event_ids,
        validated_interactions=tuple(validated),
    )


def _verify_real_trace(harness: LifecycleHarness, endpoint: str, run_id: str) -> None:
    client = f"confidence-{run_id}-client"
    server = f"confidence-{run_id}-server"
    request = build_demo_request(client, server)
    noisy_attribute = request.resource_spans[0].scope_spans[0].spans[0].attributes.add()
    noisy_attribute.key = "user.id"
    noisy_attribute.value.string_value = f"never-a-dimension-{run_id}"
    http_request = urllib.request.Request(
        endpoint,
        data=request.SerializeToString(),
        headers={"content-type": "application/x-protobuf"},
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=15) as response:
        response.read()

    harness.wait_for(
        lambda current: any(
            isinstance(item.event, InteractionUpsertEvent) and item.event.interaction.client == client
            for item in current.events
        ),
        "Collector-generated service graph interaction",
    )
    event = next(
        item.event
        for item in harness.events
        if isinstance(item.event, InteractionUpsertEvent) and item.event.interaction.client == client
    )
    assert "user.id" not in event.interaction.dimensions
    assert "client_user.id" not in event.interaction.dimensions
    entity_types = {entity.type for entity in event.interaction.entities}
    if not {"service", "service.instance", "k8s.namespace", "k8s.pod"}.issubset(entity_types):
        raise RuntimeError(f"Collector interaction did not resolve expected semantic entities: {sorted(entity_types)}")


def _verify_metric_merge(harness: LifecycleHarness, run_id: str, timestamp: int) -> str:
    attributes = _attributes(run_id, "merge")
    interaction_id = _interaction_id(attributes)
    harness.produce_input(
        metrics_json(
            (
                _sample(SERVICE_GRAPH_REQUEST_TOTAL, attributes, 10, timestamp, 100),
                _sample(SERVICE_GRAPH_REQUEST_FAILED_TOTAL, attributes, 2, timestamp + 1, 100),
            )
        ),
        f"{run_id}-merge",
    )
    harness.wait_for(
        lambda current: any(
            set(event.interaction.metrics) == {SERVICE_GRAPH_REQUEST_TOTAL, SERVICE_GRAPH_REQUEST_FAILED_TOTAL}
            for event in current.upserts(interaction_id)
        ),
        "request-total and failed-total merge",
    )
    assert {event.interaction_id for event in harness.upserts(interaction_id)} == {interaction_id}
    return interaction_id


def _verify_duplicate_expiry_and_recreation(harness: LifecycleHarness, run_id: str, timestamp: int) -> str:
    attributes = _attributes(run_id, "duplicate")
    interaction_id = _interaction_id(attributes)
    sample = _sample(SERVICE_GRAPH_REQUEST_TOTAL, attributes, 1, timestamp, 200)
    harness.produce_input(metrics_json((sample,)), f"{run_id}-duplicate-first")
    harness.wait_for(lambda current: len(current.upserts(interaction_id)) == 1, "initial duplicate-test upsert")
    time.sleep(2)
    harness.produce_input(
        metrics_json((sample.model_copy(update={"observed_at_unix_nano": timestamp + 2_000_000_000}),)),
        f"{run_id}-duplicate-repeat",
    )
    harness.wait_for(
        lambda current: len(current.deletes(interaction_id)) == 1,
        "expiry after unchanged cumulative value",
        8,
    )
    if len(harness.upserts(interaction_id)) != 1:
        raise RuntimeError("unchanged cumulative observation emitted a duplicate upsert")
    harness.produce_input(
        metrics_json((sample.model_copy(update={"value": 2, "observed_at_unix_nano": timestamp + 3_000_000_000}),)),
        f"{run_id}-duplicate-recreate",
    )
    harness.wait_for(lambda current: len(current.upserts(interaction_id)) == 2, "late recreation upsert")
    return interaction_id


def _verify_advance_reset_and_out_of_order(
    harness: LifecycleHarness,
    run_id: str,
    timestamp: int,
) -> str:
    attributes = _attributes(run_id, "counter")
    interaction_id = _interaction_id(attributes)
    samples = (
        _sample(SERVICE_GRAPH_REQUEST_TOTAL, attributes, 5, timestamp + 2, 300),
        _sample(SERVICE_GRAPH_REQUEST_TOTAL, attributes, 6, timestamp + 1, 300),
        _sample(SERVICE_GRAPH_REQUEST_TOTAL, attributes, 6, timestamp + 3, 300),
        _sample(SERVICE_GRAPH_REQUEST_TOTAL, attributes, 1, timestamp + 4, 400),
    )
    kafka_key = f"{run_id}-counter"
    for sample in samples:
        harness.produce_input(metrics_json((sample,)), kafka_key)
    harness.wait_for(lambda current: len(current.upserts(interaction_id)) == 3, "advance and counter reset upserts")
    values = [event.interaction.metrics[SERVICE_GRAPH_REQUEST_TOTAL] for event in harness.upserts(interaction_id)]
    if values != [5, 6, 1]:
        raise RuntimeError(f"out-of-order/counter sequence regressed state: {values}")
    return interaction_id


def _verify_identity_and_multiple_points(harness: LifecycleHarness, run_id: str, timestamp: int) -> None:
    first = _attributes(run_id, "identity-a")
    second = {**first, "server_k8s.namespace.name": f"{run_id}-identity-b"}
    first_id = _interaction_id(first)
    second_id = _interaction_id(second)
    if first_id == second_id:
        raise RuntimeError("identity-relevant dimension mutation did not change interaction_id")
    harness.produce_input(
        metrics_json(
            (
                _sample(SERVICE_GRAPH_REQUEST_TOTAL, first, 1, timestamp, 500),
                _sample(SERVICE_GRAPH_REQUEST_TOTAL, second, 1, timestamp + 1, 500),
                MetricSample(
                    name=UNSUPPORTED_METRIC,
                    attributes=first,
                    value=99,
                    observed_at_unix_nano=timestamp + 2,
                    start_time_unix_nano=500,
                ),
            )
        ),
        f"{run_id}-batch",
    )
    harness.wait_for(
        lambda current: bool(current.upserts(first_id)) and bool(current.upserts(second_id)),
        "independent datapoints from one OTLP envelope",
    )


def _verify_rejections_and_unsupported_metrics(
    harness: LifecycleHarness,
    run_id: str,
    timestamp: int,
) -> None:
    attributes = _attributes(run_id, "rejected")
    before = len(harness.dlq)
    harness.produce_input("{not-json", f"{run_id}-malformed")
    harness.produce_input(
        metrics_json((_sample(SERVICE_GRAPH_REQUEST_TOTAL, attributes, 1, None, 600),)),
        f"{run_id}-missing-timestamp",
    )
    harness.produce_input(
        metrics_json(
            (
                MetricSample(
                    name=UNSUPPORTED_METRIC,
                    attributes=attributes,
                    value=1,
                    observed_at_unix_nano=timestamp,
                    start_time_unix_nano=600,
                ),
            )
        ),
        f"{run_id}-unsupported-only",
    )
    harness.wait_for(lambda current: len(current.dlq) >= before + 3, "three rejected input contracts")


def _attributes(run_id: str, suffix: str) -> dict[str, TelemetryScalar]:
    return {
        "client": f"confidence-{run_id}-client",
        "server": f"confidence-{run_id}-{suffix}",
        "connection_type": "virtual_node",
        "client_service.namespace": f"confidence-{run_id}",
        "server_service.namespace": f"confidence-{run_id}",
        "client_k8s.namespace.name": f"confidence-{run_id}",
        "server_k8s.namespace.name": f"confidence-{run_id}",
    }


def _sample(
    name: str,
    attributes: dict[str, TelemetryScalar],
    value: int,
    timestamp: int | None,
    start_timestamp: int,
) -> MetricSample:
    return MetricSample(
        name=name,
        attributes=attributes,
        value=value,
        observed_at_unix_nano=timestamp,
        start_time_unix_nano=start_timestamp,
    )


def _interaction_id(attributes: dict[str, TelemetryScalar]) -> str:
    dimensions = {
        key: value
        for key, value in attributes.items()
        if key not in {"client", "server", "connection_type"}
    }
    return build_interaction_id(
        str(attributes["client"]),
        str(attributes["server"]),
        "calls",
        dimensions,
    )


if __name__ == "__main__":
    raise SystemExit(main())
