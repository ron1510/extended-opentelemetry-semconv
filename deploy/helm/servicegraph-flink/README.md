# Servicegraph Flink Chart

This chart submits the Python interaction-diff application to a native Flink
2.2.1 Application Mode cluster. It uses the same immutable image for the
launcher, JobManagers, and TaskManagers.

The default configuration uses two JobManagers with Kubernetes high
availability and one RWX claim for HA metadata, checkpoints, and savepoints.
Set `storage.storageClassName` or provide `storage.existingClaim`.

```powershell
helm upgrade --install servicegraph-flink deploy/helm/servicegraph-flink `
  --namespace servicegraph-system --create-namespace `
  --values internal-flink-values.yaml
```

Set `imagePullSecrets` for an internal registry. Kafka authentication reads an
existing Secret selected by `streamContract.kafka.security.existingSecret`.

The launcher is a post-install hook. Native Flink creates the JobManager
Deployment and TaskManager pods after submission, so those resources are not
part of Helm's rendered output. Upgrades use a savepoint and application
replacement rather than an in-place Deployment rollout.
