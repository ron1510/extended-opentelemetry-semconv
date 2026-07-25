# Interaction Lifecycle

An interaction represents activity between a client and server for one
connection type and canonical set of dimensions.

## Identity

The interaction ID is a SHA-256 digest of:

- client service name;
- server service name;
- normalized connection type;
- canonical, sorted dimensions.

Metric name is excluded. Request and failed-request totals therefore update the
same interaction.

## Activity

The Flink job accepts the Collector's
`traces_service_graph_request_total` and
`traces_service_graph_request_failed_total` metrics.

An observation counts as activity when:

- this is the first metric for the interaction;
- a cumulative counter changes;
- a cumulative stream start time changes, indicating a reset;
- a delta value is non-zero.

Repeated cumulative values and zero deltas do not refresh expiry. Older
out-of-order observations do not replace newer state.

## Upserts

On new activity, Flink creates the current interaction payload and calculates a
deterministic payload hash. It emits an `upsert` when the state is new or its
payload changes.

The payload includes:

- client, server, and connection type;
- dimensions and current metric values;
- typed entity references;
- normalized graph nodes and edges.

## Expiry and deletes

Each active interaction has event-time and processing-time expiry timers. The
event-time timer provides telemetry-time semantics; the processing-time timer
ensures an idle stream can still expire.

When the configured interaction TTL passes without activity, Flink emits one
`delete` command and marks the state inactive. A later observation can reactivate
the interaction with a new upsert.

`stateTtlSeconds` controls backend state cleanup and must be greater than:

```text
interactionTtlSeconds + allowedLatenessSeconds
```

State cleanup is not the user-visible deletion policy. Flink emits the delete
command before backend state is eventually removed.

## Delivery semantics

Kafka source offsets are committed with Flink checkpoints. The sink uses
at-least-once delivery. A retry may therefore produce duplicate commands.

Consumers should:

- partition or group by `interaction_id`;
- treat upsert and delete as idempotent commands;
- optionally deduplicate by deterministic `event_id`;
- preserve per-key Kafka order;
- never calculate an independent stale timeout.

The optional UI follows this model and keeps an offset per Kafka partition in
the same SQLite transaction as projection changes.
