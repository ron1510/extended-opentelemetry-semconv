# Air-Gapped Build And Release

## Supported Runtime

The project intentionally supports one narrow runtime matrix:

| Component | Version |
|---|---|
| Python | 3.12.13 |
| Java | 11 |
| Apache Flink and PyFlink | 2.2.1 |
| Flink SQL Kafka connector | 5.0.0-2.2 |
| OpenTelemetry Collector Contrib | 0.156.0 |
| OpenTelemetry semantic model snapshot | 1.43.0 |

Python 3.14 is not a supported project interpreter because PyFlink 2.2.1
supports Python through 3.12. Flink and PyFlink must be upgraded together.

## Artifact Model

The monorepo produces independent artifacts with different release cadence.

### Semantic Library Wheel

`extended-opentelemetry-semconv` contains:

- registry Pydantic models and validation;
- generated semantic entity interfaces;
- semconv lock metadata;
- relationship and dimension semantics;
- OTLP service-graph parsing; and
- pure interaction state and event contracts.

It depends on Pydantic, OTLP protobuf support, and YAML parsing. It does not
depend on PyFlink, Kafka, or environment settings.

### Flink Application Wheel

`otel-servicegraph-diff` contains:

- the executable CLI;
- validated Pydantic settings;
- Kafka source and sink construction;
- watermarks, keyed state, and timer wiring; and
- adapters for normal and rejected Kafka records.

It depends on the semantic library and PyFlink 2.2.1.

### Thin Flink Runtime Image

The runtime image is derived from the mirrored official Flink 2.2.1 Java 11
image. It adds only:

- Python 3.12.13;
- PyFlink and package runtime dependencies;
- `flink-sql-connector-kafka-5.0.0-2.2.jar`; and
- `interaction-serializer.jar` compiled for Java class version 55.

The runtime image excludes application wheels, source, tests, fixtures,
registry snapshots, Ruff, Pyright, pytest, Hypothesis, Node.js, and vendored
binary dependencies. Application wheels must be delivered separately.

### Rebuild Policy

Publish a new wheel for ordinary semantic or application changes. Rebuild the
runtime image only when one of these changes:

- Python or PyFlink version;
- runtime Python dependencies;
- Flink or Java version;
- Kafka connector version; or
- private serializer source.

The stable serializer filename is versionless inside the image. Its effective
version is the immutable runtime image tag and digest.

## Artifactory Inputs

An air-gapped build requires these internal services:

| Repository | Required content |
|---|---|
| Docker | Mirrored Python, Flink Java 11, Maven Java 11, and Collector images |
| PyPI | All dependencies declared by both package `pyproject.toml` files |
| Maven | Flink Kafka connector and serializer build dependencies |
| Python package repository | Published semantic and application wheels |

The standalone Collector chart has no chart dependencies and needs only the
mirrored Collector image plus an optional mirrored Helm-test image. It never
contacts Maven or PyPI.

Maven and pip are used only in disposable build stages. Deployed containers do
not contact PyPI or Maven. No JAR, Debian package, or other third-party binary
is committed to Git.

Use `.mvn/settings.xml.example` as the credential-free Maven mirror template.
Supply the real settings file as a BuildKit secret. Do not place repository
credentials in the Dockerfile, image layers, build arguments, or Git.

## Build Commands

Build both wheels with a PEP 517 frontend:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_wheels.ps1
```

Equivalent package-specific commands are:

```powershell
python -m pip wheel --no-deps --wheel-dir dist packages\extended-opentelemetry-semconv
python -m pip wheel --no-deps --wheel-dir dist apps\otel-servicegraph-diff
```

Build the runtime against internal mirrors:

```powershell
docker build `
  --file apps/otel-servicegraph-diff/Dockerfile `
  --build-arg PYTHON_BASE_IMAGE='<registry>/python:3.12.13-slim-bookworm' `
  --build-arg FLINK_BASE_IMAGE='<registry>/flink:2.2.1-scala_2.12-java11' `
  --build-arg MAVEN_BASE_IMAGE='<registry>/maven:3.9.11-eclipse-temurin-11' `
  --build-arg PIP_INDEX_URL='https://<artifactory>/api/pypi/pypi/simple' `
  --build-arg PIP_TRUSTED_HOST='<artifactory-host>' `
  --secret id=maven_settings,src='<secure-path>/settings.xml' `
  --tag '<registry>/team/servicegraph-flink:<version>' .
