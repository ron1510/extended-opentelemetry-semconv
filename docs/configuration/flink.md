# Flink Job Configuration

The Flink chart submits one PyFlink job in native Kubernetes Application Mode.
The launcher, JobManagers, and TaskManagers use the same immutable runtime
image.

## Application sizing

```yaml
application:
  clusterId: servicegraph-diff
  parallelism: 3
  jobManagerReplicas: 2
  taskManagerSlots: 2
  jobManagerCpu: "0.5"
  taskManagerCpu: "1"
  jobManagerProcessMemory: 1200m
  taskManagerProcessMemory: 1800m
```

Flink creates TaskManagers dynamically according to parallelism and available
slots. Kubernetes resource limits must remain above the corresponding Flink
process-memory values.

The cluster ID must be unique within a namespace. Do not submit a second
application with the same ID.

## Interaction settings

```yaml
job:
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

## Why Helm renders a Job, not the Flink Deployment

The chart's post-install Job runs:

```text
flink run --target kubernetes-application
```

The Flink client then creates the long-running JobManager Deployment, Services,
ConfigMaps, and TaskManager pods. Those resources do not appear in
`helm template` because Flink creates them after submission.

The ServiceAccount receives namespace-scoped permissions to manage only the
resource types Flink requires.

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

The rendered output validates the launcher and its dependencies, not the
runtime resources Flink creates later.
