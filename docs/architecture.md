# Architecture

## Runtime

```text
OTLP clients or optional live demo
  -> two Collector routers (trace-ID load balancing)
  -> two stateful Collector backends (service_graph connector)
  -> otel.servicegraph.metrics
  -> Flink graph-element engine
  -> graph.elements.events
  -> ArangoDB current-state graph
  -> read-only GraphBinary Gremlin
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

The indexer applies complete graph elements declared by Flink to native
ArangoDB vertex and edge collections. Upserts replace the document under a
SHA-256 key derived from `element_id`; deletes remove that key. The indexer
performs no semantic extraction, contributor merging, reference counting,
expiry, or staleness inference.

The generated graph schema maps semantic entity and relationship types to
stable collections and maps canonical dotted OTel fields to Gremlin-safe scalar
properties. Canonical `attributes` and `metrics` maps remain in every document.
Trusted internal clients connect directly to Gremlin Server over GraphBinary.
`ReadOnlyStrategy` and read-only permissions on every semantic ArangoDB
collection independently reject graph mutations. The provider identity has a
narrow write exception for its `TINKERPOP-GRAPH-VARIABLES` version document,
which provider `4.0.0` rewrites while opening the graph.

The semantic package owns interpretation and pure transitions. Flink owns keyed
state, timers, checkpoints, and graph lifecycle. Collector owns trace pairing
and service-graph metrics. The indexer owns Kafka offsets and the ArangoDB
current-state projection. Gremlin Server exposes read-only traversal. Helm owns
runtime resources.
