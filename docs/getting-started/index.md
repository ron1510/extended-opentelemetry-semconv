# Getting Started

The project has two related use cases.

## Use the semantic package

Use the Python package when you need typed OpenTelemetry entities or want to
normalize attributes into stable entity identifiers.

```python
from extended_otel_semconv import entities_from_attributes

entities = entities_from_attributes(
    {
        "service.name": "checkout-api",
        "service.namespace": "shop",
        "service.instance.id": "checkout-api/pod-7f8b",
        "http.request.method": "POST",
        "http.route": "/checkout/{cart_id}",
    }
)

for entity in entities:
    print(entity.entity_type, entity.entity_id)
```

An entity is created only when all of its identifying attributes are present.
Entity IDs are deterministic and URL-encode each identifying part.

Install the package from the repository:

```console
python -m pip install ./packages/extended-opentelemetry-semconv
```

Python 3.12 is required.

## Run the live graph pipeline

Use the complete runtime when you need a continuously maintained topology:

1. Applications emit paired OpenTelemetry client/server spans.
2. Collector routers keep all spans from a trace on one backend.
3. Collector backends derive service-graph metrics and publish them to Kafka.
4. Flink privately correlates observations and maintains graph-element state.
5. Consumers apply complete element `upsert` and `delete` commands.

The production deployment expects Kubernetes, Helm, Kafka-compatible brokers,
two pre-created topics, persistent storage for Flink, and an existing ArangoDB
3.12 deployment for the current-state property graph.

For an isolated demonstration, follow the [local Kind
quickstart](quickstart.md). For an existing cluster, follow the [Kubernetes
deployment guide](../deployment-and-operations.md).

## Understand the boundaries

The project intentionally does not:

- install or administer Kafka in production;
- create Kafka topics;
- modify your application instrumentation;
- infer staleness outside Flink;
- expose a custom HTTP query API;
- require a Flink Kubernetes Operator;
- require any Kubernetes CRD.

The supplied Redpanda instructions are only for local testing.
