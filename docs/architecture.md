# Architecture

## Runtime

```text
OTLP clients or optional live demo
  -> two Collector routers (trace-ID load balancing)
  -> two stateful Collector backends (service_graph connector)
  -> otel.servicegraph.metrics
  -> Flink graph-element engine
  -> graph.elements.events
  -> Elasticsearch current-state projection
  -> typed query API or Kibana
```

Both routers use the same fixed hash ring of backend pod DNS names. The
StatefulSet ordinals keep that ring stable, and trace-ID routing sends all spans
for a trace to one service-graph connector. Each backend converts its local
cumulative connector counters to deltas before Kafka, so independent shards can
contribute without overwriting one another.

The Flink job runs in a Helm-managed standalone Session cluster. Helm owns the
JobManager and TaskManager Deployments, REST Service, configuration, and
submission Job. Kubernetes HA metadata plus checkpoints on the shared claim let
a replacement JobManager recover the fixed-ID job.

## Semantic extraction

Collector dimensions are generated from entities participating in
`service_graph` relationships. Flink applies the same generated semantic
registry to each datapoint, producing all supported nodes and relationships.
High-cardinality identifiers such as pod UIDs are intentional graph identity,
not metric labels added arbitrarily by the Flink job.

## Lifecycle processing

Only request and failed-request service-graph counters affect lifecycle. The
first keyed stage maintains private interaction state derived from client,
server, connection type, and canonical dimensions. It owns event-time and
processing-time expiry timers and emits element contribution upserts and
retractions. Interactions are never published.

The second stage is keyed by graph element ID. Nodes with the same semantic ID
and edges with the same source/type/target identity share state. Complementary
optional attributes are merged. Conflicts choose the newest observation, with
contributor ID as a deterministic tie-breaker. Dependency edges accumulate
request deltas for their active lifetime.

The element stage publishes complete upserts when merged state changes and a
delete when the final contributor expires. Kafka uses `element_id` as its key.
At-least-once sink delivery is safe because events have deterministic IDs and
projection operations are idempotent.

## Projection and access

The projector applies the complete graph elements declared by Flink to a strict
Elasticsearch index. Upserts replace the document under the deterministic
element ID and deletes remove it. The projector performs no semantic
extraction, contributor merging, reference counting, expiry, or staleness
inference.

The stateless query API validates recursive patterns against the generated
mapping and translates them to Elasticsearch queries. Kibana can inspect the
same current-state index directly in development and operational environments.

The semantic package owns interpretation and pure transitions. Flink owns keyed
state, timers, checkpoints, and graph lifecycle. Collector owns trace pairing
and service-graph metrics. The access projector owns Kafka offsets and the
Elasticsearch projection. The query API owns only typed query translation.
Helm owns runtime resources.
