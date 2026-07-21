"""Verify interaction upsert/delete and DLQ records in the Compose stack."""

from __future__ import annotations

import argparse
import json
import time
import uuid

from confluent_kafka import Consumer, Producer  # type: ignore[import-untyped]

INPUT_TOPIC = "otel.servicegraph.metrics"
EVENT_TOPIC = "graph.interactions.events"
DLQ_TOPIC = "graph.interactions.dlq"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", default="localhost:9092")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    args = parser.parse_args()

    producer = Producer({"bootstrap.servers": args.bootstrap})
    producer.produce(INPUT_TOPIC, key="smoke-dlq", value="{not-json")
    producer.flush(10)

    consumer = Consumer(
        {
            "bootstrap.servers": args.bootstrap,
            "group.id": f"interaction-smoke-{uuid.uuid4()}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([EVENT_TOPIC, DLQ_TOPIC])
    found_upsert = False
    found_delete = False
    found_dlq = False
    deadline = time.monotonic() + args.timeout_seconds
    try:
        while time.monotonic() < deadline and not (found_upsert and found_delete and found_dlq):
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                raise RuntimeError(str(message.error()))
            payload = json.loads(message.value().decode("utf-8"))
            if message.topic() == DLQ_TOPIC:
                found_dlq |= payload.get("event_type") == "interaction_record_rejected"
                continue
            interaction = payload.get("interaction") or {}
            client = interaction.get("client")
            if client == "smoke-client" and payload.get("operation") == "upsert":
                found_upsert = True
            if payload.get("operation") == "delete":
                found_delete = True
    finally:
        consumer.close()

    if not (found_upsert and found_delete and found_dlq):
        raise RuntimeError(
            f"smoke verification failed: upsert={found_upsert} delete={found_delete} dlq={found_dlq}"
        )
    print("Compose smoke test passed: upsert, DLQ, and delete observed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
