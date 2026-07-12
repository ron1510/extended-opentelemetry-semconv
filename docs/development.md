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

## Code Style

Keep domain decisions in typed pure functions where possible.

Use stateful classes only when there is real state or lifecycle. `EntityGraph`
has state because it owns the live node and edge maps, locking, and TTL pruning.
Relationship expansion and evidence merging are pure modules so they can be
tested directly.

Prefer Pydantic models for serialized domain objects such as registry documents,
entities, graph nodes, graph edges, and graph snapshots.
