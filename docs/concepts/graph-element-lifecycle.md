# Graph Element Lifecycle

Flink is the authority for the current telemetry-derived graph. Public output
contains nodes and edges, never interactions. An interaction is private keyed
state used to correlate dimensions, remember which graph elements an
observation contributed, and retract those contributions after inactivity.

## Contributions

Every accepted service-graph datapoint is converted through the generated
semantic registry into node and edge contributions. A contribution is owned by
its internal interaction ID. Updating an interaction replaces its contributor
snapshot; expiry retracts every snapshot owned by that interaction.

Several interactions can contribute to the same graph element. Nodes with the
same semantic ID are one node, and edges with the same source ID, relationship
type, and target ID are one edge.

## Attribute merging

Optional attributes from different contributors complete one another. For
example, one observation can supply a pod's zone while another supplies its
version. The authoritative node contains both.

If contributors provide different values for the same optional attribute,
Flink selects the newest observation. Equal timestamps are resolved by the
lexicographically smallest contributor ID. When a contributor expires, Flink
recomputes from the remaining snapshots, so a value can fall back or disappear.

## Metrics

Collector service-graph counters enter Flink as deltas. A semantic dependency
edge accumulates `service_graph.request.total` and
`service_graph.request.failed.total` for its active lifetime. Removing one of
several contributors does not subtract historical activity. Removing the final
contributor deletes the edge; later recreation starts totals from zero.

## Expiry and output

Each internal interaction has event-time and processing-time expiry timers.
Event time follows telemetry timestamps; processing time guarantees cleanup
when input becomes idle. The configured state TTL must exceed interaction TTL
plus allowed lateness.

The element-keyed stage emits a complete `upsert` when merged state changes and
a `delete` only when the final contributor disappears. Consumers apply these
commands idempotently and never calculate their own stale timeout.
