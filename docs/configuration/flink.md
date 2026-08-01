# Flink Job Configuration

The Flink chart runs a standalone Session cluster and submits one PyFlink job
through its internal REST Service. The submitter, JobManager, and TaskManagers
use the same immutable runtime image.

## Application sizing

```yaml
application:
  clusterId: servicegraph-diff
  parallelism: 3
  jobManagerReplicas: 1
  taskManagerReplicas: 2
  taskManagerSlots: 2
  jobManagerProcessMemory: 1200m
  taskManagerProcessMemory: 1800m
```

Helm maintains the configured TaskManager replica count. Available execution
capacity is `taskManagerReplicas * taskManagerSlots`; it must cover job
parallelism. Kubernetes memory limits must remain above the corresponding
Flink process-memory values.

The cluster ID and fixed job ID must be unique within a namespace.

## Interaction settings

```yaml
job:
  fixedJobId: "00000000000000000000000000000001"
  allowNonRestoredState: false
  groupId: interaction-diff-engine
  interactionTtlSeconds: 300
  allowedLatenessSeconds: 60
  stateTtlSeconds: 86400
  checkpointIntervalMs: 30000
  restartAttempts: 3
  restartDelaySeconds: 10
```

| Value | Meaning |
| --- | --- |
| `fixedJobId` | Stable 32-hex job ID used for recovery and duplicate prevention |
| `allowNonRestoredState` | Permit an upgrade to discard savepoint state that no longer maps to an operator |
| `interactionTtlSeconds` | Inactivity period before Flink emits a delete |
| `allowedLatenessSeconds` | Out-of-order bound used to generate watermarks |
| `stateTtlSeconds` | Cleanup TTL for keyed Flink state |
| `checkpointIntervalMs` | Source-offset and state checkpoint interval |
| `restartAttempts` | Fixed-delay job restart attempts |
| `restartDelaySeconds` | Delay between restart attempts |

`stateTtlSeconds` must exceed interaction TTL plus allowed lateness.

## Kafka contract

The input topic contains OTLP JSON metrics from the Collector. The output topic
contains interaction commands:

```yaml
streamContract:
  kafka:
    brokers:
      - kafka.internal.example:9092
    security:
      protocol: SASL_SSL
      saslMechanism: SCRAM-SHA-256
      existingSecret: servicegraph-kafka-auth
  topics:
    servicegraphMetrics: otel.servicegraph.metrics
    interactionEvents: graph.interactions.events
```

The source starts from committed offsets or `earliest` when the consumer group
has no offsets. Auto topic creation is disabled. The output sink is
at-least-once.

## Persistent state

The default chart uses one shared claim for:

- Kubernetes HA metadata;
- checkpoints;
- savepoints.

```yaml
storage:
  createClaim: true
  storageClassName: rwx
  size: 10Gi
  accessModes: [ReadWriteMany]
  retainClaim: true
```

Use `storage.existingClaim` to reference a pre-provisioned claim. A multi-node
cluster requires storage that all eligible JobManager and TaskManager nodes can
mount. The default file-based design is intentionally simple for internal
clusters; validate the storage system's availability guarantees separately.

With `retainClaim: true`, Helm annotates a created claim with
`helm.sh/resource-policy: keep`. Uninstalling the release does not delete it.

## Runtime and submission

Helm renders the JobManager and TaskManager Deployments directly. A
post-install Job waits for the REST Service and runs:

```text
flink run --detached -m servicegraph-diff-rest:8081 --pyModule otel_servicegraph_diff.flink_job
```

The submitter skips submission if the fixed job ID is already active and
rejects accidental reuse of a terminal job ID.

On every Helm upgrade, a `pre-upgrade` Job gracefully stops the active job and
records its savepoint path on the state claim. The JobManager and TaskManagers
then roll to the new Helm revision. The submitter runs as a `post-upgrade` hook
and restores the new package and job configuration from the savepoint with the
same fixed job ID.

Keep `application.clusterId`, `job.fixedJobId`, and the state claim unchanged
across this operation. The automatic upgrade fails closed if the active job is
missing, the savepoint cannot be created, or the new job cannot restore all
savepoint state. `job.allowNonRestoredState=true` relaxes only the final state
mapping check and should be used for reviewed topology changes.

Kubernetes HA stores job metadata pointers in ConfigMaps and durable metadata
on the state claim. When the JobManager pod is replaced, Flink recovers the
same job and restores keyed state and source progress from the latest completed
checkpoint. One JobManager means recovery includes brief downtime.

The runtime ServiceAccount needs namespace-scoped ConfigMap CRUD/list/watch.
Set `serviceAccount.create=false` and `rbac.create=false` to use a
platform-provided account. A workload does not select an existing RoleBinding
by name. The existing RoleBinding must already name the configured
ServiceAccount as a subject.

## Logs

Flink writes control-plane logs to JobManager stdout and operator, Kafka, and
Python worker logs to TaskManager stdout. Set `logging.rootLevel` to control
the root level; the default is `INFO`.

```console
kubectl logs -n servicegraph-system \
  deployment/processing-servicegraph-flink-jobmanager --follow
kubectl logs -n servicegraph-system \
  deployment/processing-servicegraph-flink-taskmanager --follow --prefix
kubectl logs -n servicegraph-system <pod-name> --previous
```

## Environment mapping

The chart maps values to these application variables:

| Environment variable | Helm value |
| --- | --- |
| `KAFKA_BOOTSTRAP_SERVERS` | `streamContract.kafka.brokers` |
| `INTERACTION_DIFF_INPUT_TOPIC` | `streamContract.topics.servicegraphMetrics` |
| `INTERACTION_DIFF_OUTPUT_TOPIC` | `streamContract.topics.interactionEvents` |
| `INTERACTION_DIFF_GROUP_ID` | `job.groupId` |
| `INTERACTION_DIFF_TTL_SECONDS` | `job.interactionTtlSeconds` |
| `INTERACTION_DIFF_ALLOWED_LATENESS_SECONDS` | `job.allowedLatenessSeconds` |
| `INTERACTION_DIFF_STATE_TTL_SECONDS` | `job.stateTtlSeconds` |
| `FLINK_CHECKPOINT_INTERVAL_MS` | `job.checkpointIntervalMs` |
| `FLINK_PARALLELISM` | `application.parallelism` |

## Validate

```console
helm lint deploy/helm/servicegraph-flink
helm template processing deploy/helm/servicegraph-flink \
  --namespace servicegraph-system \
  --values internal-flink-values.yaml
```

The rendered output includes the complete runtime topology, the install and
upgrade submitter, and the pre-upgrade savepoint hook.
