# Extended OpenTelemetry Semantic Conventions

Build a live, organization-specific topology from OpenTelemetry.

This project extends the OpenTelemetry entity model with entities and
relationships that matter to your environment, generates the code and
Collector configuration needed to observe them, and maintains their lifecycle
as a Kafka event stream.

```text
OTLP traces
  -> trace-affine OpenTelemetry Collectors
  -> service-graph metrics
  -> Kafka
  -> stateful Flink graph-element engine
  -> node and edge upsert/delete events
  -> any downstream projection
```

## Why use it?

Traditional service graphs primarily show that one service calls another. This
project also describes the topology around service activity:

- application endpoints exposed by a service;
- namespaces containing services;
- Kubernetes pods running service instances;
- containers, processes, and runtimes;
- repositories and revisions used to build a service;
- your own domain-specific entities and relationships.

The registry is the source of truth. It generates typed Pydantic entities,
runtime relationship metadata, and the Collector dimensions that carry entity
attributes into the service-graph stream.

## What the runtime guarantees

- All spans from a trace are routed to the same service-graph backend.
- Flink privately correlates observations and owns graph staleness.
- New and changed graph elements produce complete `upsert` commands.
- Elements with no active contributors produce explicit `delete` commands.
- Kafka records are keyed by deterministic graph element IDs.
- Downstream consumers do not need their own TTL policy.

Delivery is at least once. Event IDs and graph identifiers are deterministic so
consumers can apply commands idempotently.

## Repository components

| Component | Responsibility |
| --- | --- |
| `packages/extended-opentelemetry-semconv` | Registry validation, generated entities, OTLP parsing, and pure graph transitions |
| `services/otel-servicegraph-diff` | PyFlink Kafka source, keyed state, timers, checkpoints, and event sink |
| `services/servicegraph-indexer` | ArangoDB initializer and lifecycle indexer |
| `services/servicegraph-gremlin` | Pinned read-only TinkerPop/ArangoDB runtime |
| `services/servicegraph-demo` | Optional long-running synthetic OTLP traffic |
| `deploy/helm/servicegraph-collector` | Trace router and stateful service-graph extraction |
| `deploy/helm/servicegraph-flink` | Standalone Flink Session cluster, submission, and storage |
| `deploy/helm/servicegraph-arangodb` | Optional local-development ArangoDB |
| `deploy/helm/servicegraph-indexer` | ArangoDB initializer and Kafka indexer |
| `deploy/helm/servicegraph-gremlin` | Read-only Gremlin Server |
| `deploy/helm/servicegraph-demo` | Optional traffic generator |

Kafka and topic creation remain platform responsibilities. Deployment uses
standard Kubernetes resources, Helm, and no CRDs.

## Choose a path

- [Run the complete system locally](getting-started/quickstart.md)
- [Run and debug the PyFlink job in PyCharm](development/local-pyflink.md)
- [Understand the semantic entity model](concepts/semantic-model.md)
- [Add your first custom entity](getting-started/custom-entity.md)
- [Deploy to an existing Kubernetes cluster](deployment-and-operations.md)
- [Project and traverse graph elements through ArangoDB and Gremlin](deployment/arangodb-gremlin.md)
- [Consume the graph element event stream](reference/event-schema.md)
