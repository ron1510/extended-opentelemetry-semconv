param(
    [string]$ClusterName = "servicegraph-dev",
    [string]$NodeImage = "kindest/node:v1.29.12@sha256:62c0672ba99a4afd7396512848d6fc382906b8f33349ae68fb1dbfe549f70dec",
    [string]$CollectorImage = "otel/opentelemetry-collector-contrib:0.156.0",
    [string]$RedpandaImage = "redpandadata/redpanda:v24.3.5"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Chart = Join-Path $Root "deploy/helm/servicegraph-collector"
$KindConfig = Join-Path $Root "deploy/kind/kind-config.yaml"
$RedpandaManifest = Join-Path $Root "deploy/kind/redpanda.yaml"

foreach ($Command in @("kind", "kubectl", "helm", "docker")) {
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "Required command '$Command' is not available. Install it from an approved internal mirror."
    }
}

docker image inspect $NodeImage *> $null
docker image inspect $CollectorImage *> $null
docker image inspect $RedpandaImage *> $null

if (-not ((kind get clusters) -contains $ClusterName)) {
    kind create cluster --name $ClusterName --config $KindConfig --image $NodeImage
}

kind load docker-image --name $ClusterName $CollectorImage $RedpandaImage

kubectl apply -f $RedpandaManifest
kubectl -n servicegraph-system rollout status deployment/redpanda --timeout=180s
kubectl -n servicegraph-system wait --for=condition=complete job/redpanda-topics --timeout=180s

helm upgrade --install servicegraph $Chart `
    --namespace servicegraph-system `
    --values (Join-Path $Chart "values-kind.yaml") `
    --set-string image.repository=otel/opentelemetry-collector-contrib `
    --set-string image.tag=0.156.0 `
    --wait `
    --timeout 5m

helm test servicegraph --namespace servicegraph-system --timeout 2m
kubectl -n servicegraph-system get pods,services

Write-Host "Collector OTLP endpoint inside the cluster: servicegraph-servicegraph-collector-router:4317"
