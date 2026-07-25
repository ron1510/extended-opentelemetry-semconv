# Deployment And Operations

## Prerequisites

- Kubernetes 1.25 or newer
- Helm 3
- two pre-created topics on Kafka-compatible brokers
- an RWX storage class or an existing RWX claim
- internally available Collector, Flink runtime, and optional demo and UI images
- an existing Kafka credentials Secret when using `SASL_SSL`

The charts use standard Kubernetes resources and create no CRDs. Every workload
runs as a non-root user with privilege escalation disabled, all capabilities
dropped, a read-only root filesystem, and `RuntimeDefault` seccomp.

## Installation

```powershell
helm upgrade --install servicegraph deploy/helm/servicegraph-collector `
  --namespace servicegraph-system --create-namespace `
  --values internal-collector-values.yaml

helm upgrade --install servicegraph-flink deploy/helm/servicegraph-flink `
  --namespace servicegraph-system `
  --values internal-flink-values.yaml

helm upgrade --install servicegraph-ui deploy/helm/servicegraph-ui `
  --namespace servicegraph-system `
  --values internal-ui-values.yaml

helm upgrade --install servicegraph-demo deploy/helm/servicegraph-demo `
  --namespace servicegraph-system `
  --values internal-demo-values.yaml
```

Collector values must configure the mirrored image and `streamContract` Kafka
brokers, security, and topic names. Flink values must configure `image.ref`,
the same stream contract, and either `storage.storageClassName` or
`storage.existingClaim`. The optional UI values configure its image, the same
interaction-events topic, and its SQLite claim.

The demo is optional and only needs the Collector router's OTLP HTTP endpoint.
It gradually grows and rotates synthetic service edges. Retired edges disappear
from the UI only after Flink applies its configured staleness policy and emits
delete commands.

Credentials are read from the Secret named by
`streamContract.kafka.security.existingSecret`. Do not place credentials in
values files. Both charts support `PLAINTEXT` for trusted development
environments and `SASL_SSL` with SCRAM-SHA-256 for internal deployments.

## Local Kind E2E

The local environment uses independent Helm releases:

- `streaming`: the official Redpanda chart, needed only when Kafka is not
  already available
- `collection`: the service-graph Collector chart
- `processing`: the Flink Application Mode chart
- `demo`: the optional synthetic trace producer chart
- `visualization`: the optional UI projection chart

It uses the same `extended-otel-flink-runtime:2.2.1-java11` image that is
published for deployment. Local Kafka addresses and smaller resource settings
are Helm values; there is no separate E2E image.

Create an isolated Kind cluster and load the runtime image:

```powershell
$env:KUBECONFIG = Join-Path $env:TEMP "servicegraph-e2e-kubeconfig"

docker build `
  --tag extended-otel-flink-runtime:2.2.1-java11 `
  --file apps/otel-servicegraph-diff/Dockerfile .

docker build `
  --tag extended-otel-servicegraph-ui:0.1.2 `
  --file apps/servicegraph-ui/Dockerfile .

docker build `
  --tag extended-otel-servicegraph-demo:0.1.1 `
  --file apps/servicegraph-demo/Dockerfile .

kind create cluster `
  --name servicegraph-e2e `
  --image kindest/node:v1.32.2 `
  --kubeconfig $env:KUBECONFIG `
  --wait 5m

kind load docker-image extended-otel-flink-runtime:2.2.1-java11 `
  --name servicegraph-e2e
kind load docker-image extended-otel-servicegraph-ui:0.1.2 `
  --name servicegraph-e2e
kind load docker-image extended-otel-servicegraph-demo:0.1.1 `
  --name servicegraph-e2e

kubectl create namespace servicegraph-e2e
```

Install a minimal single-broker Redpanda release and create the two topics:

```powershell
helm repo add redpanda https://charts.redpanda.com
helm repo update redpanda

helm upgrade --install streaming redpanda/redpanda `
  --version 26.1.3 `
  --namespace servicegraph-e2e `
  --set statefulset.replicas=1 `
  --set statefulset.podAntiAffinity.type=soft `
  --set console.enabled=false `
  --set external.enabled=false `
  --set tls.enabled=false `
  --set tuning.tune_aio_events=false `
  --set tests.enabled=false `
  --set storage.persistentVolume.size=2Gi `
  --set storage.persistentVolume.storageClass=standard `
  --set config.cluster.default_topic_replications=1 `
  --wait --timeout 10m

kubectl exec -n servicegraph-e2e streaming-0 -c redpanda -- `
  rpk topic create otel.servicegraph.metrics
kubectl exec -n servicegraph-e2e streaming-0 -c redpanda -- `
  rpk topic create graph.interactions.events
```

Install collection and processing:

```powershell
helm upgrade --install collection deploy/helm/servicegraph-collector `
  --namespace servicegraph-e2e `
  --set fullnameOverride=servicegraph-collector `
  --set 'streamContract.kafka.brokers[0]=streaming:9093' `
  --set streamContract.kafka.security.protocol=PLAINTEXT `
  --wait --timeout 5m

