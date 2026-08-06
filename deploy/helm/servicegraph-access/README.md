# servicegraph-access

Creates or verifies the strict `servicegraph-elements` index in an existing Elasticsearch 8.15+ cluster, then
projects Flink graph-element lifecycle events from Kafka into that current-state index. The chart does not install
Elasticsearch or ECK. A separate stateless API Deployment exposes typed Elasticsearch-backed element searches.

With a chart-created ServiceAccount the initializer runs after that account is installed. With
`serviceAccount.create=false`, it runs before installation. It always runs before upgrades and fails the release when
the existing mapping or settings differ from the generated contract.

The projector sends one Elasticsearch bulk request per Kafka poll. It commits Kafka offsets only after every bulk
item succeeds; deterministic element IDs make replayed upserts and deletes idempotent.

The API accepts recursive `and`, `or`, and `not` expressions with `eq`, `in`, `range`, `exists`, and `regex` leaves at
`POST /api/v1/elements/search`. It pages through a point-in-time Elasticsearch snapshot internally and returns every
matching document in one response.
