# Helm Values

This page summarizes user-facing values. The chart `values.yaml` files remain
the executable defaults.

## Collector

| Path | Default | Purpose |
| --- | --- | --- |
| `image.repository` | `otel/opentelemetry-collector-contrib` | Collector image |
| `image.tag` | `0.156.0` | Collector tag |
| `image.digest` | empty | Optional immutable digest |
| `router.replicaCount` | `2` | Fixed stateless router count |
| `router.queueSize` | `100000` | Load-balancer sending queue |
| `backend.replicaCount` | `2` | Fixed stateful backend count |
| `backend.serviceGraph.storeTtl` | `10s` | Unpaired span retention |
| `backend.serviceGraph.storeMaxItems` | `10000` | Pairing-store limit |
| `backend.serviceGraph.metricsFlushInterval` | `5s` | Metric flush period |
| `streamContract.kafka.brokers` | example broker | Kafka bootstrap servers |
| `streamContract.kafka.security.protocol` | `SASL_SSL` | `PLAINTEXT`, `SASL_PLAINTEXT`, or `SASL_SSL` |
| `streamContract.kafka.security.existingSecret` | `servicegraph-kafka-auth` | Existing SASL credentials |
| `streamContract.topics.servicegraphMetrics` | `otel.servicegraph.metrics` | Metrics topic |

Resource, scheduling, ServiceAccount, image-pull, and security-context values are
also available in the chart.

## Flink

| Path | Default | Purpose |
| --- | --- | --- |
| `image.ref` | internal example | Complete runtime image |
| `application.clusterId` | `servicegraph-diff` | Standalone Flink cluster ID |
| `application.parallelism` | `3` | Job parallelism |
| `application.jobManagerReplicas` | `1` | Restartable JobManager count |
| `application.taskManagerReplicas` | `2` | Fixed TaskManager count |
| `application.taskManagerSlots` | `2` | Slots per TaskManager |
| `job.fixedJobId` | `000...001` | Stable Flink job ID |
| `job.allowNonRestoredState` | `false` | Allow reviewed upgrades to discard unmapped savepoint state |
| `job.groupId` | `graph-element-engine` | Kafka source group |
| `job.interactionTtlSeconds` | `300` | Delete inactivity threshold |
| `job.allowedLatenessSeconds` | `60` | Watermark out-of-order bound |
| `job.stateTtlSeconds` | `86400` | Keyed-state cleanup TTL |
| `job.checkpointIntervalMs` | `30000` | Checkpoint interval |
| `job.restartAttempts` | `3` | Fixed-delay attempts |
| `logging.rootLevel` | `INFO` | Flink console log level |
| `rbac.create` | `true` | Create ConfigMap-only runtime RBAC |
| `storage.createClaim` | `true` | Create state claim |
| `storage.existingClaim` | empty | Use existing state claim |
| `storage.storageClassName` | `rwx` | Shared storage class |
| `storage.accessModes` | `[ReadWriteMany]` | State volume access |
| `storage.retainClaim` | `true` | Keep created claim on uninstall |

Kafka security fields and both topic names must match the Collector and
consumers.

## Elasticsearch access

| Path | Default | Purpose |
| --- | --- | --- |
| `image.repository` | internal example | Access image |
| `image.tag` | `0.3.0` | Access image tag |
| `projector.replicas` | `1` | Kafka projector replicas |
| `projector.groupId` | `servicegraph-elasticsearch-projector` | Kafka group |
| `api.replicas` | `1` | Query API replicas |
| `api.port` | `8080` | Internal HTTP port |
| `api.elasticsearchPageSize` | `1000` | Internal PIT page size |
| `elasticsearch.urls` | internal example | Elasticsearch endpoints |
| `elasticsearch.indexName` | `servicegraph-elements` | Projection index |
| `elasticsearch.numberOfShards` | `1` | Primary shards at creation |
| `elasticsearch.numberOfReplicas` | `1` | Replica shards |
| `elasticsearch.refreshInterval` | `5s` | Index refresh interval |

## Demo

| Path | Default | Purpose |
| --- | --- | --- |
| `collector.endpoint` | router OTLP HTTP URL | Trace destination |
| `traffic.emitIntervalSeconds` | `2` | Delay between batches |
| `traffic.topologyChangeIntervalSeconds` | `20` | Delay between graph changes |
| `traffic.initialEdges` | `2` | Initial active edges |
| `traffic.maxActiveEdges` | `6` | Maximum active edges |
| `traffic.requestsPerTick` | `3` | Traces per batch |
| `traffic.errorRate` | `0.08` | Failed trace probability |
| `traffic.serviceNamespace` | `shop` | Emitted service namespace |
| `traffic.instanceId` | `live-demo` | Instance-ID suffix |
| `traffic.randomSeed` | empty | Optional deterministic seed |

## Inspect exact defaults

```console
helm show values deploy/helm/servicegraph-collector
helm show values deploy/helm/servicegraph-flink
helm show values deploy/helm/servicegraph-access
helm show values deploy/helm/servicegraph-demo
```
