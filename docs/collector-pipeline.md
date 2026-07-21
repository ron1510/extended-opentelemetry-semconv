# Collector Pipeline

The Collector remains responsible for receiving traces, running the
`service_graph` connector, and exporting servicegraph metrics to Kafka.

The generated config lives at `deploy/local/otelcol.yaml`.

## Dimensions

Servicegraph dimensions are generated from the merged entity registry:

1. load upstream and extension entities;
2. find relationships where `source_signals` includes `service_graph`;
3. collect attribute refs from participating entities;
4. exclude template refs such as labels, annotations, and selectors by default.

This avoids using every known semconv attribute while still preserving the
entity fields the interaction diff engine can reason about.

The current policy includes every scalar field on participating entities. That
is semantically complete but can include high-cardinality identifiers such as
pod UIDs, service instance IDs, and process IDs. Review and load-test the
generated list against production traffic before rollout; narrowing it must be
an explicit registry policy change, not an ad hoc Collector edit.

## Production Notes

- `memory_limiter` remains first in every pipeline.
- `batch` is kept for trace and metric export efficiency.
- The `service_graph` connector is stateful; scaled deployments need traceID
  stickiness before the servicegraph tier.
- Kafka exporter retry is configured for durable local buffering.
