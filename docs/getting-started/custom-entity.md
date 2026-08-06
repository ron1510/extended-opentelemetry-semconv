# Your First Custom Entity

This walkthrough adds a `business.capability` entity and connects a service to
it with an `implements` relationship.

## 1. Define an attribute

Create `model/extensions/business/registry.yaml`:

```yaml
groups:
  - id: registry.business
    type: attribute_group
    attributes:
      - id: business.capability.name
        type: string
        stability: development
        brief: The stable name of a business capability.
```

Do not redefine an attribute already present in the pinned OpenTelemetry
registry.

## 2. Define the entity

Create `model/extensions/business/entities.yaml`:

```yaml
groups:
  - id: entity.business.capability
    type: entity
    name: business.capability
    stability: development
    brief: A business capability implemented by an application service.
    attributes:
      - ref: business.capability.name
        requirement_level: required
        role: identifying
```

At least one attribute must have `role: identifying`. All identifying
attributes must be present in an observation before the generated entity can be
created.

## 3. Define the relationship

Create `model/extensions/business/relationships.yaml`:

```yaml
groups:
  - id: relationship.service_implements_business_capability
    type: relationship
    name: implements
    source_entity: service
    target_entity: business.capability
    source_signals: [service_graph]
    stability: development
    brief: A service implements an observed business capability.
```

The deployed runtime currently materializes relationships sourced from
`service_graph`. The registry also accepts `trace` for library-level graph
normalization, but the supplied Kubernetes pipeline does not publish a separate
raw-trace graph stream.

## 4. Generate runtime artifacts

Run both generators from the repository root:

```console
python -m extended_otel_semconv.codegen
```

This updates:

- generated Pydantic entity classes;
- the package's relationship metadata;
- the Collector service-graph dimensions file.

Review and commit all generated changes with the registry source.

## 5. Validate

```console
python -m extended_otel_semconv.codegen --check
python -m pytest -m "not e2e"
```

Validation rejects duplicate upstream definitions, unknown attributes, unknown
entities, unsupported source signals, and duplicate extension IDs.

## 6. Emit the attribute

Your telemetry must include both `service.name` and
`business.capability.name` on the relevant side of an interaction. The
generated Collector dimensions carry the attribute into service-graph metrics.
Flink then creates the entity and relationship without custom operator code.

For example, a server span resource could contain:

```text
service.name = checkout-api
business.capability.name = order-fulfillment
```

## 7. Rebuild and deploy

Rebuild the Flink runtime image because it contains the generated Python package
and relationship metadata. Upgrade the Collector chart because its generated
dimensions ConfigMap changed. Rebuild the access image and run the initializer
against a fresh or intentionally migrated Elasticsearch index because the
strict generated mapping now contains the custom scalar fields.

After matching traffic is observed, query the typed API:

```console
curl -X POST http://localhost:8080/api/v1/elements/search \
  -H "Content-Type: application/json" \
  -d '{"pattern":{"op":"eq","field":"type","value":"business.capability"}}'
```

See [Registry Extensions](../registry-extensions.md) for the complete model and
generation rules.
