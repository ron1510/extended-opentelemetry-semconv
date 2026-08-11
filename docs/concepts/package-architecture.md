# Python Package Architecture

The Python implementation is split by installation reason and dependency
direction. Applications install only the layers they execute.

```text
codegen --generates--> models <-- engine <-- ingest
                          ^
                          |
                       gremlin
```

## Models

`extended-opentelemetry-semconv-models` exposes `extended_otel_semconv`.
It contains generated entities and edges, deterministic identities, strict
reconstruction, and runtime relationship metadata. Its only runtime dependency
is Pydantic.

## Codegen

`extended-opentelemetry-semconv-codegen` exposes
`extended_otel_semconv_codegen`. It owns the pinned upstream registry, local
extensions, validation, model rendering, Collector dimensions, relationship
metadata, and ArangoDB topology generation. It is never required in runtime
images.

## Engine

`extended-opentelemetry-servicegraph-engine` exposes
`extended_otel_servicegraph_engine`. It owns neutral metric and observation
contracts, interaction state, contributor aggregation, staleness, and graph
element lifecycle events. It has no Flink, Kafka, protobuf, or database
dependency.

## Ingest

`extended-opentelemetry-servicegraph-ingest` exposes
`extended_otel_servicegraph_ingest`. It parses Collector service-graph metrics,
extracts semantic entities and relationships, and creates engine observations.
OpenTelemetry protobuf is isolated to this package.

## Gremlin

`extended-opentelemetry-semconv-gremlin` exposes
`extended_otel_semconv_gremlin`. It validates element-preserving traversals and
reconstructs GraphBinary results as models. It is the only package that depends
on `gremlinpython`.

Architectural tests inspect imports in every package. Models cannot import an
adapter, the engine cannot import ingestion, and codegen cannot become a runtime
dependency.
