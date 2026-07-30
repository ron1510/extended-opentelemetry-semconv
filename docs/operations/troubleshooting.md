# Troubleshooting

Diagnose the pipeline in order. Start at OTLP ingress and move downstream.

## No interactions appear

Check:

1. application spans contain a client and server side with the same trace ID;
2. both sides reach the router;
3. routers can resolve both backend ordinal names;
4. the metrics topic receives OTLP JSON;
5. Flink is `RUNNING`;
6. output topic offsets advance;
7. UI readiness is healthy.

```console
kubectl get pods -n servicegraph-system
kubectl logs -n servicegraph-system deployment/servicegraph-collector-router
kubectl logs -n servicegraph-system statefulset/servicegraph-collector-backend
kubectl logs -n servicegraph-system deployment/servicegraph-ui
```

The service-graph connector cannot pair traces that are incomplete, sampled
inconsistently, or split across backends.

## Services appear but custom entities do not

Verify:

- every identifying attribute is present;
- the entity participates in a `service_graph` relationship;
- generated entities and dimensions are current;
- the Collector ConfigMap contains the attribute dimension;
- the Flink image includes the new generated package;
- the affected telemetry was emitted after deployment.

```console
python scripts/generate_entities.py --check
python scripts/generate_collector_dimensions.py --check
```

Existing upserts do not gain new entities until new activity produces an
updated payload.

## Interactions never delete

Confirm:

- traffic for that exact client, server, connection type, and dimensions has
  actually stopped;
- the demo is not rotating the edge back in;
- `interactionTtlSeconds` is the expected value;
- processing-time timers are running;
- Flink checkpoints and TaskManagers are healthy.

Zero delta metrics do not refresh expiry. Any non-zero delta does.

## Interactions churn or repeatedly reappear

Likely causes:

- cumulative metrics are reaching Flink without per-backend delta conversion;
- dimensions are unstable or high-cardinality;
- a counter stream repeatedly resets;
- multiple traffic sources use different attributes for the same logical edge;
- old and new Collector configurations are active simultaneously.

Inspect one interaction's dimensions and metrics in the output topic. Confirm
Collector backend configuration includes
`cumulativetodelta/servicegraph`.

## Collector backends show unmatched spans

Check router configuration and DNS:

```console
kubectl get service -n servicegraph-system \
  servicegraph-collector-backend-headless
kubectl get endpoints -n servicegraph-system \
  servicegraph-collector-backend-headless
```

Both routers must have the same ordered two-host static resolver. Tail or head
sampling upstream must keep client and server spans consistently.

## Flink submitter failed

The submitter is expected to complete after submission. Inspect its logs:

```console
kubectl get jobs -n servicegraph-system
kubectl logs -n servicegraph-system job/processing-servicegraph-flink-submitter
```

Common causes:

- image pull failure;
- JobManager or REST Service not ready;
- PVC not bound;
- a terminal job already uses `job.fixedJobId`;
- missing Python or Java dependencies in the runtime image;
- Kafka security settings rejected at application startup.

The exact submitter name depends on the Helm release and overrides.

## Flink upgrade savepoint failed

A failed `pre-upgrade` hook prevents Helm from changing the runtime
Deployments. Inspect:

```console
kubectl logs -n servicegraph-system \
  job/processing-servicegraph-flink-upgrade-savepoint
```

The hook requires the configured fixed-ID job to be active, the existing REST
Service to be reachable, and the shared claim to be writable. Keep the cluster
ID, fixed job ID, and claim unchanged in the upgrade values.

If the savepoint succeeds but the post-upgrade submitter fails, inspect both
hook Jobs. The savepoint path is retained under `/flink-state/upgrades`; fix
the image or state incompatibility and retry the upgrade. The next pre-upgrade
hook can reuse `latest.savepoint` when the job is already stopped. Do not start
a fresh job without deciding whether losing the saved interaction state is
acceptable.

## Flink runtime does not recover

Check the JobManager logs, HA ConfigMaps, and shared state claim:

```console
kubectl logs -n servicegraph-system \
  deployment/processing-servicegraph-flink-jobmanager
kubectl get configmaps -n servicegraph-system
kubectl get pvc -n servicegraph-system
```

The runtime ServiceAccount must have ConfigMap CRUD/list/watch. It does not
need finalizer permissions. Recovery also requires the existing claim and the
same stable cluster and job IDs.

## Flink rejects records

An increasing `rejected_records` counter means input records failed OTLP parsing
or semantic normalization. Inspect TaskManager logs and a sample Kafka record.

Only supported service-graph metric names and numeric points with required
client/server fields affect state.

## UI reports ready but data is old

Compare:

- `/api/v1/status` last-event time;
- output-topic end offsets;
- SQLite source offsets;
- UI consumer logs.

The UI can be caught up but display old interactions if Flink has not emitted
the expected delete. It can also lag while replaying a retained topic.

## Kafka authentication failures

For every chart, verify:

- protocol is exactly `SASL_SSL`;
- mechanism is `SCRAM-SHA-256`;
- the Secret exists in the same namespace;
- selected username, password, and CA keys exist;
- the broker certificate matches its hostname.

Do not disable endpoint identification or certificate verification to hide a
name or CA configuration problem.
