from __future__ import annotations

import time

import pytest

from tests.e2e.environment import E2EEnvironment, JsonValue, wait_for


@pytest.mark.e2e
def test_flink_events_are_projected_as_current_elasticsearch_state(
    e2e_environment: E2EEnvironment,
) -> None:
    api_url = e2e_environment.start_api_port_forward()
    observed_at = time.time_ns()
    service_id = "service:checkout-api"
    edge_id = "edge:storefront-calls-checkout"
    service = _upsert(
        service_id,
        {
            "id": service_id,
            "kind": "node",
            "type": "service",
            "attributes": {"service.name": "checkout-api", "service.version": "2.4"},
        },
        observed_at,
        "service-v1",
    )
    edge = _upsert(
        edge_id,
        {
            "id": edge_id,
            "kind": "edge",
            "type": "calls",
            "source_id": "service:storefront",
            "target_id": service_id,
            "attributes": {},
            "metrics": {
                "service_graph.request.total": 12.0,
                "service_graph.request.failed.total": 1.0,
            },
        },
        observed_at,
        "edge-v1",
    )
    e2e_environment.produce_events((service, edge))

    initial = wait_for(
        "node and edge documents",
        60,
        lambda: _documents_by_id(e2e_environment, {service_id, edge_id}),
    )
    assert initial[service_id]["attributes"] == {
        "service.name": "checkout-api",
        "service.version": "2.4",
    }
    assert initial[edge_id]["source_id"] == "service:storefront"
    assert initial[edge_id]["metrics"] == {
        "service_graph.request.total": 12.0,
        "service_graph.request.failed.total": 1.0,
    }
    queried = e2e_environment.post_json(
        f"{api_url}/api/v1/elements/search",
        {
            "pattern": {
                "op": "and",
                "operands": [
                    {
                        "op": "or",
                        "operands": [
                            {"op": "regex", "field": "attributes.service.name", "pattern": "checkout-.*"},
                            {"op": "eq", "field": "type", "value": "calls"},
                        ],
                    },
                    {"op": "exists", "field": "id"},
                ],
            }
        },
    )
    assert queried["total"] == 2
    assert {str(element["id"]) for element in _elements(queried)} == {service_id, edge_id}

    updated_service = _upsert(
        service_id,
        {
            "id": service_id,
            "kind": "node",
            "type": "service",
            "attributes": {
                "service.name": "checkout-api",
                "service.version": "2.4",
                "service.criticality": "tier-1",
            },
        },
        observed_at + 1,
        "service-v2",
    )
    e2e_environment.produce_events((updated_service, updated_service))
    updated = wait_for(
        "idempotent complete replacement",
        60,
        lambda: _document_with_attribute(e2e_environment, service_id, "service.criticality", "tier-1"),
    )
    assert updated["attributes"] == {
        "service.name": "checkout-api",
        "service.version": "2.4",
        "service.criticality": "tier-1",
    }
    assert len([document for document in e2e_environment.elasticsearch_sources() if document["id"] == service_id]) == 1
    updated_query = e2e_environment.post_json(
        f"{api_url}/api/v1/elements/search",
        {
            "pattern": {
                "op": "eq",
                "field": "attributes.service.criticality",
                "value": "tier-1",
            }
        },
    )
    assert [element["id"] for element in _elements(updated_query)] == [service_id]
    assert wait_for("committed Kafka offsets", 30, lambda: e2e_environment.committed_offset() >= 4)

    e2e_environment.produce_events(
        (
            _delete(edge_id, observed_at + 2, "edge-delete"),
            _delete(service_id, observed_at + 2, "service-delete"),
        )
    )
    wait_for("deleted Elasticsearch state", 60, lambda: not e2e_environment.elasticsearch_sources())
    assert wait_for("delete offsets", 30, lambda: e2e_environment.committed_offset() >= 6)
    deleted_query = e2e_environment.post_json(
        f"{api_url}/api/v1/elements/search",
        {"pattern": {"op": "exists", "field": "id"}},
    )
    assert deleted_query == {"total": 0, "elements": []}


def _upsert(
    element_id: str,
    element: dict[str, object],
    observed_at_unix_nano: int,
    event_id: str,
) -> dict[str, object]:
    return {
        "schema_version": "1",
        "event_id": event_id,
        "event_type": "graph_element_state_changed",
        "operation": "upsert",
        "element_id": element_id,
        "payload_hash": f"hash-{event_id}",
        "observed_at_unix_nano": observed_at_unix_nano,
        "emitted_at_unix_ms": observed_at_unix_nano // 1_000_000,
        "element": element,
    }


def _delete(element_id: str, observed_at_unix_nano: int, event_id: str) -> dict[str, object]:
    return {
        "schema_version": "1",
        "event_id": event_id,
        "event_type": "graph_element_state_changed",
        "operation": "delete",
        "element_id": element_id,
        "payload_hash": None,
        "observed_at_unix_nano": observed_at_unix_nano,
        "emitted_at_unix_ms": observed_at_unix_nano // 1_000_000,
        "element": None,
    }


def _documents_by_id(
    environment: E2EEnvironment,
    expected_ids: set[str],
) -> dict[str, dict[str, JsonValue]] | None:
    documents = environment.elasticsearch_sources()
    by_id = {str(document["id"]): dict(document) for document in documents}
    return by_id if expected_ids <= by_id.keys() else None


def _document_with_attribute(
    environment: E2EEnvironment,
    element_id: str,
    attribute: str,
    expected: JsonValue,
) -> dict[str, JsonValue] | None:
    for document in environment.elasticsearch_sources():
        if document["id"] != element_id:
            continue
        attributes = document["attributes"]
        if isinstance(attributes, dict) and attributes.get(attribute) == expected:
            return dict(document)
    return None


def _elements(response: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    elements = response["elements"]
    assert isinstance(elements, list)
    return [element for value in elements if isinstance(value, dict) for element in [value]]
