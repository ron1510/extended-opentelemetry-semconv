# Local Kind Environment

This environment runs the production-shaped images and Helm charts on a local
Kind cluster. Redpanda provides Kafka only for the demonstration.

## Build images

```powershell
docker build `
  --tag extended-otel-flink-runtime:2.2.1-java11 `
  --file services/otel-servicegraph-diff/Dockerfile .

docker build `
  --tag extended-otel-servicegraph-access:0.3.0 `
  --file services/servicegraph-access/Dockerfile .

docker build `
  --tag extended-otel-servicegraph-demo:0.1.1 `
  --file services/servicegraph-demo/Dockerfile .
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
kind load docker-image extended-otel-servicegraph-access:0.3.0 `
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

## Start Elasticsearch

Run Elasticsearch 8.15.5 on Docker's Kind network and expose its container IP
through a selectorless Kubernetes Service:

```powershell
docker run --detach --name servicegraph-e2e-elasticsearch `
  --network kind `
  --publish 127.0.0.1:9200:9200 `
  --env discovery.type=single-node `
  --env xpack.security.enabled=false `
  --env 'ES_JAVA_OPTS=-Xms512m -Xmx512m' `
  docker.elastic.co/elasticsearch/elasticsearch:8.15.5

$elasticsearchIp = (
  docker inspect servicegraph-e2e-elasticsearch | ConvertFrom-Json
)[0].NetworkSettings.Networks.kind.IPAddress

@"
apiVersion: v1
kind: Service
metadata:
  name: servicegraph-elasticsearch
  namespace: servicegraph-e2e
spec:
  ports:
    - name: http
      port: 9200
---
apiVersion: discovery.k8s.io/v1
kind: EndpointSlice
metadata:
  name: servicegraph-elasticsearch
  namespace: servicegraph-e2e
  labels:
    kubernetes.io/service-name: servicegraph-elasticsearch
addressType: IPv4
ports:
  - name: http
    protocol: TCP
    port: 9200
endpoints:
  - addresses: ["$elasticsearchIp"]
"@ | kubectl apply -f -
```

This unauthenticated HTTP configuration is only for the disposable local
environment.

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

Install the Elasticsearch projector, query API, and optional demo:

```powershell
helm upgrade --install access deploy/helm/servicegraph-access `
  --namespace servicegraph-e2e `
  --set fullnameOverride=servicegraph-access `
  --set image.repository=extended-otel-servicegraph-access `
  --set image.tag=0.3.0 `
  --set image.pullPolicy=IfNotPresent `
  --set 'elasticsearch.urls[0]=http://servicegraph-elasticsearch:9200' `
  --set elasticsearch.numberOfReplicas=0 `
  --set elasticsearch.auth.existingSecret= `
  --set elasticsearch.tls.existingSecret= `
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
kubectl port-forward -n servicegraph-e2e `
  service/servicegraph-access-api 8080:8080
```

Open `http://localhost:8080/docs` and submit recursive patterns to
`POST /api/v1/elements/search`. The result set should grow and rotate.
Retired interactions disappear only after Flink's 30-second TTL.

Optional Kibana inspection:

```powershell
docker run --detach --name servicegraph-e2e-kibana `
  --network kind `
  --publish 127.0.0.1:5601:5601 `
  --env ELASTICSEARCH_HOSTS=http://servicegraph-e2e-elasticsearch:9200 `
  docker.elastic.co/kibana/kibana:8.15.5
```

Open `http://localhost:5601` and create a data view for
`servicegraph-elements` without a time field.

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
docker rm --force servicegraph-e2e-kibana servicegraph-e2e-elasticsearch
Remove-Item $env:KUBECONFIG -ErrorAction SilentlyContinue
```

This single-node environment proves application flow and pod recovery. It does
not prove node, availability-zone, or shared-storage failure recovery.
