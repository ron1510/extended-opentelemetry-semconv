# Service-Graph Collector Chart

This standalone Helm chart deploys the Collector half of the runtime:

```text
OTLP -> router Service -> two trace-ID-hashing routers
     -> two stable StatefulSet backends -> Kafka service-graph metrics
```

It uses only namespace-scoped Kubernetes resources. It installs no CRDs or
cluster RBAC and does not require a Flink operator. Pods do not declare a fixed
UID and are compatible with OpenShift restricted SCC when the mirrored images
also support arbitrary UIDs.

## Routing Contract

The router `Deployment` has two replicas. Both use the same static hash ring
containing these stable backend identities:

```text
<release>-servicegraph-collector-backend-0.<headless-service>.<namespace>.svc:4317
<release>-servicegraph-collector-backend-1.<headless-service>.<namespace>.svc:4317
```

The `StatefulSet` is intentionally fixed at two replicas by the values schema.
A normal backend restart keeps the same hash-ring identity, and router retry
queues continue targeting that identity while it recovers. Scaling the backend
set changes the ring and must be treated as a planned telemetry-continuity
event. `publishNotReadyAddresses` preserves stable DNS during recovery; it does
not make an unready backend accept traffic.

## Install

For kind:

```powershell
helm upgrade --install servicegraph deploy/helm/servicegraph-collector `
  --namespace servicegraph-system --create-namespace `
  --values deploy/helm/servicegraph-collector/values-kind.yaml `
  --wait
```

For OpenShift, layer the credential-free stream contract and internal values:

```powershell
helm upgrade --install servicegraph deploy/helm/servicegraph-collector `
  --namespace team `
  --values deploy/contracts/servicegraph-stream.values.yaml `
  --values deploy/helm/servicegraph-collector/values-openshift.example.yaml `
  --values internal-values.yaml `
  --wait
```

The example file contains documentation-only broker addresses, storage classes,
CIDRs, and image digests. It is not deployable unchanged.

## Required Secrets

For `SASL_SSL`, `streamContract.kafka.security.existingSecret` must contain:

- `username`
- `password`
- `ca.crt`

When `internalTls.enabled=true`, `internalTls.existingSecret` must contain
`tls.crt`, `tls.key`, and `ca.crt`. The certificate SANs must cover both stable
backend ordinal DNS names. Secrets are externally managed and never rendered
by this chart.

## Air-Gapped Release

Mirror these images before installation:

- `otel/opentelemetry-collector-contrib:0.156.0`
- the optional Helm-test image configured under `test.image`
- for local kind only, the pinned `kindest/node:v1.29.12` image from
  `scripts/kind_up.ps1`

Set immutable internal repositories and digests in the release values. The
chart has no chart dependencies and requires no Maven or PyPI access at deploy
time. Maven and PyPI are relevant to the separately released Flink runtime and
wheels, not to this Collector chart.

## Flink Contract

The Collector writes OTLP JSON to
`streamContract.topics.servicegraphMetrics`. The independent Flink release must
map the same contract to `KAFKA_BOOTSTRAP_SERVERS`,
`KAFKA_SECURITY_PROTOCOL`, `KAFKA_SASL_MECHANISM`, and
`INTERACTION_DIFF_INPUT_TOPIC`. The output and DLQ topic names are carried in
the shared contract so both releases use one reviewed set of names.

## Validation

```powershell
helm lint deploy/helm/servicegraph-collector --strict
helm template servicegraph deploy/helm/servicegraph-collector `
  --namespace team `
  --values deploy/helm/servicegraph-collector/values-openshift.example.yaml
docker compose config --quiet
powershell -File scripts/kind_up.ps1
powershell -File scripts/kind_smoke.ps1
```

Enable `networkPolicy` only after replacing the example Kafka CIDRs and DNS
selectors with values that match the target cluster CNI and DNS deployment.
