param(
    [switch]$SkipImageBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$image = "extended-otel-flink-confidence:2.2.1-java11"

Push-Location $root
try {
    if (-not $SkipImageBuild) {
        docker build `
            --target development `
            --tag $image `
            --file apps/otel-servicegraph-diff/Dockerfile `
            .
        if ($LASTEXITCODE -ne 0) {
            throw "development image build failed"
        }
    }

    New-Item -ItemType Directory -Force -Path dist | Out-Null
    Remove-Item -Force -ErrorAction SilentlyContinue dist/*.whl
    docker run --rm `
        --volume "${root}:/workspace" `
        --workdir /workspace `
        $image `
        python -m pip wheel --no-deps --wheel-dir dist `
        packages/extended-opentelemetry-semconv apps/otel-servicegraph-diff
    if ($LASTEXITCODE -ne 0) {
        throw "wheel build failed"
    }
} finally {
    Pop-Location
}