helm upgrade --install processing deploy/helm/servicegraph-flink `
  --namespace servicegraph-e2e `
  --set image.ref=extended-otel-flink-runtime:2.2.1-java11 `
  --set image.pullPolicy=IfNotPresent `
  --set application.parallelism=1 `
  --set application.jobManagerReplicas=2 `
  --set application.taskManagerSlots=1 `
  --set 'streamContract.kafka.brokers[0]=streaming:9093' `
  --set streamContract.kafka.security.protocol=PLAINTEXT `
  --set storage.storageClassName=standard `
  --set storage.size=2Gi `
  --set 'storage.accessModes[0]=ReadWriteOnce' `
  --set job.interactionTtlSeconds=30 `
  --set job.allowedLatenessSeconds=2 `
  --set job.stateTtlSeconds=120 `
  --set job.checkpointIntervalMs=5000 `
  --timeout 10m

kubectl rollout status deployment/servicegraph-diff `
  --namespace servicegraph-e2e --timeout=10m
kubectl get pods --namespace servicegraph-e2e
```

Do not add `--wait` to the Flink Helm command. The launcher is a post-install
hook, while Kind's `standard` storage class waits for a pod before binding its
PVC. Waiting on all Helm resources before running the hook would deadlock that
ordering. Wait for the native JobManager Deployment explicitly instead.
The `ReadWriteOnce` claim is valid here only because this Kind cluster has one
node. A multi-node deployment requires shared `ReadWriteMany` storage.

Install the optional visualization release:

```powershell
helm upgrade --install visualization deploy/helm/servicegraph-ui `
  --namespace servicegraph-e2e `
  --set fullnameOverride=servicegraph-ui `
  --set image.repository=extended-otel-servicegraph-ui `
  --set image.tag=0.1.2 `
  --set image.pullPolicy=IfNotPresent `
  --set 'streamContract.kafka.brokers[0]=streaming:9093' `
  --set streamContract.kafka.security.protocol=PLAINTEXT `
  --set streamContract.kafka.security.existingSecret= `
  --wait --timeout 5m
```

The UI replays `graph.interactions.events` into SQLite on its retained PVC.
Only Flink `upsert` and `delete` commands change the visible graph. The UI does
not calculate staleness or expire records.

Install the optional live traffic generator:

```powershell
helm upgrade --install demo deploy/helm/servicegraph-demo `
  --namespace servicegraph-e2e `
  --set fullnameOverride=servicegraph-demo `
  --set image.repository=extended-otel-servicegraph-demo `
  --set image.tag=0.1.1 `
  --set image.pullPolicy=IfNotPresent `
  --set collector.endpoint=http://servicegraph-collector-router:4318/v1/traces `
  --wait --timeout 5m
```

For the short local Flink TTL, the default demo grows the topology every 20
seconds and then rotates edges. Production TTLs naturally make deletion slower.
The generator never deletes graph state itself.

Send a paired CLIENT/SERVER trace through OTLP:

```powershell
$traceScript = @'
import time
import grpc
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import TraceServiceStub
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, InstrumentationScope, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span, Status

def kv(key, value):
    return KeyValue(key=key, value=AnyValue(string_value=value))

now = time.time_ns()
trace_id = bytes.fromhex("1122232425262728292a2b2c2d2e2f30")
client_id = bytes.fromhex("1122232425262728")
attrs = [kv("http.request.method", "POST"), kv("http.route", "/checkout")]
client = Span(
    trace_id=trace_id, span_id=client_id, name="POST /checkout",
    kind=Span.SPAN_KIND_CLIENT, start_time_unix_nano=now,
    end_time_unix_nano=now + 20_000_000, attributes=attrs,
    status=Status(code=Status.STATUS_CODE_OK),
)
server = Span(
    trace_id=trace_id, span_id=bytes.fromhex("2132232425262728"),
    parent_span_id=client_id, name="POST /checkout",
    kind=Span.SPAN_KIND_SERVER, start_time_unix_nano=now + 1_000_000,
    end_time_unix_nano=now + 18_000_000, attributes=attrs,
    status=Status(code=Status.STATUS_CODE_OK),
)
request = ExportTraceServiceRequest(resource_spans=[
    ResourceSpans(
        resource=Resource(attributes=[
            kv("service.name", "checkout-api"),
            kv("service.namespace", "shop"),
        ]),
        scope_spans=[ScopeSpans(
            scope=InstrumentationScope(name="e2e"), spans=[client]
        )],
    ),
    ResourceSpans(
        resource=Resource(attributes=[
            kv("service.name", "inventory-api"),
            kv("service.namespace", "shop"),
        ]),
        scope_spans=[ScopeSpans(
            scope=InstrumentationScope(name="e2e"), spans=[server]
        )],
    ),
])
with grpc.insecure_channel("servicegraph-collector-router:4317") as channel:
    TraceServiceStub(channel).Export(request, timeout=15)
