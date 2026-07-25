# Extended OpenTelemetry Semantic Conventions

This project extends the OpenTelemetry entity model and turns service-graph
telemetry into a typed interaction event stream.

```text
OTLP traces
  -> Collector router
  -> Collector service_graph backend
  -> Kafka: otel.servicegraph.metrics
  -> HA PyFlink interaction diff job
  -> Kafka: graph.interactions.events
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
- `deploy/helm/servicegraph-flink`: the native Flink Application Mode runtime.
- `deploy/helm/servicegraph-ui`: the optional visualization service.

Kafka and topic creation remain external platform concerns. Deployment uses
Helm only and requires no CRDs or Kubernetes operator.

## Documentation

- [Architecture](docs/architecture.md)
- [Deployment and operations](docs/deployment-and-operations.md)
- [Development and release](docs/development.md)
- [Registry and upstream maintenance](docs/registry-extensions.md)

## Validation

```powershell
python scripts\generate_entities.py --check
python scripts\generate_collector_dimensions.py --check
python -m ruff check .
python -m pyright
python -m pytest
helm lint deploy/helm/servicegraph-collector
helm lint deploy/helm/servicegraph-demo
helm lint deploy/helm/servicegraph-flink
helm lint deploy/helm/servicegraph-ui
cd apps/servicegraph-ui/frontend
npm run build
```
