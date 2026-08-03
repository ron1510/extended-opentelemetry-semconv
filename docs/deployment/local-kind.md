# Local Kind Environment

This environment runs the production-shaped images and Helm charts on a local
Kind cluster. Redpanda provides Kafka only for the demonstration.

## Build images

```powershell
docker build `
  --tag extended-otel-flink-runtime:2.2.1-java11 `
  --file apps/otel-servicegraph-diff/Dockerfile .

docker build `
  --tag extended-otel-servicegraph-ui:0.1.2 `
  --file apps/servicegraph-ui/Dockerfile .

docker build `
  --tag extended-otel-servicegraph-demo:0.1.1 `
  --file apps/servicegraph-demo/Dockerfile .
```

## Create the cluster

Use an isolated kubeconfig so an unrelated current context cannot receive the
test deployment:

```powershell
$env:KUBECONFIG = Join-Path $env:TEMP "servicegraph-e2e-kubeconfig"

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

## Install Redpanda

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
  rpk topic create graph.elements.events --config cleanup.policy=compact
```

## Install the project

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
  --set application.jobManagerReplicas=1 `
  --set application.taskManagerReplicas=1 `
  --set application.taskManagerSlots=1 `
  --set 'streamContract.kafka.brokers[0]=streaming:9093' `
  --set streamContract.kafka.security.protocol=PLAINTEXT `
  --set storage.storageClassName=standard `
  --set storage.size=2Gi `
  --set 'storage.accessModes[0]=ReadWriteOnce' `
  --set podSecurityContext.runAsUser=9999 `
  --set podSecurityContext.runAsGroup=9999 `
  --set podSecurityContext.fsGroup=9999 `
  --set job.interactionTtlSeconds=30 `
  --set job.allowedLatenessSeconds=2 `
  --set job.stateTtlSeconds=120 `
  --set job.checkpointIntervalMs=5000 `
  --timeout 10m

kubectl rollout status deployment/processing-servicegraph-flink-jobmanager `
  --namespace servicegraph-e2e --timeout=10m
kubectl rollout status deployment/processing-servicegraph-flink-taskmanager `
  --namespace servicegraph-e2e --timeout=10m
```

RWO storage is valid for this test only because the Kind cluster has one node.
Use RWX storage for a multi-node deployment.

Install the optional UI and demo:

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

helm upgrade --install demo deploy/helm/servicegraph-demo `
  --namespace servicegraph-e2e `
  --set fullnameOverride=servicegraph-demo `
  --set image.repository=extended-otel-servicegraph-demo `
  --set image.tag=0.1.1 `
  --set image.pullPolicy=IfNotPresent `
  --set collector.endpoint=http://servicegraph-collector-router:4318/v1/traces `
  --wait --timeout 5m
```

## Inspect the system

```powershell
kubectl get pods -n servicegraph-e2e
kubectl logs -n servicegraph-e2e deployment/servicegraph-demo --follow
kubectl port-forward -n servicegraph-e2e service/servicegraph-ui 8080:8080
```

Open `http://localhost:8080`. The graph should grow, then rotate. Retired
interactions disappear only after Flink's 30-second TTL.

In another terminal, open the Flink UI:

```powershell
kubectl port-forward -n servicegraph-e2e `
  service/servicegraph-diff-rest 8081:8081
```

## Inspect Kafka

```powershell
kubectl exec -n servicegraph-e2e streaming-0 -c redpanda -- `
  rpk topic consume otel.servicegraph.metrics -o end -n 1

kubectl exec -n servicegraph-e2e streaming-0 -c redpanda -- `
  rpk topic consume graph.elements.events -o end -n 1
```

## Remove the environment

```powershell
kind delete cluster --name servicegraph-e2e
Remove-Item $env:KUBECONFIG -ErrorAction SilentlyContinue
```

This single-node environment proves application flow and pod recovery. It does
not prove node, availability-zone, or shared-storage failure recovery.
