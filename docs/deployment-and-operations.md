# Kubernetes Deployment

This guide installs the service graph into an existing Kubernetes cluster. It
assumes Kafka is already available.

## Requirements

- Kubernetes 1.25 or newer;
- Helm 3;
- Kafka-compatible brokers reachable from the namespace;
- two pre-created topics;
- Elasticsearch 8.15 or a later 8.x release reachable from the namespace;
- an internal container registry;
- shared persistent storage for Flink;
- existing Kafka and Elasticsearch credential Secrets when authentication is
  enabled.

The charts create standard Kubernetes resources and no CRDs. Workloads run as
non-root users with privilege escalation disabled, all capabilities dropped,
read-only root filesystems, and `RuntimeDefault` seccomp.

## Build and publish images

Build the Flink runtime from the repository root:

```console
docker build \
  --file services/otel-servicegraph-diff/Dockerfile \
  --target runtime \
  --build-arg PIP_INDEX_URL=https://pypi.internal.example/simple \
  --secret id=maven_settings,src=$HOME/.m2/settings.xml \
  --tag registry.internal.example/extended-otel-flink-runtime:2.2.1-java11 \
  .
```

Build the access image and optional demo image:

```console
docker build --file services/servicegraph-access/Dockerfile \
  --tag registry.internal.example/extended-otel-servicegraph-access:0.3.0 .

docker build --file services/servicegraph-demo/Dockerfile \
  --tag registry.internal.example/extended-otel-servicegraph-demo:0.1.1 .
```

Publish immutable tags or digests. The Flink image contains Python 3.12, the
application packages, Java serializers, and the Flink Kafka connector. No
runtime wheel side-loading is required.

Mirror the Collector image declared by the Collector chart when the cluster
cannot access public registries.

## Create Kafka topics

Create:

```text
otel.servicegraph.metrics
graph.elements.events
```

Choose partition counts for expected throughput and Flink parallelism. Both
topics should use retention and replication appropriate for your recovery
objectives. Disable automatic topic creation.

All installed components must use the same broker list, security configuration,
and topic names.

## Create the credentials Secret

For `SASL_PLAINTEXT` or `SASL_SSL`, create one Secret in the target
namespace containing:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: servicegraph-kafka-auth
type: Opaque
stringData:
  username: servicegraph
  password: replace-me
```

Use your secret-management system rather than committing this manifest.
`PLAINTEXT` requires no Secret. `SASL_PLAINTEXT` authenticates but does not
encrypt credentials or traffic and must be limited to a trusted internal
network. `SASL_SSL` uses the runtime image's default trust store; add private
certificate authorities to that trust store when building the image.

## Prepare values

Create `internal-collector-values.yaml`:

```yaml
image:
  repository: registry.internal.example/otelcol-contrib
  tag: "0.156.0"

streamContract:
  kafka:
    brokers: [kafka.internal.example:9093]
    security:
      protocol: SASL_SSL
      saslMechanism: SCRAM-SHA-256
      existingSecret: servicegraph-kafka-auth
      usernameKey: username
      passwordKey: password
  topics:
    servicegraphMetrics: otel.servicegraph.metrics
```

Create `internal-flink-values.yaml`:

```yaml
image:
  ref: registry.internal.example/extended-otel-flink-runtime:2.2.1-java11

serviceAccount:
  create: false
  name: servicegraph-flink
rbac:
  create: false

streamContract:
  kafka:
    brokers: [kafka.internal.example:9093]
    security:
      protocol: SASL_SSL
      saslMechanism: SCRAM-SHA-256
      existingSecret: servicegraph-kafka-auth
      usernameKey: username
      passwordKey: password
  topics:
    servicegraphMetrics: otel.servicegraph.metrics
    interactionEvents: graph.elements.events

storage:
  createClaim: false
  existingClaim: servicegraph-flink-state
