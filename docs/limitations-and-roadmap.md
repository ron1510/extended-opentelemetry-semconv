# Limitations And Roadmap

## How To Read This Document

The v1 semantic library and interaction diff engine are feature-complete and
verified locally. That does not mean the repository is already integrated,
scaled, and certified in an internal production environment.

Items use four statuses:

| Status | Meaning |
|---|---|
| Implemented and verified locally | Behavior passed repository and source-free local lifecycle checks |
| Implemented; internal configuration required | Code exists, but internal values or platform integration are required |
| Planned; not implemented | Design intent exists, but no production implementation is checked in |
| Intentionally out of scope | Another system or team owns the capability |

## Production Readiness Ledger

### Production Wheel Delivery And Submission

| Field | Value |
|---|---|
| Status | Planned; not implemented |
| Owner | Platform team with application-team package contract |
| Impact | The thin runtime image cannot execute the application until both wheels are delivered |
| Acceptance | A pinned semantic wheel and application wheel are installed into a read-only application path, the Flink job submits from that path, and no repository source or editable install is mounted |

The Compose acceptance profile proves the wheel-installed model with a shared
application volume. The checked-in OpenShift submission Job still relies on the
development source layout and must not be paired unchanged with the thin
runtime target.

The internal Helm chart should select one explicit mechanism, such as an init
container authenticated to internal PyPI or an immutable application artifact
volume. Credentials, retry behavior, checksum verification, and upgrade
ordering belong to that deployment design.

### Internal Artifact Configuration

| Field | Value |
|---|---|
| Status | Implemented; internal configuration required |
| Owner | Internal CI and platform teams |
| Impact | Mock references cannot resolve in the air-gapped environment |
| Acceptance | All base images, wheels, Python dependencies, Maven dependencies, and release images resolve only through approved Artifactory repositories and are pinned by version or digest |

Replace mock image references, zero digests, PyPI and Maven endpoints, namespace,
storage class, Kafka addresses, CIDRs, and pull credentials. Secrets must remain
outside Git and build layers.

### Durable Flink State And HA Integration

| Field | Value |
|---|---|
| Status | Implemented; internal configuration required |
| Owner | Flink/platform team |
| Impact | Checkpoint or HA-storage failure can prevent recovery and safe upgrades |
| Acceptance | Checkpoints and savepoints complete on approved durable storage, a savepoint restore succeeds in non-production, and the internal HA chart passes its existing recovery criteria |

The repository includes checkpointing, externalized checkpoint retention,
stable operator UIDs, and a namespace-scoped HA starting point. It does not
certify the example RWX storage class or replace the organization's existing HA
Flink configuration.

### Internal End-To-End Validation

| Field | Value |
|---|---|
| Status | Implemented; internal configuration required |
| Owner | Application and platform teams |
| Impact | Network, authentication, broker, storage, or chart differences may remain undiscovered |
| Acceptance | The real internal deployment produces an upsert, suppresses an unchanged cumulative sample, sends malformed input to the DLQ, emits one stale delete, recreates a late interaction, and maintains healthy checkpoints |

Local validation proves the application path, not internal infrastructure
compatibility or production capacity.

## Collector Scaling

### Legacy Single-Replica Baseline

| Field | Value |
|---|---|
| Status | Implemented and verified locally; not the production target |
| Owner | Observability team |
| Impact | Pairing capacity and availability are limited to one service-graph instance |
| Acceptance | One Collector remains healthy, exports without refused or failed telemetry, and stays within its pairing store and memory limits |

The raw OpenShift `ClusterIP` service and one-replica `Recreate` deployment
preserve pairing correctness, but are retained only as a reference. The
standalone chart supersedes this deployment for new environments.

### Trace-ID-Sticky Scaled Tier

| Field | Value |
|---|---|
| Status | Implemented; internal configuration required |
| Owner | Internal observability/platform team |
| Impact | Round-robin scaling can split spans from one trace and produce incomplete or incorrect service-graph metrics |
| Acceptance | The internal chart release consistently routes by trace ID to exactly two stable service-graph Collector ordinals, including during normal rollout and one-backend recovery tests |

