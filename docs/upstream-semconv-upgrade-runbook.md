# Upstream Semconv Upgrade Runbook

This runbook describes how to move the pinned OpenTelemetry semantic convention
snapshot to a newer upstream version.

The project does not fetch OpenTelemetry models at runtime. The upstream model is
vendored under `upstream/otel-semconv/<version>/model` and recorded in
`upstream/otel-semconv.lock.json`.

## When To Upgrade

Upgrade when you want this project to understand entities or attributes added to
a newer OpenTelemetry semantic convention release.

Do not upgrade as a casual dependency bump. The upstream model is part of the
project contract, because it affects generated entities, Collector dimensions,
relationship validation, and graph shape.

## Inputs

Choose the exact upstream tag, for example:

```text
v1.44.0
```

Use an OpenTelemetry semantic-conventions release archive:

```text
https://github.com/open-telemetry/semantic-conventions/archive/refs/tags/<version>.zip
```

## Manual Upgrade Steps

1. Create the new version directory:

```powershell
New-Item -ItemType Directory upstream\otel-semconv\v1.44.0 -Force
```

2. Download the release archive outside the repo or into a temporary directory.

3. Extract only the upstream `model` directory into:

```text
upstream/otel-semconv/v1.44.0/model
```

The final path should contain files such as:

```text
upstream/otel-semconv/v1.44.0/model/service/entities.yaml
upstream/otel-semconv/v1.44.0/model/k8s/entities.yaml
upstream/otel-semconv/v1.44.0/model/http/registry.yaml
```

4. Update `upstream/otel-semconv.lock.json`:

```json
{
  "source": {
    "kind": "github_release_source_archive",
    "repository": "open-telemetry/semantic-conventions",
    "version": "v1.44.0",
    "url": "https://github.com/open-telemetry/semantic-conventions/archive/refs/tags/v1.44.0.zip",
    "artifact": "upstream/otel-semconv/v1.44.0/model"
  }
}
```

5. Update every hardcoded upstream model path from the old version to the new
   version.

Current files that normally contain the version path:

- `scripts/generate_entities.py`
- `scripts/generate_collector_config.py`
- `scripts/validate_registry.py`
- `tests/test_registry_validation.py`
- `tests/test_graph_ingest.py`
- `docs/architecture.md`
- `README.md`

Use search to find remaining references:

```powershell
rg "v1\.43\.0|UPSTREAM_MODEL|upstream/otel-semconv" .
```

6. Regenerate committed artifacts:

```powershell
python scripts\generate_entities.py
python scripts\generate_collector_config.py
```

7. Validate the extension model against the new upstream model:

```powershell
python scripts\validate_registry.py
```

## Review Expected Changes

Review generated changes carefully. A semconv upgrade can change:

- generated entity classes under
  `packages/extended-opentelemetry-semconv/src/extended_otel_semconv/generated`;
- Collector `service_graph` dimensions in `deploy/local/otelcol.yaml`;
- validation failures if an extension now redefines something upstream added;
- graph shape if upstream added or removed identifying entity attributes.

If validation fails because upstream added an entity or attribute that this repo
previously defined as an extension, remove the extension definition and reference
the upstream definition instead. This is the core rule of the project: extend
OpenTelemetry, do not rebuild it.

## Required Checks

Run the full local validation set:

```powershell
python scripts\validate_registry.py
python scripts\generate_entities.py --check
python scripts\generate_collector_config.py --check
python -m ruff check .
python -m mypy src scripts tests
python -m pytest
docker compose config
```

Then run the live local stack at least once:

```powershell
docker compose up --build
```

Check that:

- the Collector starts without config errors;
- `graph` becomes healthy;
- Collector logs show service graph logs exported to Kafka;
- generated Collector servicegraph dimensions still match the merged registry.

## Commit Guidance

Keep the upgrade in one commit when possible. The commit should include:

- the new upstream snapshot;
- the lock-file change;
- generated Python entities;
- generated Collector config;
- any extension cleanup required by new upstream definitions;
- docs path updates.

Do not keep the old upstream version directory unless there is an explicit reason
to support multiple versions at the same time.
