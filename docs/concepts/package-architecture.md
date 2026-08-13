# Python Package Architecture

Python ownership follows deployment and installation boundaries while keeping
domain responsibilities separated into internal modules.

```text
tools/semconv_codegen --generates--> extended-opentelemetry-semconv
                                         ^
                                         |
                         otel-servicegraph-diff
```

## Semantic SDK

`extended-opentelemetry-semconv` exposes `extended_otel_semconv`. It contains
generated entities and edges, deterministic identities, strict reconstruction,
and runtime relationship metadata. Its base installation depends only on
Pydantic.

The optional `gremlin` extra exposes `extended_otel_semconv.gremlin`. This
module validates element-preserving traversals and reconstructs GraphBinary
results as semantic models. The semantic core never imports `gremlinpython`.

## Flink application

`otel-servicegraph-diff` owns its graph lifecycle engine and Collector ingestion
adapters under `otel_servicegraph_diff.engine` and
`otel_servicegraph_diff.ingest`. These remain distinct source modules but are
released and deployed only with the Flink application.

The engine owns contributor aggregation, staleness, and graph-element lifecycle
events. Ingest owns OpenTelemetry protobuf parsing and direct expansion of
service-graph datapoints into semantic node and edge contributions.

## Repository tooling

`tools.semconv_codegen` owns the pinned upstream registry, local extensions,
validation, model rendering, Collector dimensions, relationship metadata, and
ArangoDB topology generation. It is contributor tooling and is never installed
in runtime images.

Architectural tests enforce that the semantic core does not import Gremlin,
Flink does not import repository tooling, and codegen does not import runtime
packages.
