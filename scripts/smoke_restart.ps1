param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$compose = @(
    "compose",
    "-f", "docker-compose.yaml",
    "-f", "docker-compose.smoke.yaml",
    "-f", "docker-compose.restart.yaml"
)
$client = "restart-client"
$scriptsPath = (Resolve-Path "scripts").Path
$scriptsMount = "${scriptsPath}:/workspace/scripts:ro"

function Invoke-Compose {
    & docker @compose @args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose command failed: $args"
    }
}

function Get-RunningJobId {
    try {
        $jobs = Invoke-RestMethod -Uri "http://localhost:8081/jobs/overview" -TimeoutSec 5
        return ($jobs.jobs | Where-Object { $_.state -eq "RUNNING" } | Select-Object -First 1).jid
    } catch {
        return $null
    }
}

function Wait-FlinkReady {
    $deadline = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $deadline) {
        $jobId = Get-RunningJobId
        try {
            $taskManagers = Invoke-RestMethod -Uri "http://localhost:8081/taskmanagers" -TimeoutSec 5
            if ($jobId -and $taskManagers.taskmanagers.Count -gt 0) {
                return $jobId
            }
        } catch {
            Start-Sleep -Seconds 2
            continue
        }
        Start-Sleep -Seconds 2
    }
    throw "Flink job and TaskManager did not become ready"
}

function Wait-CheckpointAfter([string]$JobId, [long]$MinimumTimestamp) {
    $deadline = (Get-Date).AddMinutes(2)
    while ((Get-Date) -lt $deadline) {
        try {
            $checkpoints = Invoke-RestMethod -Uri "http://localhost:8081/jobs/$JobId/checkpoints" -TimeoutSec 5
            $completed = $checkpoints.latest.completed
            if ($completed -and $completed.trigger_timestamp -gt $MinimumTimestamp) {
                return
            }
        } catch {
            Start-Sleep -Seconds 1
            continue
        }
        Start-Sleep -Seconds 1
    }
    throw "No completed checkpoint captured the interaction"
}

try {
    $upArguments = @("--profile", "smoke", "up", "-d")
    if (-not $SkipBuild) {
        $upArguments += "--build"
    }
    $upArguments += @("kafka", "kafka-topics", "otelcol", "flink-jobmanager", "flink-taskmanager", "interaction-diff")
    Invoke-Compose @upArguments
    $jobId = Wait-FlinkReady

    $sentAfter = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    Invoke-Compose --profile smoke run --rm --no-deps `
        -e "DEMO_CLIENT_SERVICE=$client" `
        -e "DEMO_SERVER_SERVICE=restart-server" `
        demo-once
    Invoke-Compose run --rm --no-deps -v $scriptsMount interaction-diff `
        python /workspace/scripts/verify_restart.py --bootstrap kafka:9092 --client $client --require upsert --timeout-seconds 45
    Wait-CheckpointAfter -JobId $jobId -MinimumTimestamp $sentAfter

    Invoke-Compose kill --signal SIGKILL flink-taskmanager
    Invoke-Compose up -d flink-taskmanager
    $null = Wait-FlinkReady

    Invoke-Compose run --rm --no-deps -v $scriptsMount interaction-diff `
        python /workspace/scripts/verify_restart.py --bootstrap kafka:9092 --client $client `
        --require upsert --require delete --timeout-seconds 90
} finally {
    Invoke-Compose --profile smoke down --volumes --remove-orphans
}
