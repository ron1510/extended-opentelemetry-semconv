# Architecture

The project is built around a strict ownership boundary.

OpenTelemetry owns upstream semantic convention entities and attributes. This
repository owns only extension entities, extension attributes, relationship
definitions, runtime graph materialization, and generated local artifacts.

## Model Flow

1. Load the pinned upstream OpenTelemetry model from `upstream/otel-semconv/v1.43.0/model`.
2. Load extension model files from `model/extensions`.
3. Validate that extensions do not redefine upstream attributes or entities.
4. Merge upstream and extension registries in memory.
5. Generate Python entity classes from identifiable entities.
6. Generate Collector `service_graph` dimensions from merged registry attributes.

The upstream snapshot is intentionally checked in. The runtime does not fetch
OpenTelemetry models from the network.

## Runtime Flow

1. Applications send OTLP traces to the local Collector.
2. The Collector sends raw traces to the graph service.
3. The Collector `service_graph` connector derives request dependency metrics.
4. The Collector sends those service graph metrics to the graph service.
5. The graph service parses trace and metric attributes into semantic entities.
6. Registry relationship definitions turn co-observed entities into structural edges.
7. Service graph metrics create service dependency edges.
8. Nodes and edges are kept fresh by observation timestamps and TTL pruning.

## Ownership Boundary

This repository configures the OpenTelemetry Collector rather than replacing it.
The Collector remains responsible for OTLP receiving and service dependency
extraction. The Python graph engine is responsible for interpreting the resulting
telemetry as a typed entity graph.

## Runtime State

The current graph store is in memory. It is useful for model correctness,
ingestion behavior, and local development. A durable backend can be added behind
the same graph model later without changing the registry contract.
