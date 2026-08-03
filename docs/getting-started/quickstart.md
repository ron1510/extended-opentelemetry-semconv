# Local Quickstart

The fastest way to see the project is the complete Kind environment:

```text
synthetic traces -> Collectors -> Redpanda -> Flink -> UI
```

You need Docker, Kind, `kubectl`, Helm 3, and enough local capacity for
Redpanda, two Collector routers, two backends, two JobManagers, a TaskManager,
the UI, and the demo.

## Run it

1. Build the three repository images.
2. Create an isolated Kind cluster.
3. Install one local Redpanda broker and create two topics.
4. Install the Collector and Flink charts.
5. Install the optional UI and demo charts.
6. Port-forward the UI to `http://localhost:8080`.

The exact tested PowerShell commands are in [Local Kind
Environment](../deployment/local-kind.md).

## What to observe

The demo begins with two service interactions and introduces more over time.
After reaching its configured maximum, it retires one edge whenever another is
introduced.

The expected lifecycle is:

1. a paired client/server trace reaches one Collector backend;
2. a non-zero delta metric reaches Kafka;
3. Flink emits an upsert;
4. the UI displays the authoritative semantic nodes and edges;
5. the demo stops sending one edge;
6. Flink waits for the configured inactivity TTL;
7. Flink emits a delete;
8. the UI removes elements that no longer have contributors.

Use the UI's Events tab to see commands and the Flink UI on port `8081` to see
checkpoints.

## Next

After confirming the pipeline, follow [Your First Custom
Entity](custom-entity.md) to change what the graph understands rather than only
changing its traffic.
