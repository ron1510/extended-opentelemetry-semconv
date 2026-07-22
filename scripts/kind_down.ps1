param([string]$ClusterName = "servicegraph-dev")

$ErrorActionPreference = "Stop"
if (-not (Get-Command kind -ErrorAction SilentlyContinue)) {
    throw "Required command 'kind' is not available."
}
kind delete cluster --name $ClusterName