The standalone chart deploys two stateless routers, a headless governing
Service, and a two-replica service-graph StatefulSet. Routers hash by trace ID
onto stable ordinal DNS names. The chart is namespace-scoped and avoids the
Kubernetes resolver because a fixed two-name ring needs no EndpointSlice RBAC.
Internal certificates, images, Kafka values, storage, NetworkPolicy values, and
recovery validation remain environment-owned.

## NiFi And MongoDB Materialization

| Field | Value |
|---|---|
| Status | Intentionally out of scope for this repository; required for the complete product flow |
| Owner | NiFi and MongoDB owners |
| Impact | Interaction events exist in Kafka but no durable queryable current graph is materialized |
| Acceptance | Upserts and deletes are applied idempotently by `interaction_id`, duplicate event IDs are harmless, conflicting event IDs are rejected, and the Kafka-to-Mongo lifecycle passes failure and replay tests |

### Required NiFi Flow

The downstream flow must:

1. Consume `graph.interactions.events` without changing per-key ordering.
2. Parse and validate `schema_version`, `event_id`, `event_type`, `operation`,
   `interaction_id`, and the operation-specific payload.
3. Route `upsert` and `delete` operations separately.
4. Upsert the complete interaction document by `interaction_id`.
5. Delete the document by `interaction_id` for delete events.
6. Treat an identical repeated `event_id` as expected at-least-once redelivery.
7. Reject and alert on different content associated with an existing
   `event_id`.
8. Retry transient Kafka or MongoDB failures with bounded backoff.
9. Route permanent contract failures to a downstream dead-letter path.
10. Expose provenance, lag, retry, rejection, and operation-rate telemetry.

NiFi must not interpret event arrival as exactly-once delivery and must not use
metric name as the MongoDB document identity.

### Required MongoDB Design

The MongoDB owner must define:

- a unique index on `interaction_id`;
- optional unique or retained event-ID bookkeeping for conflict detection;
- indexes required by graph and insight queries;
- authorization and secret rotation;
- retention for current and optional historical data;
- backup, restore, and disaster recovery;
- document/schema compatibility policy; and
- expected behavior when a delete arrives before a repeated upsert.

NiFi templates, MongoDB manifests, database sizing, and query APIs are not part
of this repository.

## Semantic Model Limitations

### Observed Graph, Not Complete Inventory

| Field | Value |
|---|---|
| Status | Intentional v1 behavior |
| Owner | Application/product team |
| Impact | An absent interaction or entity does not prove that the real resource does not exist |
| Acceptance | Product consumers describe the data as a live observed interaction view and use a separate inventory source when authoritative existence is required |

Entities are created only when sufficient semantic fields occur in observed
telemetry. Service graph is therefore evidence of traffic, not a Kubernetes or
cloud control-plane inventory.

### Identifying And Descriptive Attribute Roles

| Field | Value |
|---|---|
| Status | Planned; not implemented |
| Owner | Semantic-model maintainers |
| Impact | The model does not formally expose why each field participates in identity versus description |
| Acceptance | OTel-compatible metadata expresses the roles, generated APIs preserve them, and compatibility/migration rules are documented |

The v1 POC intentionally treats entity fields without this distinction.

### Alert And Metric Contracts

| Field | Value |
|---|---|
| Status | Planned; not implemented |
| Owner | Product and alerting teams |
| Impact | The semantic registry does not yet define how alerts or arbitrary metrics attach to entity interfaces |
| Acceptance | Versioned contracts define attachment, lifecycle, cardinality, and compatibility behavior with tests |

Interaction metric values are available in current state, but this is not an
alert-evaluation engine.

### Template Dimensions

| Field | Value |
|---|---|
| Status | Intentionally excluded by default |
| Owner | Semantic-model maintainers |
| Impact | Labels, annotations, and selectors are unavailable as automatic interaction dimensions |
| Acceptance | Any future opt-in is explicit, bounded, reviewed for cardinality, and covered by generated-config tests |

