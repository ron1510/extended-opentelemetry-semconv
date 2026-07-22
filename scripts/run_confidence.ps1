param(
    [switch]$SkipBuild,
    [int[]]$ThroughputRates = @(100, 250, 500, 1000, 2000, 4000),
    [int]$ThroughputDurationSeconds = 120,
    [int[]]$CardinalityBaselines = @(1000, 250, 100),
    [int[]]$Cardinalities = @(10000, 25000, 50000, 100000),
    [int]$SoakDurationSeconds = 600
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$reports = Join-Path $root "reports/confidence"
$runtimeImage = "extended-otel-flink-runtime:2.2.1-java11"
$baseCompose = @("compose", "-f", "docker-compose.yaml", "-f", "docker-compose.acceptance.yaml")
$smokeCompose = @(
    "compose", "-f", "docker-compose.yaml", "-f", "docker-compose.smoke.yaml", "-f", "docker-compose.acceptance.yaml"
)

function Invoke-Docker([string[]]$Arguments) {
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker command failed: $Arguments"
    }
}

function Wait-FlinkJob {
    $deadline = (Get-Date).AddMinutes(4)
    while ((Get-Date) -lt $deadline) {
        try {
            $jobs = Invoke-RestMethod -Uri "http://localhost:8081/jobs/overview" -TimeoutSec 5
            if ($jobs.jobs | Where-Object { $_.state -eq "RUNNING" }) {
                return
            }
        } catch {
            Start-Sleep -Seconds 2
            continue
        }
        Start-Sleep -Seconds 2
    }
    throw "Flink job did not reach RUNNING state"
}

function Start-Stack([string[]]$Compose) {
    $arguments = @($Compose) + @(
        "up", "-d", "kafka", "kafka-topics", "otelcol", "wheel-installer",
        "flink-jobmanager", "flink-taskmanager", "interaction-diff"
    )
    Invoke-Docker $arguments
    Wait-FlinkJob
}

function Stop-Stack([string[]]$Compose) {
    Invoke-Docker (@($Compose) + @("--profile", "acceptance", "down", "--volumes", "--remove-orphans"))
}

function Invoke-ScaleStage(
    [string]$Kind,
    [int]$Rate,
    [int]$Duration,
    [int]$Cardinality
) {
    $suffix = [Guid]::NewGuid().ToString("N").Substring(0, 8)
    $runId = "$Kind-$Rate-$Cardinality-$suffix"
    $filename = "scale-$Kind-$Rate-$Cardinality.json"
    & docker @baseCompose --profile acceptance run --rm --no-deps acceptance-tools `
        python -m extended_otel_semconv_devtools.confidence.scale `
        --endpoint http://otelcol:4318/v1/traces `
        --bootstrap kafka:9092 `
        --flink-url http://flink-jobmanager:8081 `
        --collector-metrics-url http://otelcol:8888/metrics `
        --run-id $runId `
        --rate $Rate `
        --duration $Duration `
        --batch-size 100 `
        --cardinality $Cardinality `
        --concurrency 8 `
        --error-ratio 0.05 `
        --drain-timeout 120 `
        --report "/reports/$filename" | Out-Host
    $passed = $LASTEXITCODE -eq 0
    return $passed
}

function Invoke-IsolatedScaleStage(
    [string]$Kind,
    [int]$Rate,
    [int]$Duration,
    [int]$Cardinality
) {
    Start-Stack $baseCompose | Out-Host
    try {
        $passed = Invoke-ScaleStage $Kind $Rate $Duration $Cardinality
        return $passed
    } finally {
        docker stats --no-stream --format "{{json .}}" | Add-Content -Encoding utf8 reports/confidence/docker-stats.jsonl
        Stop-Stack $baseCompose | Out-Host
    }
}

