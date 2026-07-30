# Architecture

## Runtime

```text
OTLP clients or optional live demo
  -> two Collector routers (trace-ID load balancing)
  -> two stateful Collector backends (service_graph connector)
  -> otel.servicegraph.metrics
  -> Flink interaction diff
  -> graph.interactions.events
  -> optional UI projection (SQLite)
```

Both routers use the same fixed hash ring of two backend pod DNS names. The
backends run as a StatefulSet behind a headless Service, so their ordinal names
remain stable. Routing on trace ID sends every span for a trace to the same
backend, where the service-graph connector keeps in-memory pairing state.
Each backend converts its connector-local cumulative counters to deltas before
Kafka. Non-zero deltas from either shard represent activity, while idle zero
deltas do not refresh Flink expiry. Kafka separates service-graph extraction
from interaction state.

The Flink job runs in a dedicated standalone Session cluster. Helm owns the
JobManager and TaskManager Deployments, REST Service, configuration, and
initial submission Job. One JobManager uses Kubernetes high availability so a
replacement pod recovers the submitted job from retained metadata and its
latest checkpoint. One RWX claim stores HA metadata, checkpoints, and
savepoints. The submitter, JobManager, and TaskManagers use the same immutable
image.

## Collector Dimensions

The Collector dimensions file is generated from the merged upstream and
extension registry. Generation selects entities participating in
`service_graph` relationships, collects their scalar attribute references, and
excludes template attributes such as labels and annotations.

This policy can include high-cardinality identifiers such as pod UIDs and
service instance IDs. Treat narrowing as an explicit registry policy change,
not an ad hoc Collector configuration edit.

The Collector pipelines keep `memory_limiter` first and batch both traces and
service-graph metrics. Export retries use bounded in-memory queues. Collector
traffic between the router and backend is plaintext; cluster-level network
isolation is owned by the target platform.

## Interaction Engine

Only cumulative `traces_service_graph_request_total` and
`traces_service_graph_request_failed_total` points affect interaction state.
Unsupported service-graph metrics are ignored. Invalid records increment
Flink's `rejected_records` metric and are skipped.

An interaction ID is derived from the client, server, normalized connection
type, and canonical dimensions. Metric name is excluded so request and failed
totals update the same state.

An upsert is emitted when state is new or its payload changes. Repeated
cumulative values emit nothing and do not refresh expiry. Counter advances,
counter resets, and non-zero delta observations count as activity. Event-time
and processing-time timers emit deletes for expired interactions.

Kafka records use `interaction_id` as the key. Delivery is at least once;
deterministic event IDs and idempotent upsert/delete operations allow downstream
deduplication.

Schema 1.1 upserts include the typed entities and relationships observed for the
interaction. The optional UI consumes these commands and materializes only the
current state Flink declares. It has no TTL, expiry timer, or stale-data policy.
An interaction remains visible until Flink emits its explicit delete command.
Recent commands are retained for inspection independently of current state.

## Ownership

The semantic package owns interpretation and pure transitions. The Flink
application owns Kafka, keyed state, timers, and checkpoints. The Collector
chart owns trace routing and service-graph extraction. The demo chart owns
optional synthetic OTLP traffic but no interaction state. The Flink chart owns
submission, RBAC, runtime Deployments, and persistent state configuration. The UI
chart owns the optional projection Deployment, ClusterIP Service, and SQLite
claim; it does not own interaction lifecycle decisions.
