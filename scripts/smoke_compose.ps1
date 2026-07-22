param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$compose = @(
    "compose",
    "-f", "docker-compose.yaml",
    "-f", "docker-compose.smoke.yaml",
    "-f", "docker-compose.acceptance.yaml"
)

function Invoke-Compose {
    & docker @compose @args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose command failed: $args"
    }
}

function Wait-FlinkJob {
    $deadline = (Get-Date).AddMinutes(3)
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

try {
    if (-not $SkipBuild) {
        & "$PSScriptRoot/build_wheels.ps1"
        if ($LASTEXITCODE -ne 0) {
            throw "wheel build failed"
        }
    }
    $upArguments = @("--profile", "smoke", "up", "-d")
    if (-not $SkipBuild) {
        $upArguments += "--build"
    }
    $upArguments += @("kafka", "kafka-topics", "otelcol", "flink-jobmanager", "flink-taskmanager", "interaction-diff")
    $upArguments += @("wheel-installer")
    Invoke-Compose @upArguments
    Wait-FlinkJob

    Invoke-Compose --profile acceptance run --rm --no-deps acceptance-tools `
        python -m extended_otel_semconv_devtools.confidence.lifecycle `
        --bootstrap kafka:9092 `
        --otlp-endpoint http://otelcol:4318/v1/traces
} finally {
    Invoke-Compose --profile smoke --profile acceptance down --volumes --remove-orphans
}