```

Promote the runtime and Collector images by digest. Tags alone are not an
immutable release reference.

## Non-Root Runtime

The final image has no root setup step and defaults to the upstream `flink`
user. Required writable paths are group-owned and group-writable for OpenShift
restricted SCC behavior, where the platform replaces the image user with an
arbitrary namespace-allocated UID in group 0.

The verified runtime probe checks:

- Java 11;
- Python 3.12.13 and PyFlink 2.2.1;
- Kafka connector presence;
- serializer presence and Java class level 55; and
- application-path writability for both the default and an arbitrary UID.

Runtime pods require access only to Kafka, mounted configuration, certificates,
application wheels, and state storage.

## Semantic Convention Update

Normal workflows must work without internet access. To update the pinned OTel
model:

1. Obtain an approved local OTel source artifact containing `model/**/*.yaml`.
2. Add a new versioned snapshot under `upstream/otel-semconv` without modifying
   the old snapshot.
3. Update the lock metadata with artifact identity and file hashes.
4. Update generator snapshot references.
5. Validate extensions against the new upstream model.
6. Regenerate entities and Collector configuration.
7. Review entity fields, relationships, dimensions, and generated diffs.
8. Run all release gates and publish compatible package versions.

Generated Python constants alone can confirm names but cannot provide complete
attribute type, stability, brief, entity, or relationship semantics. Full
automated artifact comparison and affected-model reporting remain planned work.

## Release Gates

Run from the repository root with the supported Python 3.12 environment or the
development image:

```powershell
python scripts\validate_registry.py
python scripts\generate_entities.py --check
python scripts\generate_collector_config.py --check
python -m ruff check .
python -m pyright
python -m pytest
docker compose config --quiet
helm lint deploy/helm/servicegraph-collector --strict
helm template servicegraph deploy/helm/servicegraph-collector `
  --namespace team `
  --values deploy/helm/servicegraph-collector/values-openshift.example.yaml
```

Validate the generated Collector configuration in the pinned image:

```powershell
docker run --rm `
  -v "${PWD}/deploy/local/otelcol.yaml:/etc/otelcol/config.yaml:ro" `
  otel/opentelemetry-collector-contrib:0.156.0 `
  validate --config=/etc/otelcol/config.yaml
docker run --rm `
  -v "${PWD}/deploy/local/otelcol-backend.yaml:/etc/otelcol/config.yaml:ro" `
  otel/opentelemetry-collector-contrib:0.156.0 `
  validate --config=/etc/otelcol/config.yaml
```

Inspect package boundaries and hashes:

```powershell
python scripts\verify_artifacts.py `
  --dist dist `
  --report reports\confidence\artifacts.json
```

Run the source-free lifecycle:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke_compose.ps1
```

The lifecycle installs built wheels into an application volume and mounts that
volume read-only into Flink processes. It verifies real Collector, Kafka, and
Flink behavior without editable installs or repository source mounts.

## Release Sequence

1. Pin the semantic snapshot and regenerate committed artifacts.
2. Pass registry, generation, lint, type, test, Collector, and Compose gates.
3. Build and inspect both wheels.
4. Build the runtime image only when its inputs changed.
5. Publish wheels and immutable image digests to Artifactory.
6. Record compatible semantic-wheel, application-wheel, runtime-image, and
   Collector versions in the internal release definition.
7. Take a savepoint before a state-affecting upgrade.
8. Deploy to a non-production namespace and run the internal lifecycle test.
9. Promote only after reviewed deployment diff and operational evidence.

Production wheel delivery and submission are not finalized in the checked-in
OpenShift starting point. That is a migration requirement, not a reason to put
application source into the thin runtime image.

## Related Documentation

- [Architecture](architecture.md)
- [Deployment and operations](deployment-and-operations.md)
- [Limitations and roadmap](limitations-and-roadmap.md)
