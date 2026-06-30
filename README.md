# Compute Asset Semantic Registry

This repository defines a raw-preserving semantic registry for deriving compute
assets, asset interfaces, and relationships from telemetry and infrastructure
state evidence.

The design intentionally does not rewrite incoming telemetry into internal
attribute names. Instead, it records what observed fields mean, which asset
interfaces they can identify, and which graph edges they support.

## Contents

- `registry/interfaces.yaml` defines compute asset interface signatures.
- `registry/relationships.yaml` defines graph edge semantics.
- `registry/evidence-sources.yaml` defines supported evidence source contracts.
- `schemas/` contains JSON Schemas for resolved evidence, entities,
  relationships, and future metric/alert contracts.
- `examples/` contains representative evidence records.
- `collector/servicegraph-optional.yaml` shows an optional raw-preserving
  OpenTelemetry Collector setup for dependency evidence.
- `scripts/validate_registry.py` validates the registry and examples with only
  the Python standard library.

## Core Rules

1. Raw telemetry is preserved.
2. Asset evidence is derived separately from telemetry and infrastructure state.
3. Existing OpenTelemetry Semantic Convention attributes are preferred.
4. Internal extension semantics fill gaps rather than replacing upstream names.
5. High-cardinality identifiers are valid entity evidence, but not metric
   dimensions.
6. Service graph output is dependency evidence, not the primary inventory source.

## Validate

```powershell
python scripts\validate_registry.py
```

The validator checks that registry files are valid JSON/YAML-subset documents,
that interface and relationship examples point at known types, and that example
records conform to the required top-level contract shape.
