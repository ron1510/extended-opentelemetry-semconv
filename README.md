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
  -> optional SQLite projection and graph UI
```

The repository contains:

- `packages/extended-opentelemetry-semconv`: registry loading, generated
  Pydantic entities, OTLP parsing, and pure graph transitions.
- `apps/otel-servicegraph-diff`: validated settings and PyFlink wiring.
- `apps/servicegraph-demo`: optional live synthetic OTLP traffic.
- `apps/servicegraph-ui`: Kafka command projection, API, and graph frontend.
- `deploy/helm/servicegraph-collector`: the trace router and service-graph
  backend.
- `deploy/helm/servicegraph-demo`: the optional traffic generator.
- `deploy/helm/servicegraph-flink`: the standalone Flink Session runtime.
- `deploy/helm/servicegraph-ui`: the optional visualization service.

Kafka and topic creation remain external platform concerns. Deployment uses
Helm only and requires no CRDs or Kubernetes operator.

## Documentation

The MkDocs site covers the semantic model, custom entities, configuration,
deployment, operations, event contracts, and development.

```powershell
python -m pip install mkdocs-material==9.7.7
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
python -m extended_otel_semconv.codegen --check
python -m mkdocs build --strict
python -m ruff check .
python -m pyright
python -m pytest -m "not e2e"
helm lint deploy/helm/servicegraph-collector
helm lint deploy/helm/servicegraph-demo
helm lint deploy/helm/servicegraph-flink
helm lint deploy/helm/servicegraph-ui
cd apps/servicegraph-ui/frontend
npm run build
```
