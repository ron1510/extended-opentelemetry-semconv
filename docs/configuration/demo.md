# Demo Traffic Configuration

The optional demo emits paired OTLP client/server spans. It starts with a small
set of service edges, grows to a configured maximum, then rotates edges.

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
- `1 <= initialEdges <= maxActiveEdges`;
- `requestsPerTick` must be positive;
- `errorRate` must be between 0 and 1;
- `randomSeed`, when set, must be an integer.

Set `randomSeed` for a repeatable topology sequence. Keep one replica unless
multiple independent producers are intentional.

When an edge rotates out, the demo simply stops sending it. Flink emits delete
events after `interactionTtlSeconds`; the generator never writes Kafka events
or changes ArangoDB directly.

For a visible lifecycle demonstration, make the time before a retired edge can
return longer than the Flink contributor TTL.
