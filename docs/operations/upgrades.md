# Upgrades and Recovery

The Collector, Flink application, and UI have different upgrade behavior.

## Before every upgrade

1. Record current image digests and Helm values.
2. Confirm both Kafka topics are healthy.
3. Confirm the Flink job is `RUNNING`.
4. Confirm a recent checkpoint completed.
5. For stateful Flink changes, create and verify a savepoint.
6. Render and review the new chart.
7. Confirm the new image can read the existing event and state schemas.

## Collector upgrade

The routers are stateless, but backends hold in-memory span-pairing and
cumulative-to-delta state. A restart can lose in-flight pairs and reset local
metric streams.

Use a controlled rollout, keep the two-member backend identity stable, and
expect a short observation gap. Do not change the backend replica count as part
of an ordinary image upgrade.

After rollout, verify:

- both fixed backend DNS names resolve;
- both backends export delta metrics;
- input topic offsets advance;
- Flink does not produce a burst of incorrect interaction churn.

## Flink application upgrade

The native Application Mode Deployment is owned by Flink, not directly by the
Helm release. Treat an application upgrade as replacement:

1. Trigger a savepoint through the Flink REST API or CLI.
2. Verify the savepoint exists on shared storage.
3. Stop the current job according to the desired drain behavior.
4. Remove old native runtime resources without deleting retained storage.
5. deploy the new immutable image;
6. submit with restoration from the verified savepoint when state continuity is
   required;
7. verify source offsets, job state, and checkpoints.

The current chart launcher does not expose a savepoint restore path as a Helm
value. A manual restore requires adding the appropriate Flink submission
argument or performing the submission directly. Test that procedure before a
production upgrade.

Stable operator UIDs and the keyed state descriptor
`interaction-state-v1` support compatible restoration. Renaming operators,
changing key definitions, or changing serialized state models can make a
savepoint incompatible.

## JobManager failover test

Resolve the active REST endpoint, remove that JobManager pod, and verify
leadership and checkpoint recovery:

```powershell
$leaderIp = kubectl get endpoints servicegraph-diff-rest `
  --namespace servicegraph-system `
  -o jsonpath='{.subsets[0].addresses[0].ip}'

$leaderPod = kubectl get pods --namespace servicegraph-system `
  -l app=servicegraph-diff `
  -o jsonpath="{.items[?(@.status.podIP=='$leaderIp')].metadata.name}"

kubectl delete pod $leaderPod --namespace servicegraph-system
kubectl rollout status deployment/servicegraph-diff `
  --namespace servicegraph-system --timeout=5m
```

Submit new traffic after recovery. A ready control plane alone does not prove
the data path recovered.

## UI upgrade and replay

The UI uses `Recreate` with one RWO SQLite claim. An image upgrade stops the old
pod before starting the new one.

The database records applied Kafka offsets transactionally. On restart, the
consumer resumes from those offsets. To rebuild:

1. stop the UI Deployment;
2. preserve or snapshot the existing claim;
3. attach a new empty claim;
4. ensure Kafka retention still contains the desired history;
5. start the UI and monitor replay lag.

## Registry and event-schema upgrades

Adding an entity can change:

- generated package exports;
- Collector dimensions and cardinality;
- graph nodes and edges in upsert events;
- payload hashes for affected interactions.

Deploy the Collector dimensions and Flink runtime from the same registry
revision. Consumers should ignore unknown entity and edge types but validate
the event envelope.

Breaking event-contract changes require a new schema version and a migration
plan. Do not repurpose existing fields with new semantics.

## Rollback

A code rollback is safe only when the old image can read:

- the current Flink savepoint or checkpoint state;
- current Kafka records;
- the current interaction event schema;
- current SQLite schema, when rolling back the UI.

Preserve the previous image digest, chart values, and a pre-upgrade savepoint
until post-upgrade verification is complete.
