# Extended OpenTelemetry Semantic Conventions

This project extends the OpenTelemetry semantic convention entity registry without
redefining entities that OpenTelemetry already owns.

The project has three jobs:

- load a pinned upstream OpenTelemetry semantic convention model snapshot;
- define only custom extension entities and graph relationships;
- normalize telemetry-derived graph observations and persist them from the merged model.

The runtime path is production-shaped even in local development: traces enter the
OpenTelemetry Collector, the `service_graph` connector derives dependencies,
the Collector Kafka exporter writes those service graph metrics as OTLP JSON,
Kafka buffers those records, and Python loader code turns them into durable
graph observations.

## Current Status

This is a registry extension and graph-observation pipeline toolkit. It is built
around Kafka buffering and table-per-entity Postgres persistence.

What is implemented:

- upstream OpenTelemetry model loading from `upstream/otel-semconv/v1.43.0/model`;
- custom extension model loading from `model/extensions`;
- generated Pydantic entity classes for identifiable upstream and extension entities;
- registry-defined graph relationships;
- service_graph metric formatting into entity and edge observations;
- generated table-per-entity Postgres schema from SQLAlchemy metadata;
- SQLAlchemy Core upsert statements for graph observations;
- generated Collector config dimensions from the merged registry.

## Repository Layout

- `upstream/otel-semconv/v1.43.0/model/` is the pinned upstream OpenTelemetry model snapshot.
- `upstream/otel-semconv.lock.json` records the pinned upstream source.
- `model/extensions/` contains extension attributes, entities, and relationships.
- `src/extended_otel_semconv/generated/` contains committed generated entity classes.
- `src/extended_otel_semconv/graph/` contains OTLP parsing, observation formatting, and SQLAlchemy persistence helpers.
- `src/extended_otel_semconv/services/` contains runnable service packages and service-local configuration.
- `src/extended_otel_semconv_devtools/` contains local demo and end-to-end validation helpers.
- `deploy/local/otelcol.yaml` is generated from the merged registry.
- `deploy/postgres/001_graph_schema.sql` is generated from the merged registry.
- `scripts/` contains repository validation and artifact generation utilities.
- `tests/` covers registry validation, generation freshness, entity parsing, and graph ingestion.

## Architecture Docs

- [Architecture](docs/architecture.md)
- [Registry Extensions](docs/registry-extensions.md)
- [Graph Engine](docs/graph-engine.md)
- [Collector Pipeline](docs/collector-pipeline.md)
- [Upstream Semconv Upgrade Runbook](docs/upstream-semconv-upgrade-runbook.md)
- [Test Environment](docs/test-environment.md)
- [Development](docs/development.md)

## Generate

Regenerate committed artifacts after changing `model/extensions/` or the
upstream snapshot:

```powershell
python scripts\generate_entities.py
python scripts\generate_collector_config.py
python scripts\generate_postgres_schema.py
```

Check that generated files are current:

```powershell
python scripts\generate_entities.py --check
python scripts\generate_collector_config.py --check
python scripts\generate_postgres_schema.py --check
```

The entity generator emits runtime classes only for entities with explicit
`role: identifying` attributes. Entities without identifying refs remain in the
registry but are skipped by the runtime parser.

## Python API

Use `entities_from_attributes(...)` to parse raw OpenTelemetry attributes and
create every generated entity whose identifying attributes are present.

```python
from extended_otel_semconv import entities_from_attributes

entities = entities_from_attributes(
    {
        "service.name": "checkout-api",
        "service.namespace": "payments",
        "k8s.pod.uid": "4e2b0bb9-4700-4f20-bb6f-c6e2b5975c6b",
        "http.request.method": "POST",
        "http.route": "/checkout/{cart_id}",
    }
)

for entity in entities:
    print(entity.entity_type, entity.entity_id)
```

## Local Pipeline

Run the local stack:

```powershell
docker compose up --build
```

The stack starts:

- `otelcol`: OpenTelemetry Collector receiving OTLP on `4317` and `4318`;
- `kafka`: local Redpanda Kafka-compatible broker on `9092`;
- `postgres`: table-per-entity graph storage on `5432`;
- `graph-loader`: Kafka consumer that persists graph observations into Postgres;
- `demo`: sample trace generator that sends OTLP HTTP traces through the collector.

The Collector writes service graph metrics to Kafka topic
`otel.servicegraph.metrics`; `graph-loader` consumes that topic and
upserts entities and edges into Postgres.

The graph loader service entrypoint is:

```powershell
python -m extended_otel_semconv.services.graph_loader.cli
```

## Validate

```powershell
python scripts\validate_registry.py
python scripts\generate_entities.py --check
python scripts\generate_collector_config.py --check
python scripts\generate_postgres_schema.py --check
python -m ruff check .
python -m mypy src scripts tests
python -m pytest
docker compose config
```
