# Extended OpenTelemetry Semantic Conventions

This project extends the OpenTelemetry semantic convention entity registry
without redefining entities that OpenTelemetry already owns.

The runtime path is a streaming interaction diff engine:

```text
OTLP traces
  -> OpenTelemetry Collector service_graph connector
  -> Kafka topic otel.servicegraph.metrics
  -> PyFlink interaction diff state
  -> Kafka topic graph.interactions.events
  -> NiFi / MongoDB materialization outside this repo
```

Postgres is intentionally not part of the runtime.

## Published Packages

- `extended-opentelemetry-semconv` owns the registry, generated Pydantic
  entities, relationships, OTLP observation parsing, and pure interaction diff
  models.
- `otel-servicegraph-diff` owns validated runtime settings and the PyFlink/Kafka
  application wiring.

The semantic package has no PyFlink, Kafka client, or environment-settings
dependency. The Flink application depends on the semantic package through its
published Python package contract.

## Repository Layout

- `upstream/otel-semconv/v1.43.0/model/` is the pinned upstream OpenTelemetry model snapshot.
- `model/extensions/` contains extension attributes, entities, and relationships.
- `packages/extended-opentelemetry-semconv/` is the independently buildable semantic library.
- `apps/otel-servicegraph-diff/` is the independently buildable PyFlink application.
- `tools/extended_otel_semconv_devtools/` contains local telemetry and Kafka helpers.
- `deploy/local/otelcol.yaml` is generated from the merged registry.
- `deploy/openshift/` contains the air-gapped, namespace-scoped OpenShift deployment.
- `scripts/` contains repository validation and artifact generation utilities.
- `tests/` contains semantic-library and architecture tests; application tests
  live beside the application.

## Package Builds

Build the packages independently with any PEP 517 frontend:

```powershell
python -m pip wheel --no-deps --wheel-dir dist packages\extended-opentelemetry-semconv
python -m pip wheel --no-deps --wheel-dir dist apps\otel-servicegraph-diff
```

For local development, install both as editable packages:

```powershell
python -m pip install -e packages\extended-opentelemetry-semconv -e apps\otel-servicegraph-diff
```

## Generate

```powershell
python scripts\generate_entities.py
python scripts\generate_collector_config.py
```

Check generated files:

```powershell
python scripts\generate_entities.py --check
python scripts\generate_collector_config.py --check
```

## Local Pipeline

The supported runtime is Python `3.12.13`, Java `11`, Apache Flink/PyFlink
`2.2.1`, and the Flink Kafka connector `5.0.0-2.2`. Compose builds the
Dockerfile's local development target and runs the same behavior as the
production application:

```powershell
docker compose up --build
```

The stack starts Redpanda Kafka, the OpenTelemetry Collector, Flink
JobManager/TaskManager, the interaction diff job, and a demo trace generator.
The Kafka connector is a Flink client dependency, not Kafka Connect. Maven
resolves it while building the image; the Kafka cluster does not need Kafka
Connect enabled.

The Dockerfile's default `runtime` target is deliberately smaller than the
Compose development target. It contains Python, PyFlink, dependencies resolved
from the package metadata, the Kafka connector, and the private serializer,
but no application source or test tooling. Both deployable targets default to
the non-root `flink` user and contain no root setup step. OpenShift may replace
that user with a namespace allocated UID; writable image paths are group-owned
for that arbitrary-UID model.

Input topic:

- `otel.servicegraph.metrics`

Output topics:

- `graph.interactions.events`
- `graph.interactions.dlq`

## Validate

```powershell
python scripts\validate_registry.py
python scripts\generate_entities.py --check
python scripts\generate_collector_config.py --check
docker run --rm -v "${PWD}:/workspace" -w /workspace extended-otel-flink-dev:2.2.1 python -m ruff check .
docker run --rm -v "${PWD}:/workspace" -w /workspace extended-otel-flink-dev:2.2.1 python -m pyright
docker run --rm -v "${PWD}:/workspace" -w /workspace extended-otel-flink-dev:2.2.1 python -m pytest
docker compose config
```

Run the complete upsert/DLQ/delete lifecycle smoke test with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke_compose.ps1
```

## OpenShift

The production starting point uses Flink native Kubernetes HA, an RWX
checkpoint volume, a persistent Collector queue, restricted OpenShift security
contexts, and external Kafka over SCRAM-SHA-256/TLS. It requires no CRDs or
cluster-admin permissions.

See `deploy/openshift/README.md` for required mock-value replacement,
Artifactory image promotion, secret creation, server-side validation, and
operational recovery procedures.
