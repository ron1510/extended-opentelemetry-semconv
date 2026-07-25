# UI and Demo Configuration

Both components are optional. Neither one owns interaction lifecycle.

## Visualization service

The UI consumes Flink commands, applies them to SQLite, exposes a read API, and
serves a static graph frontend.

```yaml
image:
  repository: registry.internal.example/extended-otel-servicegraph-ui
  tag: "0.1.2"

streamContract:
  kafka:
    brokers: [kafka.internal.example:9092]
    security:
      protocol: SASL_SSL
      existingSecret: servicegraph-kafka-auth
  topics:
    interactionEvents: graph.interactions.events

consumer:
  groupId: servicegraph-visualization
  recentEventLimit: 1000

storage:
  storageClassName: standard
  size: 2Gi
  accessModes: [ReadWriteOnce]
  retainClaim: true
```

The Deployment uses one replica and the `Recreate` strategy because SQLite is
stored on one RWO volume. Kafka offsets are recorded in SQLite in the same
transaction as projection changes. The Kafka consumer group itself is not the
authoritative replay position.

Changing `consumer.groupId` does not clear existing SQLite state. To build a
fresh projection, use a new empty claim or deliberately remove the database
while the Deployment is stopped.

The UI never removes a record based on age. It applies only Flink `upsert` and
`delete` commands.

## Live traffic demo

The demo emits paired OTLP client/server spans. It starts with a small set of
service edges, grows to a configured maximum, then rotates edges.

```yaml
collector:
  endpoint: http://servicegraph-collector-router:4318/v1/traces

traffic:
  emitIntervalSeconds: 2
  topologyChangeIntervalSeconds: 20
  initialEdges: 2
  maxActiveEdges: 6
  requestsPerTick: 3
  errorRate: 0.08
  serviceNamespace: shop
  instanceId: live-demo
  randomSeed: ""
```

Constraints:

- intervals must be positive;
- `1 <= initialEdges <= maxActiveEdges < 10`;
- `requestsPerTick` must be positive;
- `errorRate` must be between 0 and 1.

Set `randomSeed` for a repeatable topology sequence. Keep one replica unless
multiple independent producers are intentional.

When an edge rotates out, the demo simply stops sending it. Flink emits the
delete after `interactionTtlSeconds`; the generator never writes Kafka events
or deletes UI state.

For a visible lifecycle demonstration, make the time before a retired edge can
return longer than the Flink interaction TTL.
