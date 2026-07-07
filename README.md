# Extended OpenTelemetry Semantic Conventions

This repository is a POC for OpenTelemetry-compatible entity interfaces.

The core idea is to keep OpenTelemetry attribute names and model layout, then
compose those attributes into semantic entity interfaces such as Kubernetes
clusters, namespaces, nodes, pods, and containers.

## Layout

- `model/k8s/registry.yaml` defines OTel-style attribute groups.
- `model/k8s/entities.yaml` defines OTel-style entity groups.
- `upstream/otel-semconv/` contains pinned upstream-like model snapshots.
- `upstream/otel-semconv.lock.json` records the pinned snapshot hashes.
- `src/extended_otel_semconv/` contains the Python package.
- `tests/` contains example-based and property-based tests.

## Python API

The public API exposes semantic Pydantic models, not generic bags of
attributes:

- `K8sCluster`
- `K8sNamespace`
- `K8sNode`
- `K8sPod`
- `K8sContainer`

Use `entities_from_attributes(...)` to parse raw OTel attributes and create
every supported entity independently.

## Upstream Sync

The installed `opentelemetry-semantic-conventions` package is a dependency and
is used for compatibility checks. The package does not currently expose OTel
model YAML files, so closed-network sync must use local source artifacts,
checked-in snapshots, or internal packages that include `model/**/*.yaml`.

Drift between two local model snapshots can be checked with:

```powershell
C:\Users\ronba\AppData\Local\Python\bin\python.exe scripts\check_semconv_drift.py old\model new\model
```

Inspect the installed semconv package with:

```powershell
C:\Users\ronba\AppData\Local\Python\bin\python.exe scripts\inspect_semconv_package.py
```

## Validate

```powershell
C:\Users\ronba\AppData\Local\Python\bin\python.exe scripts\validate_registry.py
C:\Users\ronba\AppData\Local\Python\bin\python.exe -m pytest
```
