# Kubernetes Deployment

This guide installs the service graph into an existing Kubernetes cluster. It
assumes Kafka is already available.

## Requirements

- Kubernetes 1.25 or newer;
- Helm 3;
- Kafka-compatible brokers reachable from the namespace;
- two pre-created topics;
- an internal container registry;
- shared persistent storage for Flink;
- an existing Kafka credentials Secret when using `SASL_SSL`.

The charts create standard Kubernetes resources and no CRDs. Workloads run as
non-root users with privilege escalation disabled, all capabilities dropped,
read-only root filesystems, and `RuntimeDefault` seccomp.

## Build and publish images

Build the Flink runtime from the repository root:

```console
docker build \
  --file apps/otel-servicegraph-diff/Dockerfile \
  --target runtime \
  --build-arg PIP_INDEX_URL=https://pypi.internal.example/simple \
  --secret id=maven_settings,src=$HOME/.m2/settings.xml \
  --tag registry.internal.example/extended-otel-flink-runtime:2.2.1-java11 \
  .
```

Build optional images:

```console
docker build --file apps/servicegraph-ui/Dockerfile \
  --tag registry.internal.example/extended-otel-servicegraph-ui:0.1.2 .

docker build --file apps/servicegraph-demo/Dockerfile \
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

For `SASL_SSL`, create one Secret in the target namespace containing:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: servicegraph-kafka-auth
type: Opaque
stringData:
  username: servicegraph
  password: replace-me
  ca.crt: |
    -----BEGIN CERTIFICATE-----
    ...
    -----END CERTIFICATE-----
```

Use your secret-management system rather than committing this manifest.
`PLAINTEXT` requires no Secret and is intended only for trusted development
networks.

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
      caKey: ca.crt
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
      caKey: ca.crt
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

## Validate before installation

```console
helm lint deploy/helm/servicegraph-collector
helm lint deploy/helm/servicegraph-flink

helm template collection deploy/helm/servicegraph-collector \
  --namespace servicegraph-system \
  --values internal-collector-values.yaml

helm template processing deploy/helm/servicegraph-flink \
  --namespace servicegraph-system \
  --values internal-flink-values.yaml
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

## Install optional visualization

Create values matching the same Kafka contract, then install:

```console
helm upgrade --install visualization deploy/helm/servicegraph-ui \
  --namespace servicegraph-system \
  --values internal-ui-values.yaml \
  --wait --timeout 5m
```

Expose it using your internal Ingress or a local port-forward:

```console
kubectl port-forward --namespace servicegraph-system \
  service/servicegraph-ui 8080:8080
```

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
7. Stop the contributing telemetry and wait for the configured TTL.
8. Confirm Flink emits element deletes and the UI removes them.

See [Monitoring](operations/monitoring.md) for commands and production signals.

## Uninstall behavior

Helm deletes the Flink Deployments, Service, and configuration. Kubernetes HA
ConfigMaps and retained Flink and UI claims can remain. Inspect and preserve
checkpoints or savepoints before deleting runtime resources or storage.