The suffixes `.label`, `.annotation`, and `.selector` are excluded to prevent
unbounded service-graph metric series.

### Upstream Semconv Drift Automation

| Field | Value |
|---|---|
| Status | Planned; partially implemented manually |
| Owner | Semantic-model maintainers |
| Impact | Upstream changes require careful manual snapshot replacement and review |
| Acceptance | An offline tool compares two local source artifacts and reports added, removed, and changed attributes/entities plus affected extensions and generated classes |

The current implementation pins a local model snapshot, records lock metadata,
validates extensions, and checks generated output. It does not yet implement a
complete semantic drift report. Generated models remain tied to the pinned
semconv version until an explicit upgrade.

## Runtime And Scale Limitations

### Supported Metrics

| Field | Value |
|---|---|
| Status | Implemented and verified locally for v1 counters |
| Owner | Application team |
| Impact | Service-graph latency histogram data is not stored in interaction state |
| Acceptance | Future histogram support defines aggregation/merge semantics, identity behavior, event compatibility, and bounded state cost |

V1 supports only:

- `traces_service_graph_request_total`
- `traces_service_graph_request_failed_total`

Known unsupported service-graph metrics are ignored. Invalid input is sent to
the DLQ.

### Delivery Semantics

| Field | Value |
|---|---|
| Status | Implemented and verified locally as at-least-once |
| Owner | Application and downstream teams |
| Impact | Identical events can be delivered more than once |
| Acceptance | Every downstream consumer is idempotent and conflict detection is monitored |

Exactly-once behavior across Kafka, Flink, NiFi, and MongoDB is not claimed.
Deterministic event IDs make redelivery observable and safe when consumers obey
the contract.

### Capacity And Performance

| Field | Value |
|---|---|
| Status | Local characterization only; internal capacity unknown |
| Owner | Platform, observability, Kafka, and application teams |
| Impact | Local throughput numbers cannot size the internal production cluster |
| Acceptance | Internal tests establish sustainable throughput, interaction cardinality, checkpoint health, lag drain, and operating headroom using real platform limits |

Kafka partitions, Collector pairing capacity, Flink slots, Python operator
throughput, state cardinality, checkpoint storage, and downstream MongoDB
writes are independent constraints. Production should operate with measured
headroom rather than extrapolating linearly from Docker.

### Failure And Upgrade Certification

| Field | Value |
|---|---|
| Status | Planned internal validation |
| Owner | Flink/platform and application teams |
| Impact | Recovery behavior under infrastructure disruption is not certified |
| Acceptance | Savepoint restore, TaskManager loss, JobManager failover, broker interruption, rolling upgrade, and rollback tests meet internal recovery objectives |

The repository has restart configuration, checkpointing, stable UIDs, and
deterministic delivery, but HA failover and outage scenarios were intentionally
excluded from local acceptance.

## Intentionally Out Of Scope

These are not backlog omissions for the v1 repository:

- Kafka Connect or broker administration;
- Postgres or a relational persistence layer;
- Kubernetes CRDs, a Flink operator, or cluster-scoped controllers;
- ClusterRole or cluster-admin-owned resources;
- NiFi templates and MongoDB deployment manifests;
- authoritative general infrastructure inventory ingestion;
- alert evaluation and incident correlation; and
- performance certification for the internal cluster.

## Recommended Implementation Order

1. Create a final source commit and versioned v1 release artifacts.
2. Implement internal wheel delivery and submission in the Flink Helm release.
3. Configure Artifactory, Kafka security, durable state, and real namespace
   values.
4. Deploy the standalone Collector chart with internal values and validate one
   backend restart without changing the two-name hash ring.
5. Run the internal source-free lifecycle through the final Collector topology.
6. Build and certify the NiFi/MongoDB materialization flow.
7. Validate savepoint restore, failover, broker interruption, and rollback.
8. Measure internal capacity and set alerts and operating limits.
9. Automate offline semconv drift reporting before the next upstream upgrade.

## Related Documentation

- [Architecture](architecture.md)
- [Air-gapped build and release](build-and-release.md)
- [Deployment and operations](deployment-and-operations.md)
