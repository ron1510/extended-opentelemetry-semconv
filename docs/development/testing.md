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
the UI projection. PyFlink tests are skipped when `apache-flink` is not
installed in the active Python 3.12 environment.

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

## Kubernetes lifecycle test

The E2E test requires a running Docker engine plus `kind`, `kubectl`, and Helm.
It creates a uniquely named Kind cluster, builds the current Flink and UI
images, installs Redpanda and the project charts, sends deterministic OTLP
traces, and verifies the complete upsert/delete lifecycle through Kafka and the
UI API.

```console
python -m pytest -m e2e --run-e2e
```

The cluster, kubeconfig, and temporary image tags are removed after the test.
Keep them after success or failure when debugging:

```console
python -m pytest -m e2e --run-e2e --keep-e2e-cluster
```

The test honors `PIP_INDEX_URL`, `PIP_TRUSTED_HOST`, and
`NPM_CONFIG_REGISTRY` during image builds. Set `MAVEN_SETTINGS` to the path of
an internal Maven settings file when required.

This first lifecycle test intentionally does not replace the JobManager or run
a Helm upgrade. Recovery and upgrade validation remain separate operational
tests.
