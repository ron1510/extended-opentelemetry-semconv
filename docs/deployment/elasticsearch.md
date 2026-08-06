# Elasticsearch Projection

The `servicegraph-access` image and Helm chart create or verify the strict index, continuously project Flink's
`graph.elements.events` lifecycle stream into it, and expose a typed query API. They do not install Elasticsearch;
Elasticsearch must already be available and ECK can manage it independently.

## Compatibility

The initializer uses the Elasticsearch Python client `8.15.1`, is integration-tested against Elasticsearch `8.15.5`,
and accepts servers from `8.15` through later `8.x` releases. Other major versions and Elasticsearch versions older
than `8.15` are rejected.

The fixed index name is `servicegraph-elements`. Its mapping is generated from the same semantic registry that owns
the Collector dimensions:

```console
python -m extended_otel_semconv.codegen
python -m extended_otel_semconv.codegen --check
```

The committed artifact is
`packages/extended-opentelemetry-semconv/src/extended_otel_semconv/metadata/elasticsearch-graph-elements-index.json`.
It uses strict dynamic mappings, preserves canonical dotted OpenTelemetry attribute names as literal fields, and
records its schema version, registry-lock digest, and deterministic mapping hash in `_meta`.

## Build the access image

Build from the repository root and publish the image to the registry reachable by your cluster:

```console
docker build --file apps/servicegraph-access/Dockerfile \
  --build-arg PIP_INDEX_URL=https://pypi.internal.example/simple \
  --tag registry.internal.example/extended-otel-servicegraph-access:0.3.0 .
```

## Credentials and CA

Create or externally manage an authentication Secret:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: servicegraph-elasticsearch-auth
type: Opaque
stringData:
  username: servicegraph-index-initializer
  password: replace-me
```

Create a separate Secret containing the CA used by the ECK HTTP certificate:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: servicegraph-elasticsearch-ca
type: Opaque
stringData:
  ca.crt: |
    -----BEGIN CERTIFICATE-----
    ...
    -----END CERTIFICATE-----
```

The chart identity needs `create_index`, `view_index_metadata`, `index`, and `delete` privileges for
`servicegraph-elements`. Access to basic server information is also required for the compatibility check; grant the
minimum cluster-level permission required by your Elasticsearch security policy.

## Install against ECK

Use the ECK HTTP Service as the endpoint. The initializer needs no Kubernetes API access and does not read ECK
resources.

```yaml
# internal-access-values.yaml
image:
  repository: registry.internal.example/extended-otel-servicegraph-access
  tag: "0.3.0"

serviceAccount:
  create: false
  name: servicegraph-access

elasticsearch:
  urls:
    - https://production-es-http.elasticsearch.svc:9200
  indexName: servicegraph-elements
  numberOfShards: 1
  numberOfReplicas: 1
  refreshInterval: 5s
  auth:
    existingSecret: servicegraph-elasticsearch-auth
    usernameKey: username
    passwordKey: password
  tls:
    existingSecret: servicegraph-elasticsearch-ca
    caKey: ca.crt

streamContract:
  kafka:
    brokers:
      - kafka.internal.example:9092
    security:
      protocol: SASL_SSL
      saslMechanism: SCRAM-SHA-256
      existingSecret: servicegraph-kafka-auth
      usernameKey: username
      passwordKey: password
      caKey: ca.crt
  topics:
    interactionEvents: graph.elements.events

projector:
  replicas: 1
  groupId: servicegraph-elasticsearch-projector

api:
  replicas: 1
  port: 8080
  elasticsearchPageSize: 1000
```

```console
helm upgrade --install access deploy/helm/servicegraph-access \
  --namespace servicegraph-system \
  --values internal-access-values.yaml \
  --wait
```

With an existing ServiceAccount the initializer runs as a `pre-install` and `pre-upgrade` hook. When the chart creates
the ServiceAccount, initial creation uses `post-install` because a pre-install Pod cannot reference a chart resource
that Helm has not created; upgrades still use `pre-upgrade`.

The initializer creates a missing index and exits without mutation when mapping and settings match. Any mapping hash,
field, shard, replica, or refresh-interval mismatch fails the Helm operation. It never deletes, recreates, or modifies
an existing index.

The projector also verifies the index at startup, then consumes with auto-commit disabled. Each Kafka poll becomes one
Elasticsearch bulk request: upserts replace the complete document under `element_id`, and deletes remove that ID.
Offsets are committed only when every bulk item succeeds. A failed batch terminates the process without committing;
Kubernetes restarts it and Kafka replays the records. Elasticsearch search visibility follows the configured refresh
interval, which defaults to five seconds.

The Elasticsearch identity used by the long-running projector needs `index` and `delete` privileges in addition to
the initializer's `create_index` and `view_index_metadata` privileges. The API identity also needs `read` and
`view_index_metadata`. The Kafka identity needs read access to
`graph.elements.events` and group access for `servicegraph-elasticsearch-projector`.

Projector replicas share one Kafka consumer group. Increasing replicas provides useful concurrency only up to the
number of partitions in `graph.elements.events`.

## Query graph elements

Port-forward the internal API Service for local access:

```console
kubectl port-forward --namespace servicegraph-system service/access-servicegraph-access-api 8080:8080
```

Submit a recursive pattern:

```console
curl --request POST http://127.0.0.1:8080/api/v1/elements/search \
  --header 'content-type: application/json' \
  --data '{
    "pattern": {
      "op": "and",
      "operands": [
        {"op": "eq", "field": "kind", "value": "node"},
        {
          "op": "or",
          "operands": [
            {"op": "regex", "field": "attributes.service.name", "pattern": "checkout-.*"},
            {"op": "in", "field": "type", "values": ["service", "app.endpoint"]}
          ]
        }
      ]
    }
  }'
```

Supported operations are `and`, `or`, `not`, `eq`, `in`, `range`, `exists`, and `regex`. Fields and values are
validated against the generated mapping. Regex patterns use Elasticsearch syntax.

The API opens a point-in-time snapshot and retrieves matches in pages of `api.elasticsearchPageSize`, but returns a
single `{total, elements}` response without a public cap or pagination token. Large matches therefore consume memory
in both the gateway and caller until public pagination is added.

!!! warning
    The primary shard count cannot be changed in place. Select it before the first installation. Changing shard count,
    replica count, refresh interval, or the generated mapping in values/code causes verification to fail; migration is
    an explicit future concern, not an automatic initializer action.

## Local Elasticsearch 8.15 validation

The opt-in test starts `docker.elastic.co/elasticsearch/elasticsearch:8.15.5` directly with security disabled, one
primary shard, zero replicas, and a 512 MiB heap. It validates strict types, dotted fields, queries, replacement,
deletion, idempotent initialization, and incompatible mapping rejection.

```console
python -m pytest -m elasticsearch --run-elasticsearch
```

The container is removed automatically. Its final bounded logs are printed to pytest output when the test fails.
Plain HTTP without authentication is supported only for this local validation path.
