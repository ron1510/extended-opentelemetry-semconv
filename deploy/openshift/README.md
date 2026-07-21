# OpenShift Deployment

This bundle is a namespace-scoped production starting point for OpenShift. It
uses standard Kubernetes APIs only: no CRDs, operator, Route, ClusterRole, or
cluster-admin action is required.

## Required Inputs

Replace every mock value before applying:

- namespace `team`, if your project name differs;
- both `artifactory.example.internal` image references and zero digests;
- Kafka broker `kafka.example.internal:9093`;
- Kafka egress CIDR `192.0.2.0/24`;
- Kubernetes API CIDR `198.51.100.10/32`;
- storage class `basic`, if the production class differs.

Create these secrets outside Git:

```powershell
oc -n team create secret generic servicegraph-kafka-auth `
  --from-literal=username='<scram-username>' `
  --from-literal=password='<scram-password>' `
  --from-file=ca.crt='C:\secure\kafka-ca.crt'

oc -n team create secret docker-registry internal-registry-pull `
  --docker-server='<internal-registry>' `
  --docker-username='<username>' `
  --docker-password='<password>'
```

`kafka-secret.example.yaml` documents the required keys and is intentionally
excluded from the Kustomize bundle.

The external Kafka service must already contain:

- `otel.servicegraph.metrics`
- `graph.interactions.events`
- `graph.interactions.dlq`

The baseline expects three partitions for each topic. Topic auto-creation is
disabled. Replication, retention, quotas, and ACLs remain owned by the Kafka
platform.

## Air-Gapped Image Build

Mirror the Python and Flink base images into Artifactory. The build reads
Python packages from the supplied internal PyPI index and copies the checked-in
Flink connector JARs into the image; containers install nothing at startup.
`requirements.lock` pins the reviewed Linux/Python 3.12 dependency closure, so
the internal mirror must contain those exact versions.

```powershell
docker build `
  --build-arg PYTHON_BASE_IMAGE='<registry>/python:3.12.13-slim-bookworm' `
  --build-arg FLINK_BASE_IMAGE='<registry>/flink:2.2.1-scala_2.12-java17' `
  --build-arg PIP_INDEX_URL='https://<artifactory>/api/pypi/pypi/simple' `
  --build-arg PIP_TRUSTED_HOST='<artifactory-host>' `
  --tag '<registry>/team/servicegraph-flink:<version>' .
```

Promote the application and Collector 0.156.0 images by digest, then replace
the mock digests in `flink.yaml` and `collector.yaml`. Verify the vendored JAR
hashes against `vendor/flink/README.md` before building.

The two small Java serializers are part of the Flink application image. They
map the two fields of a PyFlink `Row` to the Kafka record key and value. They
are not Kafka Connect plugins and place no requirement on the Kafka service.

## Validate And Apply

Review the rendered resources before contacting the cluster:

```powershell
kubectl kustomize deploy/openshift > rendered-openshift.yaml
kubectl apply --dry-run=client -f rendered-openshift.yaml
oc -n team apply --dry-run=server -k deploy/openshift
oc -n team auth can-i create configmaps `
  --as=system:serviceaccount:team:servicegraph-flink
oc -n team auth can-i use scc/restricted-v2 `
  --as=system:serviceaccount:team:servicegraph-flink
oc -n team diff -k deploy/openshift
```

Apply only after the server-side dry run and diff are reviewed:

```powershell
oc -n team apply -k deploy/openshift
oc -n team get pods,pvc,jobs
oc -n team port-forward service/servicegraph-flink-jobmanager 8081:8081
```

The submission Job is idempotent: it exits successfully when an active
`servicegraph-interaction-diff` job already exists. Delete and recreate the
submission Job only when an intentionally stopped or failed job must be
submitted again.

## Operations

- Keep the Collector at one replica. The service graph connector is stateful;
  scaling requires trace-ID-sticky routing before the Collector tier.
- The Collector queue uses a separate RWO PVC because its file storage backend
  is not safe on shared network filesystems.
- The Flink HA metadata, checkpoints, and savepoints use the RWX PVC.
- Take a savepoint before changing Flink, operator UIDs, state model versions,
  or Kafka connector versions.
- Monitor checkpoint failures and duration, Kafka consumer lag, Collector
  refused/export-failed metrics, DLQ volume, and delete/upsert ratios.
- OTLP ingress permits pods in `team`. Applications in other projects require
  an explicit additional NetworkPolicy rule.
- Standard NetworkPolicy cannot select external services by DNS name. Replace
  the mock Kafka and API CIDRs with stable platform-approved destinations.
