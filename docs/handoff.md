# Engineering Handoff

## Handoff Status

Development is complete for the repository-owned v1 semantic model and
interaction diff engine. The Collector scaling topology is implemented as a
standalone Helm chart and verified locally. Internal OpenShift integration,
the existing HA Flink release, and downstream materialization remain owned by
the internal deployment phase.

This document records what was implemented, what was actually verified, what
was not verified, and the recommended continuation order.

## Implemented System

### Semantic Model

The `extended-opentelemetry-semconv` package provides:

- a pinned OpenTelemetry semantic-convention model snapshot;
- local extensions using the upstream OTel YAML model shape;
- strict registry parsing and reference validation with Pydantic;
- generated immutable semantic interfaces such as `Service`, `K8sPod`,
  `K8sNode`, and `AppEndpoint`;
- entity resolution from telemetry attributes;
- relationships and service-graph participation metadata;
- service-graph dimensions derived only from attributes used by modeled
  participating entities;
- exclusion of template dimensions such as labels, annotations, and selectors;
- OTLP service-graph observation parsing; and
- pure typed interaction identity, state, expiry, and event transitions.

The semantic package does not depend on PyFlink, Kafka clients, or environment
configuration.

### PyFlink Application

The independent `otel-servicegraph-diff` package provides:

- PyFlink 2.2.1 source, watermark, keyed-state, and timer wiring;
- Pydantic Settings validation for runtime configuration;
- parsing of request-total and failed-total service-graph metrics;
- keyed `InteractionState` storage by deterministic `interaction_id`;
- merging of supported metrics into one interaction;
- suppression of unchanged cumulative observations;
- counter progression and reset handling;
- event-time and processing-time expiry;
- deterministic upsert/delete events;
- malformed-input DLQ records; and
- keyed Kafka output through the private Java 11 serializers.

The delivery boundary is at-least-once. Downstream systems must accept repeated
identical event IDs and reject conflicting content for one event ID.

### Runtime Packaging

The repository produces two independent wheels:

- `extended-opentelemetry-semconv`
- `otel-servicegraph-diff`

The thin Flink runtime image contains Java 11, Python 3.12.13, PyFlink 2.2.1,
the Flink Kafka connector, runtime Python dependencies, and the private
interaction serializer. It intentionally excludes application wheels and
source code. Ordinary application releases publish wheels without rebuilding
the runtime image.

### Collector Architecture

The standalone chart under `deploy/helm/servicegraph-collector` implements:

```text
Applications
  -> ClusterIP OTLP router Service
  -> two stateless routing Collector replicas
  -> trace-ID consistent hashing
  -> two stable StatefulSet ordinal DNS identities
  -> two stateful service-graph Collector backends
  -> Kafka otel.servicegraph.metrics
```

The backend hash ring contains exactly two stable names. The chart values
schema prevents accidental backend scaling in v1. A backend restart changes
its pod UID and IP but not its routing identity. The chart uses a static
resolver, so it requires no EndpointSlice RBAC.

The chart also provides:

- a headless governing Service with `publishNotReadyAddresses`;
- one persistent sending-queue claim per backend;
- router and backend metrics Services;
- disruption budgets;
- optional namespace-scoped NetworkPolicies;
- optional router-to-backend TLS;
- Kafka `SASL_SSL` and `SCRAM-SHA-256` configuration;
- non-root, read-only-root-filesystem security settings; and
- arbitrary OpenShift UID compatibility without CRDs or cluster-scoped RBAC.

The old raw OpenShift Collector manifest remains a single-replica reference and
should not be used as the new production Collector deployment.

### Shared Release Contract

`deploy/contracts/servicegraph-stream.values.yaml` is the credential-free
contract between the independently released Collector and Flink deployments.
It records brokers, Kafka security mode, Secret key names, and all three topic
names. Credentials remain in externally managed Secrets.

## Local Deployment Modes

### Docker Compose

Compose runs the complete product-owned runtime:

```text
OTLP traces -> Collector router -> two service-graph backends
  -> Redpanda -> PyFlink diff job -> Redpanda events and DLQ
```

The stable local backend identities are `otelcol-backend-0` and
`otelcol-backend-1`. The public developer endpoint remains `otelcol:4317/4318`.

### Kind

Kind deploys the actual Collector Helm chart with a disposable Redpanda
fixture. Kubernetes 1.29.12 is pinned for compatibility with the local
Docker Desktop/WSL cgroup environment. The kind workflow does not deploy
Flink; its purpose is to validate the Collector chart, Kubernetes resources,
StatefulSet DNS, probes, and trace-to-Kafka path.

## Verification Evidence

### Static And Unit Gates

The final verification completed with:

- registry validation passed;
- generated entity and Collector artifacts current;
- Ruff passed;
- strict Pyright passed with zero errors;
- 85 tests passed and 3 environment-dependent tests skipped;
- strict Helm lint passed;
- all 14 rendered Kubernetes resources passed Kubeconform; and
- Docker Compose configuration validation passed.

### Real Kind Collector Verification

The kind run verified:

- two router pods running;
- two service-graph StatefulSet backend pods running;
- the Helm connectivity test succeeding;
- paired OTLP spans entering through the router;
- a request-total service-graph metric arriving in Kafka;
- backend ordinal `-0` being deleted and recreated with a new pod UID and IP;
- the router retaining the same stable ordinal DNS identity; and
- another paired trace reaching Kafka after backend recovery.

The kind run discovered and fixed a persistent-queue issue: file-storage
compaction originally defaulted outside the mounted queue volume and failed on
a read-only root filesystem. Compaction now uses the mounted per-backend queue
directory. A regression test protects this behavior.

