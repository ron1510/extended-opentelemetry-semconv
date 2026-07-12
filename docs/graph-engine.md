# Graph Engine

The graph engine turns telemetry into a live entity graph.

The important files are:

- `graph/model.py`: serializable node, edge, snapshot, and source-signal models;
- `graph/evidence.py`: pure functions for creating and reinforcing nodes and edges;
- `graph/relationships.py`: pure functions for expanding registry relationships into edge candidates;
- `graph/store.py`: stateful in-memory graph store with locking and TTL pruning;
- `graph/otlp.py`: OTLP trace parsing;
- `graph/metrics.py`: OTLP metric parsing for service graph metrics.

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

## TTL

The graph store prunes nodes and edges whose `last_seen` is older than the
configured TTL. The default is 900 seconds.
