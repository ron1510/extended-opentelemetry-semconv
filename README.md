# Extended OpenTelemetry Semantic Conventions

This project extends the OpenTelemetry semantic convention entity registry without
redefining entities that OpenTelemetry already owns.

The project has three jobs:

- load a pinned upstream OpenTelemetry semantic convention model snapshot;
- define only custom extension entities and graph relationships;
- ingest telemetry and materialize a live entity graph from the merged model.

The graph engine accepts raw OTLP traces and OpenTelemetry Collector
`service_graph` connector metrics. Raw traces create observed entities directly.
`service_graph` metrics are treated as graph reinforcement events: they create
the client/server entities available in metric dimensions, reinforce structural
relationships, and create dependency edges such as `calls`, `publishes_to`, and
`queries`.

## Current Status

This is an in-memory graph engine and registry extension toolkit. It is built to
make the model boundaries clear before adding durable storage or a richer query
API.

What is implemented:

- upstream OpenTelemetry model loading from `upstream/otel-semconv/v1.43.0/model`;
- custom extension model loading from `model/extensions`;
- generated Pydantic entity classes for identifiable upstream and extension entities;
- registry-defined graph relationships;
- OTLP trace ingestion;
- OTLP metric ingestion for Collector `service_graph` output;
- graph TTL pruning;
- node and edge observation counts;
- node and edge source attribution from `trace` and `service_graph`;
- generated Collector config dimensions from the merged registry.

## Repository Layout

- `upstream/otel-semconv/v1.43.0/model/` is the pinned upstream OpenTelemetry model snapshot.
- `upstream/otel-semconv.lock.json` records the pinned upstream source.
- `model/extensions/` contains extension attributes, entities, and relationships.
- `src/extended_otel_semconv/generated/` contains committed generated entity classes.
- `src/extended_otel_semconv/graph/` contains OTLP parsing and graph materialization.
- `deploy/local/otelcol.yaml` is generated from the merged registry.
- `scripts/` contains validation, generation, and demo helpers.
- `tests/` covers registry validation, generation freshness, entity parsing, and graph ingestion.

## Architecture Docs

- [Architecture](docs/architecture.md)
- [Registry Extensions](docs/registry-extensions.md)
- [Graph Engine](docs/graph-engine.md)
- [Collector Pipeline](docs/collector-pipeline.md)
- [Development](docs/development.md)

## Generate

Regenerate committed artifacts after changing `model/extensions/` or the
upstream snapshot:

```powershell
python scripts\generate_entities.py
python scripts\generate_collector_config.py
```

Check that generated files are current:

```powershell
python scripts\generate_entities.py --check
python scripts\generate_collector_config.py --check
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

## Live Graph Demo

Run the local stack:

```powershell
docker compose up --build
```

The stack starts:

- `graph`: FastAPI entity graph service on `http://localhost:8000`;
- `otelcol`: OpenTelemetry Collector receiving OTLP on `4317` and `4318`;
- `demo`: sample trace generator that sends OTLP HTTP traces through the collector.

Inspect the graph:

```powershell
curl http://localhost:8000/health
curl http://localhost:8000/entities
curl http://localhost:8000/edges
curl http://localhost:8000/graph
```

## Validate

```powershell
python scripts\validate_registry.py
python scripts\generate_entities.py --check
python scripts\generate_collector_config.py --check
python -m ruff check .
python -m mypy src scripts tests
python -m pytest
docker compose config
```
