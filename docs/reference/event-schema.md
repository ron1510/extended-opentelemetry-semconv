# Graph Element Event Schema

The compacted `graph.elements.events` topic contains JSON lifecycle commands
keyed by `element_id`. The producer schema is `2.0`.

## Envelope

| Field | Type | Description |
| --- | --- | --- |
| `schema_version` | string | `"2.0"` |
| `event_id` | string | Deterministic SHA-256 transition ID |
| `event_type` | string | `"graph_element_state_changed"` |
| `operation` | string | `"upsert"` or `"delete"` |
| `element_id` | string | Graph element ID and Kafka key |
| `observed_at_unix_nano` | integer | Observation or final expiry time |
| `emitted_at_unix_ms` | integer | Event emission wall-clock time |
| `payload_hash` | string or null | Hash of the complete upsert element |
| `element` | object or null | Complete node or edge on upsert |

## Node upsert

```json
{
  "schema_version": "2.0",
  "event_id": "sha256",
  "event_type": "graph_element_state_changed",
  "operation": "upsert",
  "element_id": "service:checkout-api",
  "observed_at_unix_nano": 1784977200000000000,
  "emitted_at_unix_ms": 1784977200500,
  "payload_hash": "sha256",
  "element": {
    "kind": "node",
    "id": "service:checkout-api",
    "type": "service",
    "attributes": {
      "service.name": "checkout-api",
      "service.version": "2.4"
    }
  }
}
```

## Edge upsert

```json
{
  "schema_version": "2.0",
  "event_id": "sha256",
  "event_type": "graph_element_state_changed",
  "operation": "upsert",
  "element_id": "edge:sha256",
  "observed_at_unix_nano": 1784977200000000000,
  "emitted_at_unix_ms": 1784977200500,
  "payload_hash": "sha256",
  "element": {
    "kind": "edge",
    "id": "edge:sha256",
    "type": "calls",
    "source_id": "service:storefront",
    "target_id": "service:checkout-api",
    "attributes": {},
    "metrics": {
      "service_graph.request.total": 3,
      "service_graph.request.failed.total": 0
    }
  }
}
```

## Delete

```json
{
  "schema_version": "2.0",
  "event_id": "sha256",
  "event_type": "graph_element_state_changed",
  "operation": "delete",
  "element_id": "service:checkout-api",
  "observed_at_unix_nano": 1784977500000000000,
  "emitted_at_unix_ms": 1784977500100,
  "payload_hash": null,
  "element": null
}
```

Consumers must treat upsert as complete replacement, delete by `element_id`,
preserve per-key Kafka order, and avoid independent extraction or expiry logic.
Deterministic event IDs support deduplication under at-least-once delivery.