```

See [Collector configuration](configuration/collector.md), [Flink
configuration](configuration/flink.md), and the [Helm values
reference](reference/helm-values.md) before changing topology or state values.

Create `internal-access-values.yaml` for the same Kafka contract and your
existing Elasticsearch service. See [Elasticsearch projection and query
API](deployment/elasticsearch.md) for endpoint, Secret, privilege, mapping,
query, and immutable shard-count requirements.

## Validate before installation

```console
helm lint deploy/helm/servicegraph-collector
helm lint deploy/helm/servicegraph-flink
helm lint deploy/helm/servicegraph-access

helm template collection deploy/helm/servicegraph-collector \
  --namespace servicegraph-system \
  --values internal-collector-values.yaml

helm template processing deploy/helm/servicegraph-flink \
  --namespace servicegraph-system \
  --values internal-flink-values.yaml

helm template access deploy/helm/servicegraph-access \
  --namespace servicegraph-system \
  --values internal-access-values.yaml
```

Review rendered Secrets references, images, storage classes, RBAC, resource
limits, and namespace policy compatibility.

## Install collection and processing

```console
helm upgrade --install collection deploy/helm/servicegraph-collector \
  --namespace servicegraph-system \
  --create-namespace \
  --values internal-collector-values.yaml \
  --wait --timeout 5m

helm upgrade --install processing deploy/helm/servicegraph-flink \
  --namespace servicegraph-system \
  --values internal-flink-values.yaml \
  --wait \
  --timeout 10m
```

Helm creates the standalone JobManager and TaskManager Deployments before its
post-install submitter runs. Confirm both workloads are ready:

```console
kubectl rollout status deployment/processing-servicegraph-flink-jobmanager \
  --namespace servicegraph-system \
  --timeout=10m
kubectl rollout status deployment/processing-servicegraph-flink-taskmanager \
  --namespace servicegraph-system \
  --timeout=10m
```

The existing ServiceAccount needs ConfigMap CRUD/list/watch for Kubernetes HA.
It does not need Pod, Deployment, Service, CRD, or finalizer permissions.

Subsequent `helm upgrade` operations stop the active job with a savepoint,
roll the runtime image and configuration, and restore the same job ID from
that savepoint. Keep the cluster ID, fixed job ID, and state claim stable.

## Install projection and query access

The pre-install initializer creates or verifies the strict index before the
projector and API start:

```console
helm upgrade --install access deploy/helm/servicegraph-access \
  --namespace servicegraph-system \
  --values internal-access-values.yaml \
  --wait --timeout 5m
```

Keep the API internal to the cluster or use a local port-forward:

```console
kubectl port-forward --namespace servicegraph-system \
  service/servicegraph-access-api 8080:8080
```

Kibana may inspect the `servicegraph-elements` index directly. Product
consumers should use the typed `POST /api/v1/elements/search` contract.

## Install optional demo traffic

```console
helm upgrade --install demo deploy/helm/servicegraph-demo \
  --namespace servicegraph-system \
  --values internal-demo-values.yaml \
  --wait --timeout 5m
```

Do not install the demo in a production telemetry namespace unless synthetic
services are explicitly desired.

## Verify end to end

1. Confirm both routers and both backends are ready.
2. Confirm the Flink job is `RUNNING`.
3. Confirm completed checkpoints continue increasing.
4. Send paired client/server traces to the router.
5. Confirm the metrics topic advances.
6. Confirm node and edge upserts appear.
7. Confirm the projector commits offsets and documents appear in Elasticsearch.
8. Query expected nodes and edges through the access API.
9. Stop the contributing telemetry and wait for the configured TTL.
10. Confirm Flink emits element deletes and Elasticsearch removes the
    corresponding documents.

See [Monitoring](operations/monitoring.md) for commands and production signals.

## Uninstall behavior

Helm deletes the Flink Deployments, Service, and configuration. Kubernetes HA
ConfigMaps and the retained Flink claim can remain. Uninstalling the access
chart does not delete the Elasticsearch index. Inspect and preserve checkpoints
or savepoints before deleting runtime resources or storage.
