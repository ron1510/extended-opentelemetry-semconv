"""Render a concise Markdown summary from machine-readable confidence evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=Path("reports/confidence"))
    parser.add_argument("--output", type=Path, default=Path("reports/confidence/README.md"))
    parser.add_argument("--json-output", type=Path, default=Path("reports/confidence/confidence.json"))
    args = parser.parse_args()
    stages = [_load(path) for path in sorted(args.reports.glob("scale-*.json"))]
    artifact = _load(args.reports / "artifacts.json")
    lifecycle = _load(args.reports / "lifecycle.json")
    runtime = _load(args.reports / "runtime.json")
    passing_rates = [
        int(cast(dict[str, object], stage["config"])["paired_traces_per_second"])
        for stage in stages
        if stage.get("passed") is True and path_kind(stage) == "throughput"
    ]
    highest = max(passing_rates, default=0)
    lines = [
        "# Java 11 Local Confidence Report",
        "",
        "This report covers the source-free wheel-installed local Collector/Kafka/Flink path only.",
        "",
        "## Artifacts",
        "",
    ]
    for wheel in cast(list[dict[str, object]], artifact["wheels"]):
        lines.append(f"- `{wheel['filename']}`: `{wheel['sha256']}`")
    lines.extend(
        [
            "",
            "## Functional Lifecycle",
            "",
            f"- Interaction events: {lifecycle['interaction_events']}",
            f"- DLQ events: {lifecycle['dlq_events']}",
            f"- Deterministic duplicate deliveries: {lifecycle['duplicate_event_ids']}",
            "",
            "## Scale",
            "",
            f"- Highest passing local throughput: {highest:,} paired traces/second",
            f"- Suggested ceiling from this machine: {highest // 2:,} paired traces/second",
            "",
            "| Stage | Rate | Cardinality | Arrival | p95 | Lag | Checkpoints | Result |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for stage in stages:
        config = cast(dict[str, object], stage["config"])
        flink = cast(dict[str, object], stage["flink"])
        p95 = stage.get("p95_latency_seconds")
        p95_text = "n/a" if p95 is None else f"{float(p95):.3f}s"
        lines.append(
            f"| {path_kind(stage)} | {config['paired_traces_per_second']} | "
            f"{config['interaction_cardinality']} | {float(stage['arrival_ratio']):.4f} | "
            f"{p95_text} | {stage.get('kafka_lag_after_drain')} | "
            f"{flink['completed_checkpoints']} | {'PASS' if stage['passed'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Scope Limits",
            "",
            "No claim is made for HA, checkpoint restoration, broker-outage recovery, OpenShift rollout, "
            "NiFi/MongoDB correctness, or performance on the internal cluster.",
            "",
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    aggregate = {
        "schema_version": "1.0",
        "artifacts": artifact,
        "runtime": runtime,
        "lifecycle": lifecycle,
        "scale_stages": stages,
        "highest_passing_pairs_per_second": highest,
        "recommended_max_pairs_per_second": highest // 2,
        "excluded_claims": [
            "high availability and checkpoint restoration",
            "Kafka broker outage recovery",
            "OpenShift rollout readiness",
            "NiFi and MongoDB correctness",
            "performance on the internal cluster",
        ],
    }
    args.json_output.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def path_kind(stage: dict[str, object]) -> str:
    run_id = str(cast(dict[str, object], stage["config"])["run_id"])
    return run_id.partition("-")[0]


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} did not contain a JSON object")
    return cast(dict[str, object], value)


if __name__ == "__main__":
    raise SystemExit(main())
