# Registry And Upstream Maintenance

Extensions live under `model/extensions`. Use them only for entities,
attributes, and relationships that OpenTelemetry does not already define.
Extension entities may reference upstream attributes.

Runtime entity classes are generated only for entities with at least one
identifying attribute. Relationships create graph edges when their source and
target entities are observed together. A `service -> service` dependency is
reserved for service-graph telemetry.

The generators enforce:

- no upstream attribute or entity redefinition;
- valid entity attribute references;
- valid relationship source and target entities;
- known relationship source signals;
- no duplicate extension definitions.

After changing an extension, run:

```powershell
python scripts\generate_entities.py
python scripts\generate_collector_dimensions.py
python -m pytest
```

## Upstream Snapshot

The project vendors an exact OpenTelemetry model under
`upstream/otel-semconv/<version>/model` and records its source in
`upstream/otel-semconv.lock.json`. The snapshot is build input and is never
downloaded at runtime.

To upgrade:

1. Select an exact semantic-conventions release tag.
2. Extract only its `model` directory under a new versioned directory.
3. Update `upstream/otel-semconv.lock.json`.
4. Update hardcoded `UPSTREAM_MODEL` paths in both generators and registry
   behavior tests.
5. Regenerate entities and Collector dimensions.
6. Run the complete validation set from `docs/development.md`.
7. Remove the previous snapshot unless multiple versions are intentionally
   supported.

Review generated changes carefully. An upstream upgrade can change public
entity classes, identifying attributes, Collector dimensions, and graph shape.
If upstream now owns an extension definition, delete the extension and use the
upstream definition.
