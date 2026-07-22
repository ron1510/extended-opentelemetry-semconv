# Test Environment

Tests validate the registry, generated semantic entity classes, Collector config,
servicegraph parsing, interaction diff behavior, and Docker Compose wiring.

## Local Checks

```powershell
python scripts\validate_registry.py
python scripts\generate_entities.py --check
python scripts\generate_collector_config.py --check
docker run --rm -v "${PWD}:/workspace" -w /workspace extended-otel-flink-dev:2.2.1 python -m pytest
docker compose config
```

Mandatory static checks run in the pinned Python 3.12/Flink image:

```powershell
docker run --rm -v "${PWD}:/workspace" -w /workspace extended-otel-flink-dev:2.2.1 python -m ruff check .
docker run --rm -v "${PWD}:/workspace" -w /workspace extended-otel-flink-dev:2.2.1 python -m pyright
```

## Runtime Stack

`docker compose up --build` starts:

- `kafka`: Redpanda Kafka-compatible broker on `9092`.
- `otelcol`: stateless trace-ID router receiving OTLP on `4317` and `4318`.
- `otelcol-backend-0` and `otelcol-backend-1`: stateful service-graph
  connectors receiving routed spans.
- `flink-jobmanager`: local Flink JobManager UI on `8081`.
- `flink-taskmanager`: local Flink worker.
- `interaction-diff`: PyFlink interaction diff job.
- `demo`: synthetic trace generator.

The Collector writes servicegraph metrics to `otel.servicegraph.metrics`.
The diff job writes upsert/delete events to `graph.interactions.events` and bad
records to `graph.interactions.dlq`.

Run the deterministic lifecycle test:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke_compose.ps1
```

It builds and starts the stack with a short TTL, waits for one running Flink
job, verifies keyed upsert and delete events, verifies malformed input on the
DLQ, and removes containers and local checkpoint volumes.

Compose checkpoints use a shared local volume. A production Kubernetes
deployment must use durable object-storage checkpoints and internal resource,
storage, security, and monitoring values. The standalone Collector chart
provides the scaled trace-ID routing topology.

Exercise the exact chart in kind:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\kind_up.ps1
powershell -ExecutionPolicy Bypass -File scripts\kind_smoke.ps1
```

The scripts do not fetch dependencies. `kind`, `kubectl`, `helm`, the supported
Python environment, and the Collector and Redpanda images must already exist
through local or approved internal mirrors. The kind node is pinned to Kubernetes 1.29.12 to
avoid silently changing the local API and cgroup requirements with each kind
release.

The failure-recovery smoke test checkpoints an interaction, kills the
TaskManager, and verifies the restored state completes one upsert/delete
lifecycle:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke_restart.ps1
```

Pass `-SkipBuild` after building `extended-otel-flink-dev:2.2.1` to reuse the local
image.

## Stress Helpers

```powershell
python -m extended_otel_semconv_devtools.telemetry.stress --run-id codexstress01 --requests 1200 --workers 16
```

Send a malformed Kafka metric payload:

```powershell
python -m extended_otel_semconv_devtools.telemetry.poison --bootstrap localhost:9092 --topic otel.servicegraph.metrics
```
