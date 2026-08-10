# Local Kind Environment

The repository's opt-in E2E fixture is the shortest reproducible local
ArangoDB/Gremlin environment. It creates an isolated Kind cluster, pinned
Redpanda and ArangoDB containers, the indexer, and read-only Gremlin Server:

```powershell
python -m pytest -m e2e --run-e2e --keep-e2e-cluster
```

The output prints the temporary kubeconfig. Set it in the shell before using
`kubectl`:

```powershell
$env:KUBECONFIG = '<printed kubeconfig path>'
kubectl get pods -n servicegraph-e2e
```

Port-forward Gremlin:

```powershell
kubectl port-forward -n servicegraph-e2e `
  service/servicegraph-gremlin 8182:8182
```

Then connect with the GraphBinary example in [ArangoDB and
Gremlin](arangodb-gremlin.md). Useful traversals include:

```python
g.V().has_label("service").value_map(True).to_list()
g.V().has("service_name", "storefront").out("calls").value_map(True).to_list()
g.E().has_label("calls").value_map(True).to_list()
```

The focused fixture injects exact Flink schema-2 output so storage and traversal
changes can be tested quickly. To run the complete telemetry path, install the
Collector, Flink, and demo charts into the same cluster using the commands in
[Kubernetes Deployment](../deployment-and-operations.md). Configure all charts
with the fixture's `servicegraph-redpanda:9092` broker and existing
`graph.elements.events` topic.

Without `--keep-e2e-cluster`, pytest removes the Kind cluster, Docker
containers, temporary images, and kubeconfig automatically. With the flag,
delete them after inspection:

```powershell
kind delete cluster --name <printed cluster name>
docker rm --force <printed ArangoDB and Redpanda containers>
```
