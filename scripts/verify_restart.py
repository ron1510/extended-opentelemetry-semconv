"""Verify checkpoint recovery preserves one interaction lifecycle."""

from __future__ import annotations

import argparse
import json
import time
import uuid

from confluent_kafka import Consumer  # type: ignore[import-untyped]

EVENT_TOPIC = "graph.interactions.events"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", default="localhost:9092")
    parser.add_argument("--client", required=True)
    parser.add_argument("--require", action="append", choices=("upsert", "delete"), required=True)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--linger-seconds", type=int, default=3)
    args = parser.parse_args()

    required_operations = set(args.require)
    matching_interaction_ids: set[str] = set()
    event_ids: dict[str, dict[str, set[str]]] = {}
    consumer = Consumer(
        {
            "bootstrap.servers": args.bootstrap,
            "group.id": f"interaction-restart-{uuid.uuid4()}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([EVENT_TOPIC])
    deadline = time.monotonic() + args.timeout_seconds
    completed_at: float | None = None
    try:
        while time.monotonic() < deadline:
            message = consumer.poll(1.0)
            if message is not None:
                if message.error():
                    raise RuntimeError(str(message.error()))
                payload = json.loads(message.value().decode("utf-8"))
                interaction = payload.get("interaction") or {}
                operation = payload.get("operation")
                event_id = payload.get("event_id")
                interaction_id = payload.get("interaction_id")
                if not isinstance(interaction_id, str) or not interaction_id:
                    continue
                if operation == "upsert" and interaction.get("client") == args.client:
                    matching_interaction_ids.add(interaction_id)
                if interaction_id in matching_interaction_ids and operation in required_operations:
                    if not isinstance(event_id, str) or not event_id:
                        raise RuntimeError("matching interaction event has no event_id")
                    by_operation = event_ids.setdefault(interaction_id, {})
                    by_operation.setdefault(operation, set()).add(event_id)

            complete_interactions = _complete_interactions(event_ids, required_operations)
            if complete_interactions:
                completed_at = completed_at or time.monotonic()
                if time.monotonic() - completed_at >= args.linger_seconds:
                    break
    finally:
        consumer.close()

    complete_interactions = _complete_interactions(event_ids, required_operations)
    if not complete_interactions:
        observed = {interaction_id: sorted(by_operation) for interaction_id, by_operation in event_ids.items()}
        raise RuntimeError(f"restart verification failed: required={sorted(required_operations)} observed={observed}")
    print(
        f"Restart verification passed for {args.client}: {sorted(required_operations)} "
        f"interaction_id={sorted(complete_interactions)[0]}"
    )
    return 0


def _complete_interactions(
    event_ids: dict[str, dict[str, set[str]]],
    required_operations: set[str],
) -> set[str]:
    return {
        interaction_id
        for interaction_id, by_operation in event_ids.items()
        if required_operations.issubset(by_operation)
    }


if __name__ == "__main__":
    raise SystemExit(main())
