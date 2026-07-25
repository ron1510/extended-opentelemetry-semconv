# UI HTTP API

The optional visualization service exposes health, graph, entity, interaction,
and event endpoints.

## Health

### `GET /health/live`

Returns `200` when the HTTP process is running.

### `GET /health/ready`

Returns `200` when the Kafka consumer is running. It returns `503` with the
consumer error when startup or consumption has failed.

## Status

### `GET /api/v1/status`

Returns consumer status, topic, graph counts, and the most recent event time.

```console
curl http://localhost:8080/api/v1/status
```

## Graph

### `GET /api/v1/graph`

Optional query parameters:

| Parameter | Meaning |
| --- | --- |
| `q` | Search node IDs, types, and attributes |
| `entity_type` | Include one entity type |
| `edge_type` | Include one relationship type |

```console
curl "http://localhost:8080/api/v1/graph?entity_type=k8s.pod"
curl "http://localhost:8080/api/v1/graph?edge_type=runs"
```

The response contains nodes, edges, total counts, and a `truncated` flag.

## Entities

### `GET /api/v1/entities`

Parameters:

- `q`: optional search, maximum 200 characters;
- `entity_type`: optional exact type;
- `limit`: 1 to 500, default 100;
- `offset`: non-negative, default 0.

## Interactions

### `GET /api/v1/interactions`

Lists current interactions with `limit` and `offset` pagination.

### `GET /api/v1/interactions/{interaction_id}`

Returns one current interaction or `404` when it is absent.

## Recent events

### `GET /api/v1/events`

Returns recent applied commands. `limit` is 1 to 1,000 and defaults to 100.
This history is diagnostic; the current graph remains the authoritative
projection.

## OpenAPI

FastAPI also exposes:

- `/docs` for Swagger UI;
- `/redoc` for ReDoc;
- `/openapi.json` for the machine-readable schema.
