# Testing

The repository has fast unit and component tests plus one opt-in Kubernetes
lifecycle test. Tests require CPython 3.12; other interpreter versions are not
supported by the project packages.

## Fast suite

Install the repository packages and development dependencies as described in
[Repository Development](../development.md), then run:

```console
python -m pytest -m "not e2e"
```

This covers registry validation, generation from YAML through importable Python
models, semantic graph behavior, Flink state and timer behavior, the demo, and
the Elasticsearch initializer, projector, and query API. PyFlink tests are
skipped when `apache-flink` is not installed in the active Python 3.12
environment.

Check all generated artifacts together:

```console
python -m extended_otel_semconv.codegen --check
```

Generate an optional branch-coverage report without enforcing an arbitrary
percentage:

```console
python -m pytest -m "not e2e" \
  --cov=extended_otel_semconv.codegen \
  --cov=extended_otel_semconv.registry \
  --cov=otel_servicegraph_diff \
  --cov-branch \
  --cov-report=term-missing
```

## Projector lifecycle test

The E2E test requires a running Docker engine plus `kind`, `kubectl`, and Helm.
It creates a uniquely named Kind cluster, builds the production access image,
and installs the access chart. Redpanda and Elasticsearch run as isolated
Docker containers connected to the Kind network. The test publishes exact
Flink graph-element lifecycle envelopes and verifies upsert, complete
replacement, replay, committed Kafka offsets, and deletion in Elasticsearch.

Flink and the Collectors are intentionally excluded from this test. Their
behavior is covered independently, while this deployment test starts at the
projector's public Kafka contract and avoids importing the large Flink runtime
image into Kind.

```console
python -m pytest -m e2e --run-e2e
```

The cluster, Docker containers, kubeconfig, and temporary image tag are removed
after the test. Keep the complete environment after success or failure when
debugging:

```console
python -m pytest -m e2e --run-e2e --keep-e2e-cluster
```

The test honors `PIP_INDEX_URL` and `PIP_TRUSTED_HOST` during the access image
build.

## Elasticsearch integration test

The access foundation has a separate opt-in test that starts Elasticsearch
8.15.5 directly in Docker. It does not use Testcontainers and is independent
of the Kind lifecycle test:

```console
python -m pytest -m elasticsearch --run-elasticsearch
```

The disposable container uses a 512 MiB heap and is removed automatically.
On failure, its bounded logs are included in pytest output.
