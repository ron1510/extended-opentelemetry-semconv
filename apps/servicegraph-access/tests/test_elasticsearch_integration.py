from __future__ import annotations

import copy
import json
import socket
import subprocess
import uuid
from collections.abc import Iterator
from typing import cast

import pytest
from elasticsearch import BadRequestError, Elasticsearch
from fastapi.testclient import TestClient

from servicegraph_access.api import ApiSettings, QueryClient, create_app
from servicegraph_access.index import (
    AccessSettings,
    IndexInitializationError,
    IndexSettings,
    ensure_index,
    initialize,
    load_generated_mapping,
)
from servicegraph_access.projector import event_to_bulk_operations

ELASTICSEARCH_IMAGE = "docker.elastic.co/elasticsearch/elasticsearch:8.15.5"


@pytest.fixture(scope="module")
def elasticsearch_url(request: pytest.FixtureRequest) -> Iterator[str]:
    if not request.config.getoption("--run-elasticsearch"):
        pytest.skip("pass --run-elasticsearch to start disposable Elasticsearch 8.15")
    subprocess.run(["docker", "version"], check=True, capture_output=True, text=True)
    container = f"servicegraph-es-{uuid.uuid4().hex[:10]}"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    run = subprocess.run(
        [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--name",
            container,
            "--publish",
            f"127.0.0.1:{port}:9200",
            "--env",
            "discovery.type=single-node",
            "--env",
            "xpack.security.enabled=false",
            "--env",
            "ES_JAVA_OPTS=-Xms512m -Xmx512m",
            ELASTICSEARCH_IMAGE,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert run.stdout.strip()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        if request.session.testsfailed:
            logs = subprocess.run(
                ["docker", "logs", "--tail", "80", container],
                check=False,
                capture_output=True,
                text=True,
            )
            print("\nElasticsearch integration logs:\n" + logs.stdout + logs.stderr)
        subprocess.run(["docker", "rm", "--force", container], check=False, capture_output=True, text=True)


@pytest.mark.elasticsearch
def test_real_elasticsearch_index_lifecycle(elasticsearch_url: str) -> None:
    settings = AccessSettings(
        elasticsearch_urls=elasticsearch_url,
        number_of_replicas=0,
        connection_deadline_seconds=120,
    )
    assert initialize(settings) == "created"
    assert initialize(settings) == "unchanged"

    client = Elasticsearch(elasticsearch_url)
    node_id = "service:checkout"
    edge_id = "edge:checkout-catalog"
    node: dict[str, object] = {
        "schema_version": "1",
        "event_id": "event-node-1",
        "payload_hash": "hash-node-1",
        "id": node_id,
        "kind": "node",
        "type": "service",
        "attributes": {
            "service.name": "checkout",
            "http.request.method": "POST",
            "process.pid": 42,
            "process.interactive": False,
        },
        "metrics": {},
        "observed_at_unix_nano": 1_725_000_000_000_000_000,
        "emitted_at_unix_ms": 1_725_000_000_000,
    }
    edge: dict[str, object] = {
        "schema_version": "1",
        "event_id": "event-edge-1",
        "payload_hash": "hash-edge-1",
        "id": edge_id,
        "kind": "edge",
        "type": "calls",
        "source_id": "service:checkout",
        "target_id": "service:catalog",
        "attributes": {},
        "metrics": {
            "service_graph.request.total": 12.0,
            "service_graph.request.failed.total": 2.0,
        },
        "observed_at_unix_nano": 1_725_000_000_000_000_000,
        "emitted_at_unix_ms": 1_725_000_000_000,
    }
    client.index(index=settings.index_name, id=node_id, document=node, refresh=True)
    client.index(index=settings.index_name, id=edge_id, document=edge, refresh=True)
    catalog: dict[str, object] = {
        **node,
        "event_id": "event-catalog-1",
        "payload_hash": "hash-catalog-1",
        "id": "service:catalog",
        "attributes": {
            "service.name": "catalog",
            "process.pid": 84,
            "process.interactive": True,
        },
    }
    client.index(index=settings.index_name, id="service:catalog", document=catalog, refresh=True)

    api = TestClient(
        create_app(
            ApiSettings(
                elasticsearch_urls=elasticsearch_url,
                number_of_replicas=0,
                elasticsearch_page_size=2,
            ),
            cast(QueryClient, client),
        )
    )
    all_elements = api.post(
        "/api/v1/elements/search",
        json={"pattern": {"op": "exists", "field": "id"}},
    )
    assert all_elements.status_code == 200
    assert all_elements.json()["total"] == 3

    nodes = api.post(
        "/api/v1/elements/search",
        json={
            "pattern": {
                "op": "and",
                "operands": [
                    {
                        "op": "or",
                        "operands": [
                            {
                                "op": "regex",
                                "field": "attributes.service.name",
                                "pattern": "checkout.*|catalog.*",
                            },
                            {"op": "eq", "field": "type", "value": "missing"},
                        ],
                    },
                    {"op": "not", "operand": {"op": "exists", "field": "source_id"}},
                ],
            }
        },
    )
    assert nodes.status_code == 200
    assert {element["id"] for element in nodes.json()["elements"]} == {node_id, "service:catalog"}

    ranged_edges = api.post(
        "/api/v1/elements/search",
        json={
            "pattern": {
                "op": "and",
                "operands": [
                    {"op": "exists", "field": "source_id"},
                    {"op": "range", "field": "metrics.service_graph.request.total", "gte": 10},
                ],
            }
        },
    )
    assert ranged_edges.status_code == 200
    assert [element["id"] for element in ranged_edges.json()["elements"]] == [edge_id]

    for field, value in (
        ("attributes.service.name", "checkout"),
        ("attributes.http.request.method", "POST"),
        ("attributes.process.pid", 42),
        ("attributes.process.interactive", False),
    ):
        result = client.search(index=settings.index_name, query={"term": {field: value}})
        assert result["hits"]["total"]["value"] == 1
    metric_result = client.search(
        index=settings.index_name,
        query={"range": {"metrics.service_graph.request.total": {"gte": 10.0}}},
    )
    assert metric_result["hits"]["total"]["value"] == 1

    replacement = copy.deepcopy(node)
    cast(dict[str, object], replacement["attributes"])["service.name"] = "checkout-v2"
    client.index(index=settings.index_name, id=node_id, document=replacement, refresh=True)
    stored = client.get(index=settings.index_name, id=node_id)
    assert stored["_source"]["attributes"]["service.name"] == "checkout-v2"

    unknown = copy.deepcopy(node)
    cast(dict[str, object], unknown["attributes"])["custom.unknown"] = "rejected"
    with pytest.raises(BadRequestError):
        client.index(index=settings.index_name, id="invalid-unknown", document=unknown)
    invalid_number = copy.deepcopy(node)
    cast(dict[str, object], invalid_number["attributes"])["process.pid"] = "42"
    with pytest.raises(BadRequestError):
        client.index(index=settings.index_name, id="invalid-number", document=invalid_number)

    client.delete(index=settings.index_name, id=edge_id, refresh=True)
    assert not bool(client.exists(index=settings.index_name, id=edge_id))

    incompatible_name = "servicegraph-elements-incompatible"
    incompatible = copy.deepcopy(load_generated_mapping())
    incompatible_properties = cast(dict[str, object], incompatible["properties"])
    cast(dict[str, object], incompatible_properties["id"])["type"] = "text"
    client.indices.create(
        index=incompatible_name,
        mappings=incompatible,
        settings={"number_of_shards": 1, "number_of_replicas": 0, "refresh_interval": "5s"},
    )
    with pytest.raises(IndexInitializationError, match="field definitions"):
        ensure_index(
            client,  # type: ignore[arg-type]
            IndexSettings(name=incompatible_name, number_of_replicas=0),
            load_generated_mapping(),
        )

    lifecycle_id = "service:projected"
    lifecycle_event: dict[str, object] = {
        "schema_version": "1",
        "event_id": "projected-event-1",
        "event_type": "graph_element_state_changed",
        "operation": "upsert",
        "element_id": lifecycle_id,
        "payload_hash": "projected-hash-1",
        "observed_at_unix_nano": 1_725_000_000_000_000_000,
        "emitted_at_unix_ms": 1_725_000_000_000,
        "element": {
            "id": lifecycle_id,
            "kind": "node",
            "type": "service",
            "attributes": {"service.name": "projected"},
        },
    }
    first = client.bulk(
        operations=event_to_bulk_operations(json.dumps(lifecycle_event), settings.index_name),
        refresh=True,
    )
    assert first["errors"] is False

    lifecycle_event["event_id"] = "projected-event-2"
    lifecycle_event["payload_hash"] = "projected-hash-2"
    projected_element = cast(dict[str, object], lifecycle_event["element"])
    projected_element["attributes"] = {"service.name": "projected-v2"}
    replacement_result = client.bulk(
        operations=event_to_bulk_operations(json.dumps(lifecycle_event), settings.index_name),
        refresh=True,
    )
    replay_result = client.bulk(
        operations=event_to_bulk_operations(json.dumps(lifecycle_event), settings.index_name),
        refresh=True,
    )
    assert replacement_result["errors"] is False
    assert replay_result["errors"] is False
    projected = client.search(index=settings.index_name, query={"term": {"id": lifecycle_id}})
    assert projected["hits"]["total"]["value"] == 1
    assert projected["hits"]["hits"][0]["_source"]["attributes"]["service.name"] == "projected-v2"

    lifecycle_event.update(
        {
            "event_id": "projected-event-3",
            "operation": "delete",
            "payload_hash": None,
            "element": None,
        }
    )
    deletion = event_to_bulk_operations(json.dumps(lifecycle_event), settings.index_name)
    assert client.bulk(operations=deletion, refresh=True)["errors"] is False
    replayed_deletion = client.bulk(operations=deletion, refresh=True)
    assert replayed_deletion["items"][0]["delete"]["status"] == 404
    assert not bool(client.exists(index=settings.index_name, id=lifecycle_id))
    client.close()
