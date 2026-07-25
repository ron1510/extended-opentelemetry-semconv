# Development

## Environment

Use Python 3.12. Create a virtual environment and install all repository
packages:

```console
python -m venv .venv
python -m pip install -e packages/extended-opentelemetry-semconv
python -m pip install -e apps/otel-servicegraph-diff
python -m pip install -e apps/servicegraph-demo
python -m pip install -e apps/servicegraph-ui
python -m pip install hypothesis pytest pyright ruff
```

The PyFlink package is large. For package-only changes, install only the
semantic package and tools required by the relevant tests.

## Generated files

Registry source is hand-written; generated Python, relationship metadata, and
Collector dimensions are committed:

```console
python scripts/generate_entities.py
python scripts/generate_collector_dimensions.py
```

Never manually patch generated modules or dimensions. Change registry source
and regenerate.

## Validation

```console
python scripts/generate_entities.py --check
python scripts/generate_collector_dimensions.py --check
python -m ruff check .
python -m pyright
python -m pytest
helm lint deploy/helm/servicegraph-collector
helm lint deploy/helm/servicegraph-demo
helm lint deploy/helm/servicegraph-flink
helm lint deploy/helm/servicegraph-ui
```

Build the frontend:

```console
cd apps/servicegraph-ui/frontend
npm install
npm run build
```

Tests focus on registry validation, generated artifacts, pure interaction
transitions, Flink timers, demo topology, and idempotent UI projection.

## Documentation

```console
python -m pip install mkdocs-material==9.7.7
python -m mkdocs build --strict
python -m mkdocs serve
```

Open `http://127.0.0.1:8000`. The generated `site/` directory is ignored and
must not be committed.

## Runtime images

The Flink release artifact is one immutable image. Python packages are
installed directly from repository source; there is no wheel staging:

```console
docker build \
  --file apps/otel-servicegraph-diff/Dockerfile \
  --target runtime \
  --build-arg PIP_INDEX_URL=https://pypi.internal.example/simple \
  --secret id=maven_settings,src=$HOME/.m2/settings.xml \
  --tag registry.internal.example/extended-otel-flink-runtime:2.2.1-java11 \
  .
```

The build compiles Java serializers, resolves the Flink Kafka connector,
installs Python packages and dependencies, and copies them into the Flink
2.2.1 Java 11 image. The UI Docker build compiles frontend assets before
installing its Python service. The demo image installs its package directly.

## Release checklist

1. Run generated-file, Python, frontend, Helm, and documentation checks.
2. Build images from a clean commit.
3. Run the complete local lifecycle test.
4. Record image digests.
5. Review event-schema and registry compatibility.
6. Publish immutable images and chart source.
7. Test installation using only published artifacts.
8. Describe entity, relationship, dimension, state, and event changes in the
   release notes.

Mirror Python, Maven, Flink, Collector, and frontend dependencies into internal
repositories when deployment environments cannot access public registries.
