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

## What This Repo Owns

- pinned upstream OpenTelemetry model loading from `upstream/otel-semconv/v1.43.0/model`;
- custom extension model loading from `model/extensions`;
- generated Pydantic entity classes for identifiable upstream and extension entities;
- registry-defined graph relationships;
- Collector servicegraph dimension generation from modeled entity fields;
- servicegraph metric parsing into interaction observations;
- PyFlink state/diff logic that emits idempotent upsert/delete interaction events.

## Repository Layout

- `upstream/otel-semconv/v1.43.0/model/` is the pinned upstream OpenTelemetry model snapshot.
- `model/extensions/` contains extension attributes, entities, and relationships.
- `src/extended_otel_semconv/generated/` contains committed generated entity classes.
- `src/extended_otel_semconv/graph/` contains OTLP parsing, relationships, dimensions, and interaction diff models.
- `src/extended_otel_semconv/services/interaction_diff/` contains the PyFlink service entrypoint.
- `src/extended_otel_semconv_devtools/telemetry/` contains local telemetry and Kafka helper tools.
- `deploy/local/otelcol.yaml` is generated from the merged registry.
- `deploy/openshift/` contains the air-gapped, namespace-scoped OpenShift deployment.
- `scripts/` contains repository validation and artifact generation utilities.
- `tests/` covers registry validation, generated models, servicegraph parsing, dimensions, and interaction diff behavior.

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

The supported runtime is Python `3.12.13`, Apache Flink/PyFlink `2.2.1`, and
the Flink Kafka connector `5.0.0-2.2`. Use:

```powershell
docker compose up --build
```

The stack starts Redpanda Kafka, the OpenTelemetry Collector, Flink
JobManager/TaskManager, the interaction diff job, and a demo trace generator.
The vendored Kafka JARs are Flink client dependencies, not Kafka Connect
components; the Kafka cluster does not need Kafka Connect enabled.

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
docker run --rm -v "${PWD}:/workspace" -w /workspace extended-otel-flink:2.2.1 python -m ruff check .
docker run --rm -v "${PWD}:/workspace" -w /workspace extended-otel-flink:2.2.1 python -m pyright
docker run --rm -v "${PWD}:/workspace" -w /workspace extended-otel-flink:2.2.1 python -m pytest
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
