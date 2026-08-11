# Extended OpenTelemetry Semantic Conventions

Define the entities and relationships that matter to your organization, derive
them from OpenTelemetry, and maintain them as a live graph.

The project merges a pinned OpenTelemetry semantic-conventions registry with
your extensions, generates typed entity models and Collector dimensions, and
turns service-graph telemetry into authoritative node and edge lifecycle events.

```text
OTLP traces
  -> Collector router
  -> Collector service_graph backend
  -> Kafka: otel.servicegraph.metrics
  -> HA PyFlink graph-element job
  -> Kafka: graph.elements.events
  -> ArangoDB current-state graph
  -> read-only GraphBinary Gremlin
```

The repository contains:

- `packages/extended-opentelemetry-semconv-models`: generated Pydantic entities
  and relationships.
- `packages/extended-opentelemetry-semconv-codegen`: registry sources,
  validation, and deterministic generation.
- `packages/extended-opentelemetry-servicegraph-engine`: pure interaction and
  graph-element lifecycle transitions.
- `packages/extended-opentelemetry-servicegraph-ingest`: Collector metric
  parsing and semantic normalization.
- `packages/extended-opentelemetry-semconv-gremlin`: typed GraphBinary client.
- `services/otel-servicegraph-diff`: validated settings and PyFlink wiring.
- `services/servicegraph-demo`: optional live synthetic OTLP traffic.
- `services/servicegraph-indexer`: ArangoDB topology initialization and Kafka
  lifecycle projection.
- `services/servicegraph-gremlin`: the pinned TinkerPop/ArangoDB provider runtime.
- `deploy/helm/servicegraph-collector`: the trace router and service-graph
  backend.
- `deploy/helm/servicegraph-demo`: the optional traffic generator.
- `deploy/helm/servicegraph-flink`: the standalone Flink Session runtime.
- `deploy/helm/servicegraph-arangodb`: optional local-development ArangoDB.
- `deploy/helm/servicegraph-indexer`: initializer and current-state indexer.
- `deploy/helm/servicegraph-gremlin`: read-only Gremlin Server.

Kafka and topic creation remain external platform concerns. Deployment uses
Helm only and requires no CRDs or Kubernetes operator.

## Documentation

The MkDocs site covers the semantic model, custom entities, configuration,
deployment, operations, event contracts, and development.

```powershell
python -m pip install -e ".[docs]"
python -m mkdocs serve
```

Start with:

- [Documentation home](docs/index.md)
- [Local quickstart](docs/getting-started/quickstart.md)
- [Your first custom entity](docs/getting-started/custom-entity.md)
- [Kubernetes deployment](docs/deployment-and-operations.md)
- [Graph element event schema](docs/reference/event-schema.md)

## Validation

```powershell
python -m extended_otel_semconv_codegen --check
python -m mkdocs build --strict
python -m ruff check .
python -m pyright
python -m pytest -m "not e2e"
helm lint deploy/helm/servicegraph-collector
helm lint deploy/helm/servicegraph-demo
helm lint deploy/helm/servicegraph-flink
helm lint deploy/helm/servicegraph-arangodb
helm lint deploy/helm/servicegraph-indexer
helm lint deploy/helm/servicegraph-gremlin
```
