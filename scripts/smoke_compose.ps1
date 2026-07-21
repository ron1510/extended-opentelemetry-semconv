param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$compose = @(
    "compose",
    "-f", "docker-compose.yaml",
    "-f", "docker-compose.smoke.yaml"
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
    $upArguments = @("--profile", "smoke", "up", "-d")
    if (-not $SkipBuild) {
        $upArguments += "--build"
    }
    $upArguments += @("kafka", "kafka-topics", "otelcol", "flink-jobmanager", "flink-taskmanager", "interaction-diff")
    Invoke-Compose @upArguments
    Wait-FlinkJob

    Invoke-Compose --profile smoke run --rm --no-deps demo-once
    Start-Sleep -Seconds 7
    Invoke-Compose run --rm --no-deps interaction-diff python scripts/verify_smoke.py --bootstrap kafka:9092
} finally {
    Invoke-Compose --profile smoke down --volumes --remove-orphans
}
