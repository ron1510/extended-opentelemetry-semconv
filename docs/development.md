# Development And Release

Use Python 3.12 and install the two packages in editable mode:

```powershell
python -m pip install -e packages/extended-opentelemetry-semconv `
  -e apps/otel-servicegraph-diff
python -m pip install pytest ruff pyright hypothesis
```

Run the behavior and generated-artifact checks:

```powershell
python scripts\generate_entities.py --check
python scripts\generate_collector_dimensions.py --check
python -m ruff check .
python -m pyright
python -m pytest
helm lint deploy/helm/servicegraph-collector
helm lint deploy/helm/servicegraph-flink
```

The generators validate extensions against the pinned upstream model before
producing committed Python entities or Collector dimensions.

## Runtime Image

The release artifact is one immutable Flink image. Python packages are
installed directly from the repository; there is no wheel staging or
side-loading step.

```powershell
docker build `
  --file apps/otel-servicegraph-diff/Dockerfile `
  --target runtime `
  --build-arg PIP_INDEX_URL=https://pypi.internal.example/simple `
  --secret id=maven_settings,src=$HOME/.m2/settings.xml `
  --tag registry.internal.example/extended-otel-flink-runtime:2.2.1-java11 `
  .
```

The build compiles the Java serializers, resolves the Flink Kafka connector,
installs both Python packages and their dependencies, and copies them into the
Flink 2.2.1 Java 11 image. The resulting container runs as the non-root Flink
user.

Publish by digest or immutable tag. Mirror the Python, Maven, Flink, and
Collector dependencies required by the internal environment instead of
downloading artifacts during deployment.
