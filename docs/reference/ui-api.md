# UI HTTP API

The optional UI is an indexed projection of Flink graph-element events.

## Health and status

- `GET /health/live` reports that the HTTP process is running.
- `GET /health/ready` requires the Kafka consumer to be running.
- `GET /api/v1/status` returns consumer state, topic, element/node/edge counts,
  and the most recent event time.

## Graph

`GET /api/v1/graph` returns nodes, edges, total counts, and `truncated`.

| Parameter | Meaning |
| --- | --- |
| `q` | Search node IDs, types, and attributes |
| `entity_type` | Include one node type and its connected graph |
| `edge_type` | Include one relationship type and its endpoints |

Edges are retained if they arrive before their nodes but omitted from this view
until both endpoint nodes exist.

## Elements

`GET /api/v1/elements` lists authoritative stored elements.

| Parameter | Meaning |
| --- | --- |
| `q` | Search IDs and attributes |
| `kind` | `node` or `edge` |
| `element_type` | Exact semantic entity or relationship type |
| `limit` | 1 to 500, default 100 |
| `offset` | Non-negative, default 0 |

## Events and OpenAPI

- `GET /api/v1/events` returns recently applied lifecycle events.
- `/docs`, `/redoc`, and `/openapi.json` expose the generated API definition.
