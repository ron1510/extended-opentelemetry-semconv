# Test Environment

This project has two test environments:

- local Python validation;
- local Docker Compose runtime validation.

The Python checks prove model, formatting, schema, and graph-observation
behavior. The Docker Compose checks prove the OpenTelemetry Collector, Kafka,
and Postgres are wired consistently.

## Prerequisites

Python:

- Python 3.11 or newer
- project dependencies from `pyproject.toml`

Runtime:

- Docker Desktop or another Docker engine with Compose support
- free local ports `4317`, `4318`, `9092`, and `5432`
- `otel/opentelemetry-collector-contrib:0.156.0`

Optional but useful:

- `rg` for search

## Python Validation

Run all local checks:

```powershell
python scripts\validate_registry.py
python scripts\generate_entities.py --check
python scripts\generate_collector_config.py --check
python scripts\generate_postgres_schema.py --check
python -m ruff check .
python -m mypy src scripts tests
python -m pytest
```

What each check proves:

- `validate_registry.py`: extension entities and relationships are valid against the pinned upstream model.
- `generate_entities.py --check`: committed generated entity classes match the merged registry.
- `generate_collector_config.py --check`: committed Collector pipeline matches the merged registry.
- `generate_postgres_schema.py --check`: committed table-per-entity schema matches the merged registry.
- `ruff`: style and obvious static issues are clean.
- `mypy`: typed source, scripts, and tests are internally consistent.
- `pytest`: parser, registry, generated model, relationship, SQLAlchemy persistence, and graph behavior are correct.

## Test Suite Layout

- `tests/test_registry_validation.py`: upstream snapshot loading and extension validation.
- `tests/test_generated_entities.py`: generated entity API and generation freshness.
- `tests/test_app_entities.py`: entity parsing from raw attribute dictionaries.
- `tests/test_graph_relationships.py`: pure relationship expansion rules.
- `tests/test_graph_ingest.py`: OTLP trace/metric parsing and service graph observation formatting.
- `tests/test_graph_formatter.py`: OTLP JSON service graph formatting.
- `tests/test_postgres_schema.py`: table-per-entity schema generation.

The tests do not need a running Collector. They build OTLP protobuf or OTLP JSON
payloads directly and call parser/formatter functions in process.

## Docker Compose Runtime

Validate Compose rendering:

```powershell
docker compose config
```

Start the runtime:

```powershell
docker compose up --build
```

Services:

- `otelcol`: OpenTelemetry Collector on OTLP gRPC `4317` and OTLP HTTP `4318`
- `kafka`: Redpanda Kafka-compatible broker on `9092`
- `postgres`: source-of-truth graph database on `5432`
- `graph-loader`: Kafka consumer that writes graph observations to Postgres
- `demo`: synthetic telemetry generator

The demo sends traces to the Collector. The Collector converts service graph
metrics and writes them to Kafka as OTLP JSON. The graph loader consumes those
OTLP JSON metrics and persists normalized entity and edge observations to
Postgres.

## End-to-End Stress Validation

Run a tagged stress workload through OTLP HTTP:

```powershell
python -m extended_otel_semconv_devtools.graph_loader.stress --run-id codexstress01 --requests 1200 --workers 16
```

Verify the resulting graph rows from the loader container:

```powershell
docker exec extended-opentelemetry-semconv-graph-loader-1 python -m extended_otel_semconv_devtools.graph_loader.verify --run-id codexstress01 --postgres-url postgresql+psycopg://entity_graph:entity_graph@postgres:5432/entity_graph
```

The stress workload covers paired service dependencies, same-service spans,
orphan client spans, spans without Kubernetes attributes, and noisy
high-cardinality attributes. The verifier checks that stress services and edges
exist, dependency `calls` edges were created, and same-service dependency edges
were not created.

Malformed Kafka payload handling can be checked with an isolated topic:

```powershell
docker exec extended-opentelemetry-semconv-graph-loader-1 python -m extended_otel_semconv_devtools.graph_loader.poison --bootstrap kafka:9092 --topic otel.servicegraph.poison-test
docker exec extended-opentelemetry-semconv-graph-loader-1 python -m extended_otel_semconv.services.graph_loader.cli --input kafka-otlp-json-metrics --kafka-bootstrap kafka:9092 --kafka-topic otel.servicegraph.poison-test --kafka-group-id poison-test --kafka-batch-size 1 --max-messages 1 --postgres-url postgresql+psycopg://entity_graph:entity_graph@postgres:5432/entity_graph
```

The expected result is `errors=1`, one row in `graph_observation_errors`, and no
graph-loader crash.

## Collector-Specific Notes

The local Collector config is generated and development-oriented.

It keeps `memory_limiter` first in each pipeline and uses `batch` before export.
The `service_graph` connector is stateful, so a production deployment with more
than one Collector replica needs sticky routing before the connector. The local
Compose environment runs one Collector, so no routing layer is needed there.

## Debugging Failures

If generated checks fail, regenerate:

```powershell
python scripts\generate_entities.py
python scripts\generate_collector_config.py
```

If registry validation fails, inspect whether an extension now duplicates
upstream OpenTelemetry or references a missing attribute/entity.

If the Docker stack starts but Kafka receives no service graph metrics, check:

```powershell
docker compose logs otelcol --tail 120
docker compose logs demo --tail 120
```

If ports are busy, stop the existing stack:

```powershell
docker compose down
```
