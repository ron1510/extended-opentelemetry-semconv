# Architecture

The project is built around a strict ownership boundary.

OpenTelemetry owns upstream semantic convention entities and attributes. This
repository owns only extension entities, extension attributes, relationship
definitions, graph-observation normalization, SQLAlchemy persistence helpers,
and generated local artifacts.

## Model Flow

1. Load the pinned upstream OpenTelemetry model from `upstream/otel-semconv/v1.43.0/model`.
2. Load extension model files from `model/extensions`.
3. Validate that extensions do not redefine upstream attributes or entities.
4. Merge upstream and extension registries in memory.
5. Generate Python entity classes from identifiable entities.
6. Generate Collector `service_graph` dimensions from merged registry attributes.

The upstream snapshot is intentionally checked in. The runtime does not fetch
OpenTelemetry models from the network.

Use [Upstream Semconv Upgrade Runbook](upstream-semconv-upgrade-runbook.md) when
changing this pinned version. A version bump is a model migration, not only a
dependency update.

## Runtime Flow

1. Applications send OTLP traces to the local Collector.
2. The Collector `service_graph` connector derives request dependency metrics.
3. The Collector Kafka exporter writes service graph metrics to Kafka as OTLP JSON.
4. The graph loader consumes those metrics and writes normalized graph observations to Postgres.
5. The formatter turns each datapoint log into normalized graph observations.
6. The loader writes observations into table-per-entity Postgres tables through
   SQLAlchemy Core statements generated from the merged registry.

## Ownership Boundary

This repository configures the OpenTelemetry Collector rather than replacing it.
The Collector remains responsible for OTLP receiving, service dependency
extraction, datapoint-to-log conversion, and Kafka export. Python code is
responsible for registry-aware observation formatting and SQLAlchemy persistence
helpers.

## Runtime State

Postgres is the source-of-truth storage target. It uses one generated table per
entity type plus shared edge, idempotency, and error tables. Organization-owned
systems can project this data into graph caches outside this repository.

## Validation Surface

Architecture-level changes should pass both validation layers:

- Python checks described in [Test Environment](test-environment.md);
- Docker Compose runtime validation for Collector, Kafka, and Postgres wiring.