'@

$encodedTrace = [Convert]::ToBase64String(
  [Text.Encoding]::UTF8.GetBytes($traceScript)
)

kubectl delete pod trace-producer --namespace servicegraph-e2e `
  --ignore-not-found
kubectl run trace-producer --namespace servicegraph-e2e `
  --image=extended-otel-flink-runtime:2.2.1-java11 `
  --image-pull-policy=IfNotPresent `
  --restart=Never `
  --command -- /usr/local/bin/python -c `
  "import base64; exec(base64.b64decode('$encodedTrace'))"
kubectl wait pod/trace-producer --namespace servicegraph-e2e `
  --for=jsonpath='{.status.phase}'=Succeeded --timeout=2m
```

Verify both Kafka stages. The second command must contain an `upsert` event
whose client is `checkout-api` and server is `inventory-api`; approximately 30
seconds later it also contains the expiry delete.

```powershell
kubectl exec -n servicegraph-e2e streaming-0 -c redpanda -- `
  rpk topic consume otel.servicegraph.metrics -o start -n 1

kubectl exec -n servicegraph-e2e streaming-0 -c redpanda -- `
  rpk topic consume graph.interactions.events -o start -n 1
```

Test JobManager failover by resolving the active REST endpoint, deleting that
pod, and checking recovery:

```powershell
$leaderIp = kubectl get endpoints servicegraph-diff-rest `
  --namespace servicegraph-e2e `
  -o jsonpath='{.subsets[0].addresses[0].ip}'
$leaderPod = kubectl get pods --namespace servicegraph-e2e `
  -l app=servicegraph-diff `
  -o jsonpath="{.items[?(@.status.podIP=='$leaderIp')].metadata.name}"

kubectl delete pod $leaderPod --namespace servicegraph-e2e
kubectl rollout status deployment/servicegraph-diff `
  --namespace servicegraph-e2e --timeout=5m
kubectl get pods --namespace servicegraph-e2e
```

The replacement JobManager must become ready, the REST endpoint must move to a
surviving or replacement pod, and the Flink UI must show the job as `RUNNING`
with completed checkpoints continuing to increase. Submit another trace after
the deletion to verify processing, not only control-plane recovery. This
single-node check proves JobManager pod recovery, not recovery from node or
storage failure.

Open the Flink UI locally:

```powershell
kubectl port-forward --namespace servicegraph-e2e `
  service/servicegraph-diff-rest 8081:8081
```

Open the service graph UI locally:

```powershell
kubectl port-forward --namespace servicegraph-e2e `
  service/servicegraph-ui 8080:8080
```

Then open `http://localhost:8080`.

Remove the environment when it is no longer needed:

```powershell
kind delete cluster --name servicegraph-e2e
Remove-Item $env:KUBECONFIG -ErrorAction SilentlyContinue
```

## Flink Application Mode

The Flink chart installs a post-install launcher Job. The launcher calls
`flink run --target kubernetes-application`; the native Flink client then
creates the long-running `servicegraph-diff` JobManager Deployment and dynamic
TaskManager pods. The Deployment is therefore visible in the cluster after
submission but is not present in `helm template` output.

Do not launch a second application with the same cluster ID. Upgrade the job by
taking a savepoint, stopping the existing application, installing the new
immutable image, and restoring from the verified savepoint.

## Runtime Settings

| Variable | Default |
| --- | --- |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:9092` |
| `KAFKA_SECURITY_PROTOCOL` | `PLAINTEXT` |
| `INTERACTION_DIFF_INPUT_TOPIC` | `otel.servicegraph.metrics` |
| `INTERACTION_DIFF_OUTPUT_TOPIC` | `graph.interactions.events` |
| `INTERACTION_DIFF_GROUP_ID` | `interaction-diff-engine` |
| `INTERACTION_DIFF_TTL_SECONDS` | `300` |
| `INTERACTION_DIFF_ALLOWED_LATENESS_SECONDS` | `60` |
| `INTERACTION_DIFF_STATE_TTL_SECONDS` | `86400` |
| `FLINK_CHECKPOINT_INTERVAL_MS` | `30000` |
| `FLINK_PARALLELISM` | `3` |
| `FLINK_RESTART_ATTEMPTS` | `3` |
| `FLINK_RESTART_DELAY_SECONDS` | `10` |

State TTL must exceed interaction TTL plus allowed lateness. `SASL_SSL`
additionally requires mechanism, username, password, CA file, and endpoint
identification settings.

## Operations

Monitor Collector export failures, Kafka lag, checkpoint age and failures,
JobManager restarts, `rejected_records`, and RWX volume capacity. Before an
upgrade, verify the savepoint exists and can be read by the new image. After an
upgrade, verify both topic flows and that checkpoints resume.

Uninstalling the Helm release does not delete a retained state claim. Native
Flink runtime resources may require explicit cleanup because Flink, not Helm,
creates them after submission.
