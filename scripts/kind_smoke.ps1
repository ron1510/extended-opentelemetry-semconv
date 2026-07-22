param(
    [string]$Namespace = "servicegraph-system",
    [string]$Python = "C:\Users\ronba\AppData\Local\Python\bin\python.exe",
    [int]$LocalOtlpPort = 14318
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$RouterService = "service/servicegraph-servicegraph-collector-router"
$PreviousPythonPath = $env:PYTHONPATH
$PortForward = $null

try {
    $PortForward = Start-Process kubectl `
        -ArgumentList @("-n", $Namespace, "port-forward", $RouterService, "${LocalOtlpPort}:4318") `
        -WindowStyle Hidden `
        -PassThru
    Start-Sleep -Seconds 3
    if ($PortForward.HasExited) {
        throw "Collector port-forward exited before the smoke trace was sent."
    }

    $env:PYTHONPATH = @(
        (Join-Path $Root "tools"),
        (Join-Path $Root "packages/extended-opentelemetry-semconv/src")
    ) -join [IO.Path]::PathSeparator
    $env:OTLP_HTTP_ENDPOINT = "http://127.0.0.1:${LocalOtlpPort}/v1/traces"
    $env:DEMO_ONCE = "true"
    $env:DEMO_CLIENT_SERVICE = "kind-client"
    $env:DEMO_SERVER_SERVICE = "kind-server"
    & $Python -m extended_otel_semconv_devtools.telemetry.demo
    if ($LASTEXITCODE -ne 0) {
        throw "The local OTLP producer failed with exit code $LASTEXITCODE."
    }
}
finally {
    $env:PYTHONPATH = $PreviousPythonPath
    if ($null -ne $PortForward -and -not $PortForward.HasExited) {
        Stop-Process -Id $PortForward.Id -Force
    }
}

$Payload = kubectl -n $Namespace exec deployment/redpanda -- `
    rpk topic consume otel.servicegraph.metrics -X brokers=redpanda:9092 --num 1 --format '%v'
if ($LASTEXITCODE -ne 0) {
    throw "Kafka verification failed with exit code $LASTEXITCODE."
}
if ($Payload -notmatch "traces_service_graph_request_total") {
    throw "No service-graph request-total metric was observed in Kafka."
}

Write-Host "Verified paired traces through router, stateful service-graph backend, and Kafka."
