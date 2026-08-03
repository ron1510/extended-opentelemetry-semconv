# Monitoring

Monitor the pipeline as one system. A healthy pod is not proof that telemetry is
moving.

## Collector

Watch:

- refused spans and failed exports;
- service-graph connector items awaiting pairing;
- backend memory and restarts;
- router queue growth;
- Kafka exporter queue failures and retry duration;
- unmatched spans caused by incomplete traces.

Useful commands:

```console
kubectl get pods -n servicegraph-system \
  -l app.kubernetes.io/instance=collection

kubectl logs -n servicegraph-system \
  statefulset/servicegraph-collector-backend \
  --since=15m
```

Both backend ordinal DNS names must resolve and both pods must remain ready.
One unavailable backend remaps traces only after send failures and can disrupt
in-flight pairing.

## Kafka

Track:

- input and output topic write rates;
- partition availability and under-replication;
- Flink consumer-group lag;
- UI projection lag;
- broker request latency and rejected writes;
- topic retention relative to recovery time.

An advancing input topic with a static output topic usually means Flink is
stopped, backpressured, rejecting records, or not detecting activity.

## Flink

Track:

- job state;
- completed, failed, and in-progress checkpoints;
- time since the last completed checkpoint;
- checkpoint duration and size;
- source lag and backpressure;
- TaskManager availability;
- JobManager leadership changes;
- restart count;
- `rejected_records`;
- state volume capacity.

Open the Flink UI:

```console
kubectl port-forward -n servicegraph-system \
  service/servicegraph-diff-rest 8081:8081
```

The job must remain `RUNNING`, and completed checkpoints must continue to
increase while traffic is present.

## UI

Check:

```console
curl http://servicegraph-ui:8080/health/live
curl http://servicegraph-ui:8080/health/ready
curl http://servicegraph-ui:8080/api/v1/status
```

Readiness fails when its Kafka consumer is not running. Status reports the last
event time and projection counts. Compare the consumer's position with the
output topic end offset when the graph appears stale.

Monitor SQLite PVC capacity. The current graph, recent-event history, and
source offsets share that database.

## End-to-end canary

A useful canary emits a known paired trace periodically and verifies:

1. the metrics topic receives it;
2. the graph-element topic receives node and edge upserts;
3. the projection exposes the expected entities;
4. stopping the canary eventually produces a delete.

Use a bounded, recognizable service namespace so canary entities are easy to
filter and do not collide with production services.

## Suggested alerts

Alert on:

- any Flink job not `RUNNING`;
- checkpoint failure or excessive checkpoint age;
- sustained Kafka consumer lag;
- repeated Collector export failures;
- Collector or TaskManager restart loops;
- `rejected_records` increasing;
- state or SQLite volume nearing capacity;
- UI readiness failure;
- no output events while input activity is present.
