# Graph Engine

The graph engine turns telemetry into a live entity graph.

The important files are:

- `graph/model.py`: shared source-signal type aliases;
- `graph/observation.py`: normalized entity and edge observation models;
- `graph/relationships.py`: pure functions for expanding registry relationships into edge candidates;
- `graph/service_graph.py`: service graph datapoint to graph-observation formatting;
- `graph/postgres_schema.py`: table-per-entity SQLAlchemy metadata and DDL generation;
- `graph/postgres_loader.py`: SQLAlchemy Core upsert statements for observations;
- `graph/otlp.py`: OTLP trace parsing;
- `graph/metrics.py`: OTLP metric parsing for service graph metrics.

Generated entity classes live under `src/extended_otel_semconv/generated`. The
graph engine consumes those generated classes through
`entities_from_attributes(...)`; it should not hardcode entity-specific parsing
rules.

## Ingestion Sources

The graph has two source signals:

- `trace`: raw OTLP spans;
- `service_graph`: metrics emitted by the OpenTelemetry Collector service graph connector.

Each node and edge records:

- `first_seen`
- `last_seen`
- `observations`
- `sources`
- `attributes`

`sources` is a count by source signal, for example:

```json
{
  "trace": 2,
  "service_graph": 12
}
```

## Raw Trace Ingestion

Trace ingestion:

1. merges resource and span attributes;
2. parses all generated semantic entities from the attribute set;
3. creates or reinforces nodes;
4. applies registry relationships whose source signal includes `trace`.

Client spans do not create `app.endpoint` entities. Server spans can create
application endpoints.

## Service Graph Metric Ingestion

Service graph ingestion:

1. reads the `client` and `server` service names;
2. normalizes `client_*` and `server_*` dimensions back into normal attributes;
3. parses entities for both sides;
4. creates or reinforces nodes;
5. applies registry relationships whose source signal includes `service_graph`;
6. creates a dependency edge between services.

Dependency edge type is derived from service graph `connection_type`:

- empty or unknown: `calls`
- `messaging_system`: `publishes_to`
- `database`: `queries`

The dependency edge is created only when the relationship registry allows that
service-to-service relationship for `service_graph`.

## Relationship Semantics

Relationship definitions are structural co-observation rules. Given a telemetry
record and a relationship definition:

```yaml
source_entity: k8s.pod
target_entity: service
name: runs
```

if both entities are parsed from the same telemetry record, the graph creates:

```text
k8s.pod -> runs -> service
```

This keeps relationship creation explicit while avoiding hardcoded topology in
Python code.

## Persistence

The project writes to Postgres as the source of truth. Entity tables are
generated per entity type from SQLAlchemy metadata built from the merged
registry. Loader code uses SQLAlchemy Core PostgreSQL upserts against that same
metadata, so DDL and writes share one schema model. The loader records
`observation_id` values before upsert, so replayed Kafka messages are skipped
instead of counted twice.

Staleness is represented by `last_seen`; downstream organizational systems can
decide how to project or hide stale data in graph caches.

## Tests

Graph behavior is covered by:

- `tests/test_graph_relationships.py` for pure relationship expansion;
- `tests/test_graph_ingest.py` for OTLP parsing and service graph observation formatting;
- `tests/test_graph_formatter.py` for OTLP JSON log formatting;
- `tests/test_postgres_schema.py` for generated table-per-entity schema and SQLAlchemy upserts.

The tests build OTLP protobuf requests directly. They do not require a running
Collector.
