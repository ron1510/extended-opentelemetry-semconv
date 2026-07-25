# Interaction Event Schema

The `graph.interactions.events` topic contains JSON commands keyed by
`interaction_id`. The current producer schema is `1.1`.

## Common envelope

Every command has:

| Field | Type | Description |
| --- | --- | --- |
| `schema_version` | string | Currently `"1.1"` |
| `event_id` | string | Deterministic SHA-256 event identifier |
| `event_type` | string | `"interaction_state_changed"` |
| `operation` | string | `"upsert"` or `"delete"` |
| `interaction_id` | string | Deterministic interaction identifier and Kafka key |
| `observed_at_unix_nano` | integer | Observation or expiry time |
| `emitted_at_unix_ms` | integer | Wall-clock event emission time |
| `payload_hash` | string or null | Hash of the upsert payload |
| `interaction` | object or null | Current interaction for upserts |

## Upsert example

```json
{
  "schema_version": "1.1",
  "event_id": "a deterministic sha256 value",
  "event_type": "interaction_state_changed",
  "operation": "upsert",
  "interaction_id": "a deterministic sha256 value",
  "observed_at_unix_nano": 1784977200000000000,
  "emitted_at_unix_ms": 1784977200500,
  "payload_hash": "a deterministic sha256 value",
  "interaction": {
    "client": "storefront",
    "server": "checkout-api",
    "connection_type": "calls",
    "dimensions": {
      "server_http.request.method": "POST",
      "server_http.route": "/checkout"
    },
    "metrics": {
      "traces_service_graph_request_total": 3
    },
    "entities": [
      {
        "id": "service:storefront",
        "type": "service"
      },
      {
        "id": "service:checkout-api",
        "type": "service"
      }
    ],
    "graph": {
      "nodes": [
        {
          "id": "service:storefront",
          "type": "service",
          "attributes": {
            "service.name": "storefront"
          }
        }
      ],
      "edges": [
        {
          "source": "service:storefront",
          "target": "service:checkout-api",
          "type": "calls",
          "attributes": {
            "service_graph.request.total": 3
          }
        }
      ]
    }
  }
}
```

The exact dimensions depend on generated Collector configuration and emitted
telemetry.

## Delete example

```json
{
  "schema_version": "1.1",
  "event_id": "a deterministic sha256 value",
  "event_type": "interaction_state_changed",
  "operation": "delete",
  "interaction_id": "a deterministic sha256 value",
  "observed_at_unix_nano": 1784977500000000000,
  "emitted_at_unix_ms": 1784977500100,
  "payload_hash": null,
  "interaction": null
}
```

## Consumer rules

1. Use the Kafka record key as the interaction key.
2. Upsert the complete interaction payload on `upsert`.
3. Remove that interaction on `delete`.
4. Make both operations idempotent.
5. Deduplicate by `event_id` when duplicate side effects matter.
6. Do not infer deletion from wall-clock age.
7. Reject unsupported major schema behavior explicitly.

Schema `1.1` added graph nodes and edges. The supplied UI reader accepts `1.0`
and `1.1`, while the current Flink producer emits `1.1`.
