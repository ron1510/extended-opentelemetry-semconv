# Development

Use the registry as the source of truth.

Do not hand-edit generated entity modules or the local Collector config. Change
the model, then regenerate.

## Commands

Validate the extension registry:

```powershell
python scripts\validate_registry.py
```

Regenerate committed artifacts:

```powershell
python scripts\generate_entities.py
python scripts\generate_collector_config.py
```

Check generated artifacts:

```powershell
python scripts\generate_entities.py --check
python scripts\generate_collector_config.py --check
```

Run code quality checks:

```powershell
python -m ruff check .
python -m mypy src scripts tests
python -m pytest
```

Check the Docker Compose wiring:

```powershell
docker compose config
```

Run the local stack:

```powershell
docker compose up --build
```

For what each check proves and how the local runtime is wired, see
[Test Environment](test-environment.md).

For upstream OpenTelemetry model upgrades, see
[Upstream Semconv Upgrade Runbook](upstream-semconv-upgrade-runbook.md).

## Code Style

Keep domain decisions in typed pure functions where possible.

Use stateful classes only when there is real state or lifecycle. The formatter
and schema generation paths should stay as typed pure functions so they can be
tested directly and reused behind different Kafka/runtime adapters.

Prefer Pydantic models for serialized domain objects such as registry documents,
entities, graph nodes, graph edges, and graph snapshots.

## Documentation Expectations

When changing behavior, update the closest durable documentation:

- registry rules: `docs/registry-extensions.md`;
- graph ingestion or edge semantics: `docs/graph-engine.md`;
- Collector config or pipeline shape: `docs/collector-pipeline.md`;
- upstream versioning: `docs/upstream-semconv-upgrade-runbook.md`;
- tests or runtime checks: `docs/test-environment.md`.

Prefer concise module docstrings for code boundaries that are not obvious from
the function names. Avoid comments that restate a single line of code.