### Real Compose Flink Verification

The source-free Compose lifecycle installed built wheels into the application
volume and exercised:

```text
paired traces -> router -> two backends -> Kafka -> PyFlink -> Kafka
```

The run produced:

- 14 interaction events;
- 3 expected DLQ events;
- zero duplicate event IDs; and
- successful pairing, metric merging, identity, duplicate suppression,
  malformed input, ignored metric, expiry/delete, and recreation checks.

This verifies Flink end to end locally. It does not verify the internal HA
Flink chart, OpenShift runtime, external Kafka service, NiFi, or MongoDB.

## Internal Work Remaining

### Artifact And Release Configuration

- Mirror the pinned Collector, Flink, Python, Maven, kind, test, and supporting
  images into internal Artifactory.
- Publish both wheels to internal PyPI.
- Resolve Maven dependencies through the internal Maven mirror.
- Pin promoted image digests and wheel versions in internal release metadata.
- Implement wheel delivery and job submission in the existing HA Flink chart.
- Do not add source code or wheels to the thin runtime image merely to simplify
  submission.

### Collector Release

- Create organization-owned values layered over the standalone chart.
- Replace all example image repositories, zero digests, brokers, CIDRs, DNS
  selectors, and storage classes.
- Create the Kafka authentication Secret outside Git.
- Create the internal router-to-backend TLS Secret if internal TLS is enabled.
- Ensure the TLS certificate SANs contain both stable backend ordinal DNS names.
- Select the production RWO storage class for per-backend queue claims.
- Validate NetworkPolicy behavior against the internal CNI, DNS deployment,
  Kafka addresses, and monitoring namespace.
- Keep the backend count at two until a deliberate ring-migration design exists.

### Kafka

- Create the three topics with approved partition count, replication,
  retention, and quotas.
- Grant Collector write access to `otel.servicegraph.metrics`.
- Grant Flink read and consumer-group access to the input topic.
- Grant Flink write access to `graph.interactions.events` and
  `graph.interactions.dlq`.
- Confirm TLS trust, SCRAM credentials, hostname verification, and broker
  message-size limits.

Kafka Connect is not required.

### Flink And Durable State

- Map the shared stream contract into `InteractionDiffConfig` variables.
- Deliver the two wheels into a read-only application path.
- Configure the existing HA chart with durable checkpoint, savepoint, and HA
  metadata storage.
- Confirm Kafka partitions, Flink parallelism, and TaskManager slots align.
- Validate savepoint creation and restoration before a production promotion.
- Run TaskManager loss, JobManager failover, broker interruption, and rolling
  upgrade tests in the internal environment.

### Monitoring And Operations

- Scrape router, backend, Flink, and Kafka metrics.
- Alert on Collector refusal, queue pressure, retry, and export failures.
- Alert on Kafka lag, Flink backpressure, and failed or slow checkpoints.
- Monitor DLQ rate and rejection reasons.
- Monitor interaction state size and upsert/delete ratios.
- Establish service-graph store limits and memory headroom from internal load.
- Document Collector and Flink rollback procedures.

### NiFi And MongoDB

NiFi and MongoDB remain outside this repository. The downstream team must:

- consume `graph.interactions.events` while preserving per-key ordering;
- validate schema version, event ID, operation, and interaction ID;
- upsert MongoDB documents by a unique `interaction_id` index;
- delete documents by `interaction_id`;
- accept identical deterministic event redelivery;
- reject conflicting content for one event ID;
- provide retry, downstream DLQ, provenance, and monitoring; and
- define MongoDB authorization, indexes, retention, backup, and recovery.

### Semantic Roadmap

- Implement complete offline upstream semconv drift reporting.
- Define identifying versus descriptive attribute roles when required.
- Add latency histogram semantics if the product needs them.
- Add alert and broader metric attachment contracts separately.
- Treat service-graph entities as observed traffic evidence, not authoritative
  infrastructure inventory.

## Recommended Continuation Order

1. Publish immutable internal wheels and image digests.
2. Prepare the shared stream values and Kafka topics, ACLs, TLS, and Secrets.
3. Configure and deploy the standalone Collector chart in a non-production
   namespace.
4. Integrate wheel delivery and submission into the existing HA Flink chart.
5. Configure durable Flink state and deploy the job.
6. Repeat the paired trace, interaction event, DLQ, expiry/delete, and
   recreation lifecycle against the real external Kafka service.
7. Restart one Collector backend and verify recovery without changing the
   two-name ring.
8. Validate savepoint restore and HA behavior.
9. Establish internal capacity and alert thresholds.
10. Implement and independently certify the NiFi-to-MongoDB flow.

## Supported Claim

The repository supports the following claim:

> The semantic model, two-package Python implementation, Java 11/PyFlink 2.2.1
> diff engine, standalone trace-ID-routed Collector chart, and local
> Collector/Kafka/Flink lifecycle are implemented and verified. Internal
> artifact integration, HA/OpenShift certification, external Kafka validation,
> and NiFi/MongoDB materialization remain deployment work.

Do not claim production certification, internal-cluster capacity, cross-system
exactly-once delivery, or NiFi/MongoDB correctness until the corresponding
internal acceptance work is complete.

## Related Documentation

- [Architecture](architecture.md)
- [Air-gapped build and release](build-and-release.md)
- [Deployment and operations](deployment-and-operations.md)
- [Limitations and roadmap](limitations-and-roadmap.md)
- [Collector Helm chart](../deploy/helm/servicegraph-collector/README.md)