Push-Location $root
try {
    New-Item -ItemType Directory -Force -Path $reports | Out-Null
    Remove-Item -Force -ErrorAction SilentlyContinue "$reports/*.json"

    if (-not $SkipBuild) {
        & "$PSScriptRoot/build_wheels.ps1"
        if ($LASTEXITCODE -ne 0) { throw "wheel build failed" }
        Invoke-Docker ($baseCompose + @("--profile", "acceptance", "build", "wheel-installer", "acceptance-tools"))
    }

    C:/Users/ronba/AppData/Local/Python/bin/python.exe scripts/verify_artifacts.py `
        --dist dist --report reports/confidence/artifacts.json
    if ($LASTEXITCODE -ne 0) { throw "wheel inspection failed" }

    $defaultProbe = docker run --rm `
        -v "${root}/scripts/runtime_probe.py:/tmp/runtime_probe.py:ro" `
        $runtimeImage python /tmp/runtime_probe.py
    if ($LASTEXITCODE -ne 0) { throw "default runtime probe failed" }
    $arbitraryProbe = docker run --rm --user 1000720000:0 `
        -v "${root}/scripts/runtime_probe.py:/tmp/runtime_probe.py:ro" `
        $runtimeImage python /tmp/runtime_probe.py
    if ($LASTEXITCODE -ne 0) { throw "arbitrary UID runtime probe failed" }
    @{
        default = $defaultProbe | ConvertFrom-Json
        arbitrary_uid = $arbitraryProbe | ConvertFrom-Json
    } | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 reports/confidence/runtime.json

    docker run --rm `
        -v "${root}/dist:/wheels:ro" `
        -v "${root}/scripts/verify_clean_semantic.py:/tmp/verify_clean_semantic.py:ro" `
        --entrypoint /bin/sh `
        python:3.12.13-slim-bookworm `
        -ec "python -m pip install --disable-pip-version-check /wheels/extended_opentelemetry_semconv-0.1.0-py3-none-any.whl && python /tmp/verify_clean_semantic.py"
    if ($LASTEXITCODE -ne 0) { throw "clean semantic wheel import failed" }

    Start-Stack $smokeCompose
    try {
        Invoke-Docker ($smokeCompose + @(
            "--profile", "acceptance", "run", "--rm", "--no-deps", "acceptance-tools",
            "python", "-m", "extended_otel_semconv_devtools.confidence.lifecycle",
            "--bootstrap", "kafka:9092", "--otlp-endpoint", "http://otelcol:4318/v1/traces",
            "--report", "/reports/lifecycle.json"
        ))
    } finally {
        Stop-Stack $smokeCompose
    }

    Remove-Item -Force -ErrorAction SilentlyContinue reports/confidence/docker-stats.jsonl
    $highestPassingRate = 0
    $passingRates = @()
    foreach ($rate in $ThroughputRates) {
        $passed = Invoke-IsolatedScaleStage "throughput" $rate $ThroughputDurationSeconds 100
        if (-not $passed) { break }
        $highestPassingRate = $rate
        $passingRates += $rate
    }
    if ($highestPassingRate -le 0) {
        throw "no throughput stage passed"
    }

    $cardinalityRate = [Math]::Max([Math]::Floor($highestPassingRate * 0.5), 1)
    $lowestPassingRate = ($passingRates | Measure-Object -Minimum).Minimum
    $baselineRate = [Math]::Max([Math]::Floor($lowestPassingRate * 0.5), 1)
    $baselinePassed = $false
    foreach ($baseline in $CardinalityBaselines) {
        $baselineDuration = [Math]::Max([Math]::Ceiling($baseline / $baselineRate), 1)
        if (Invoke-IsolatedScaleStage "cardinality" $baselineRate $baselineDuration $baseline) {
            $baselinePassed = $true
            break
        }
    }
    if (-not $baselinePassed) {
        throw "cardinality baseline stage failed"
    }
    foreach ($cardinality in $Cardinalities) {
        $duration = [Math]::Max([Math]::Ceiling($cardinality / $cardinalityRate), 1)
        $passed = Invoke-IsolatedScaleStage "cardinality" $cardinalityRate $duration $cardinality
        if (-not $passed) { break }
    }

    $soakPassed = $false
    $soakRates = @($passingRates | Sort-Object -Descending | ForEach-Object {
        [Math]::Max([Math]::Floor($_ * 0.7), 1)
    } | Select-Object -Unique)
    foreach ($soakRate in $soakRates) {
        if (Invoke-IsolatedScaleStage "soak" $soakRate $SoakDurationSeconds 100) {
            $soakPassed = $true
            break
        }
    }
    if (-not $soakPassed) {
        throw "soak stage failed"
    }

    C:/Users/ronba/AppData/Local/Python/bin/python.exe scripts/render_confidence_report.py
    if ($LASTEXITCODE -ne 0) { throw "confidence report rendering failed" }
} finally {
    Pop-Location
}
