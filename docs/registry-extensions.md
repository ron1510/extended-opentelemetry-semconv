# Registry Extensions

Extensions live under `model/extensions`.

Use extension files for things OpenTelemetry does not already define. If an
entity or attribute exists in the upstream OpenTelemetry snapshot, reference it;
do not redefine it.

When the upstream snapshot changes, re-check every extension against the new
OpenTelemetry model. If upstream now owns an entity or attribute that this repo
previously extended, delete the extension definition and use upstream instead.

## Attributes

Attributes are declared in `attribute_group` entries.

```yaml
groups:
  - id: registry.app
    type: attribute_group
    attributes:
      - id: app.endpoint.route
        type: string
        stability: development
        brief: Application endpoint route.
```

## Entities

Entities use OpenTelemetry-style `entity` entries. Runtime Python classes are
generated only when the entity has at least one identifying attribute.

```yaml
groups:
  - id: entity.app.endpoint
    type: entity
    name: app.endpoint
    stability: development
    brief: Application endpoint exposed by a service.
    attributes:
      - ref: service.name
        role: identifying
      - ref: service.namespace
        role: identifying
      - ref: http.request.method
        role: identifying
      - ref: http.route
        role: identifying
```

An extension entity can reference upstream attributes. That is the normal path.

## Relationships

Relationships are extension-only graph contracts.

```yaml
groups:
  - id: relationship.service_exposes_app_endpoint
    type: relationship
    name: exposes
    source_entity: service
    target_entity: app.endpoint
    source_signals: [trace, service_graph]
```

The current relationship engine is intentionally simple: when source and target
entities are observed together in one telemetry record, the graph creates the
relationship edge. Self-type dependency relationships such as `service -> service`
are reserved for service graph metrics.

Supported `source_signals` are:

- `trace`
- `service_graph`

## Validation Rules

`python scripts\validate_registry.py` enforces:

- extension attributes cannot redefine upstream attributes;
- extension entities cannot redefine upstream entities;
- extension entity attribute references must exist in upstream or extension attributes;
- relationship source and target entities must exist in upstream or extension entities;
- relationship source signals must be known;
- duplicate extension attributes, entities, and relationships are rejected.

## Adding A New Entity

1. Check the upstream model first.
2. Add only missing extension attributes.
3. Add the extension entity with identifying refs.
4. Add relationship definitions if the entity participates in the graph.
5. Run generation and validation:

```powershell
python scripts\validate_registry.py
python scripts\generate_entities.py
python scripts\generate_collector_config.py
python -m pytest
```

## Related Runbooks

- [Upstream Semconv Upgrade Runbook](upstream-semconv-upgrade-runbook.md)
- [Test Environment](test-environment.md)
