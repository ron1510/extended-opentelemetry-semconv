# Servicegraph Demo Chart

This optional chart runs one synthetic traffic producer. It emits paired
client/server spans through OTLP HTTP, grows the active service topology, and
then rotates edges. It does not write Kafka events or implement staleness;
those decisions remain in the Flink job.

```powershell
helm upgrade --install demo deploy/helm/servicegraph-demo `
  --namespace servicegraph-system `
  --set image.repository=registry.internal.example/extended-otel-servicegraph-demo `
  --set collector.endpoint=http://servicegraph-collector-router:4318/v1/traces
```

Set `traffic.randomSeed` for a repeatable sequence. Keep one replica unless
independent overlapping traffic generators are intentional.
