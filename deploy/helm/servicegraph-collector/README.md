# Servicegraph Collector Chart

This chart deploys two stateless OTLP routers and two service-graph backends.
The backends run as a StatefulSet behind a headless Service, giving both
routers the same fixed two-member hash ring. Trace-ID routing therefore keeps
paired spans on the same backend. The backends export OTLP JSON metrics to the
configured Kafka topic.

Each backend converts its connector-local cumulative counters to deltas before
Kafka. This allows both backends to contribute to one logical interaction
without interleaved cumulative streams looking like counter resets in Flink.

```powershell
helm upgrade --install servicegraph deploy/helm/servicegraph-collector `
  --namespace servicegraph-system --create-namespace `
  --values internal-collector-values.yaml
```

Values must provide the internal image, Kafka brokers, topic names, and an
existing Secret for `SASL_PLAINTEXT` or `SASL_SSL`. The chart creates neither topics nor
credentials. Version 0.2 fixes both replica counts at two because changing the
backend count remaps the trace hash ring and can split in-flight trace pairs.

Generate registry-derived dimensions with:

```powershell
python -m tools.semconv_codegen
```
