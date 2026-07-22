# Extended OpenTelemetry Semantic Conventions

This project extends the OpenTelemetry semantic entity model and turns
service-graph telemetry into a typed, current interaction view.

```text
OTLP traces
  -> OpenTelemetry Collector service_graph connector
  -> Kafka topic otel.servicegraph.metrics
  -> PyFlink keyed interaction state and diffing
  -> Kafka topics graph.interactions.events / graph.interactions.dlq
  -> NiFi / MongoDB materialization outside this repository
```

Postgres and Kafka Connect are intentionally not part of the runtime.

## Project Status

The semantic library and v1 interaction diff engine are feature-complete and
verified through a source-free local Collector, Kafka, and Flink lifecycle.
Internal artifact configuration, production wheel delivery, real-cluster
validation, and downstream NiFi/MongoDB materialization remain to be completed.

The standalone Collector Helm chart implements a trace-ID-routing tier feeding
two stateful service-graph Collector replicas through stable ordinal DNS and a
headless Service. Internal image, Kafka, TLS, storage, and NetworkPolicy values
still require configuration and real-cluster validation. The older raw
OpenShift manifest remains only as a single-replica reference baseline.

## Packages

- `extended-opentelemetry-semconv` owns the OTel-style registry, generated
  Pydantic entities, relationships, dimensions, OTLP parsing, interaction
  contracts, hashing, expiry, and pure state transitions.
- `otel-servicegraph-diff` owns validated runtime settings and PyFlink/Kafka
  wiring.

The semantic package imports without PyFlink or a Kafka client.

## Supported Runtime

- Python 3.12.13
- Java 11
- Apache Flink and PyFlink 2.2.1
- Flink SQL Kafka connector 5.0.0-2.2
- OpenTelemetry Collector Contrib 0.156.0
- Pinned OpenTelemetry semantic model 1.43.0

## Developer Documentation

- [Architecture and contracts](docs/architecture.md)
- [Air-gapped build and release](docs/build-and-release.md)
- [Deployment and operations](docs/deployment-and-operations.md)
- [Limitations and roadmap](docs/limitations-and-roadmap.md)
- [Engineering handoff](docs/handoff.md)
- [OpenShift manifest usage](deploy/openshift/README.md)
- [Standalone Collector Helm chart](deploy/helm/servicegraph-collector/README.md)

## Repository Layout

- `upstream/otel-semconv/v1.43.0/model/`: pinned upstream OTel model.
- `model/extensions/`: project attributes, entities, and relationships in OTel
  model YAML.
- `packages/extended-opentelemetry-semconv/`: independently published semantic
  library.
- `apps/otel-servicegraph-diff/`: independently published PyFlink application
  and thin runtime image.
- `deploy/`: local topology, standalone Collector chart, shared stream
  contract, kind fixture, and legacy OpenShift starting point.
- `scripts/`: generation, validation, artifact, and lifecycle tooling.
- `tools/`: development-only telemetry, Kafka, and confidence helpers.

## Generate And Validate

Use the supported Python 3.12 environment or the development image:

```powershell
python scripts\validate_registry.py
python scripts\generate_entities.py --check
python scripts\generate_collector_config.py --check
python -m ruff check .
python -m pyright
python -m pytest
docker compose config --quiet
docker run --rm -v "${PWD}:/workspace" -w /workspace alpine/helm:3.17.3 `
  lint deploy/helm/servicegraph-collector --strict
```

Run the complete source-free upsert, duplicate-suppression, DLQ, expiry/delete,
and recreation lifecycle with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke_compose.ps1
```

Run the chart itself in kind with `scripts\kind_up.ps1`, then verify paired
traces reach Kafka with `scripts\kind_smoke.ps1`. These scripts expect `kind`,
`kubectl`, `helm`, and the required images to be available from approved local
or internal mirrors.

## Build Artifacts

Build both wheels:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_wheels.ps1
```

The thin runtime image contains Python, PyFlink, runtime dependencies, the
Kafka connector, and the private Java 11 serializers. It excludes application
source and wheels; production wheel delivery belongs to the internal deployment
integration.
