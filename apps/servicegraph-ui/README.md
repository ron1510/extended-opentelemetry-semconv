# Servicegraph UI

This service projects Flink interaction `upsert` and `delete` commands into a
queryable SQLite view and serves the interaction graph UI. Flink is the only
owner of staleness; this service never expires data based on time.
