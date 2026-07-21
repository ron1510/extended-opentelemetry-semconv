# Interaction Diff Engine

The graph engine turns servicegraph metric datapoints into a live interaction
event stream.

Important modules:

- `graph/metrics.py`: parses OTLP JSON/protobuf servicegraph metrics.
- `graph/dimensions.py`: selects servicegraph dimensions from modeled entity fields.
- `graph/interaction.py`: pure Pydantic observation, state, event, and diff logic.
- `graph/service_graph.py`: formats servicegraph datapoints into entity/edge observations for shared tests and relationship behavior.
- `services/interaction_diff/`: PyFlink service wiring.

## Interaction Observations

Each servicegraph datapoint becomes an `InteractionObservation` when it contains
`client` and `server` attributes.

The interaction ID is derived from:

- client
- server
- normalized connection type
- canonicalized datapoint dimensions

Metric name is intentionally excluded from identity so request totals and failed
totals update the same interaction state.

## State And Diff Rules

Flink stores one `InteractionState` per interaction ID.

An upsert event is emitted only when no state exists or the payload hash changes.
An unchanged cumulative counter neither emits an event nor refreshes expiry.
Counter advances and resets are activity; delta observations are activity when
their value is non-zero.

A delete event is emitted when the event-time expiry timer fires and the state
has not been refreshed beyond that timer. A matching processing-time safety
timer guarantees deletion when all Kafka partitions are idle and no watermark
can advance.

## Output Contract

Events are written to `graph.interactions.events` with:

- `schema_version`
- `event_id`
- `operation`
- `interaction_id`
- `observed_at_unix_nano`
- `emitted_at_unix_ms`
- `payload_hash`
- `interaction`

Malformed input records are written to `graph.interactions.dlq`.

Kafka records use `interaction_id` as the record key and the event envelope as
the value. This preserves partition ordering for each interaction. Delivery is
at least once; deterministic event IDs and downstream upsert/delete operations
provide idempotency.

## State Compatibility

Persisted `InteractionState` is strict and versioned by its Flink operator UID
and state descriptor. A state-contract change requires an explicit savepoint
migration or a new operator UID. Flink must not silently accept an incompatible
checkpoint.
