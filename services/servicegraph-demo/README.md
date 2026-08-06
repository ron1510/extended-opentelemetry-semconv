# Servicegraph Demo

This long-running process emits paired OTLP client/server spans to the Collector
router. It starts with a small service topology, adds edges over time, and then
rotates active edges. Flink remains the only component responsible for deciding
when a retired interaction is stale and emitting its delete command.

Run it through the Helm chart in
`deploy/helm/servicegraph-demo`. The main controls are the OTLP HTTP endpoint,
emit interval, topology-change interval, active-edge bounds, request count, and
error rate.
