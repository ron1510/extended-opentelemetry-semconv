# Architecture

The project is built around a strict ownership boundary.

OpenTelemetry owns upstream semantic convention entities and attributes. This
repository owns extension entities, extension attributes, relationship
definitions, generated semantic models, servicegraph dimension selection, and
the streaming interaction diff engine.

## Model Flow

1. Load the pinned upstream OpenTelemetry model from `upstream/otel-semconv/v1.43.0/model`.
2. Load extension model files from `model/extensions`.
3. Validate that extensions do not redefine upstream attributes or entities.
4. Merge upstream and extension registries in memory.
5. Generate Python entity classes from identifiable entities.
6. Generate Collector `service_graph` dimensions from entity fields that
   participate in `service_graph` relationships.

The upstream snapshot is intentionally checked in. The runtime does not fetch
OpenTelemetry models from the network.

## Runtime Flow

1. Applications send OTLP traces to the Collector.
2. The Collector `service_graph` connector derives request dependency metrics.
3. The Collector Kafka exporter writes servicegraph metrics to Kafka as OTLP JSON.
4. The PyFlink interaction diff job consumes those metrics.
5. Flink keeps one keyed state record per interaction ID.
6. Flink emits idempotent `upsert` and `delete` events to Kafka.
7. NiFi and MongoDB materialization are downstream of this repository.

## Runtime State

Flink keyed state is the runtime source of current interaction truth. It stores
latest observation time, metrics by name, dimensions, resolved entities, payload
hash, and event-time expiry timestamp.

Delete events are emitted from event-time timers when watermarks advance. A
matching processing-time safety timer handles a completely idle input stream;
it emits the same business expiry and is replaced on every real observation.
Flink state TTL remains defensive cleanup and is not a source of graph deletes.

## Production Notes

- Scaled Collector servicegraph tiers need traceID-sticky routing.
- Servicegraph output represents observed interactions, not full inventory.
- Dimension generation is registry-driven and excludes template refs such as
  labels, annotations, and selectors by default.
- Kafka event consumers must be idempotent by `interaction_id`.
