"""Send one malformed message to a service graph metrics Kafka topic."""

from __future__ import annotations

import argparse
import os

from confluent_kafka import Producer  # type: ignore[import-untyped]


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a malformed service graph metric message.")
    parser.add_argument("--bootstrap", default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"))
    parser.add_argument("--topic", default=os.getenv("GRAPH_KAFKA_TOPIC", "otel.servicegraph.metrics"))
    parser.add_argument("--payload", default="{not-json")
    args = parser.parse_args()

    producer = Producer({"bootstrap.servers": args.bootstrap})
    producer.produce(args.topic, value=args.payload.encode("utf-8"))
    producer.flush(10)
    print(f"sent_bad_message topic={args.topic}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
