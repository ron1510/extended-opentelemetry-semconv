# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from kafka.structs import TopicPartition
from pydantic import SecretStr, ValidationError

import servicegraph_access.projector as projector_module
from servicegraph_access.projector import (
    BulkClient,
    KafkaRecord,
    KafkaSecurityProtocol,
    ProjectionError,
    ProjectorSettings,
    create_consumer,
    create_elasticsearch_client,
    event_to_bulk_operations,
    project_poll,
)


class Record:
    def __init__(self, offset: int, value: bytes) -> None:
        self.offset = offset
        self.value = value


class FakeBulkClient:
    def __init__(self, response: Mapping[str, object]) -> None:
        self.response = response
        self.calls: list[tuple[Sequence[Mapping[str, object]], bool]] = []

    def bulk(
        self,
        *,
        operations: Sequence[Mapping[str, object]],
        refresh: bool,
    ) -> Mapping[str, object]:
        self.calls.append((operations, refresh))
        return self.response

    def close(self) -> None:
        pass


def _upsert(*, kind: str = "node", element_id: str = "service:checkout") -> bytes:
    element: dict[str, object] = {
        "id": element_id,
        "kind": kind,
        "type": "service" if kind == "node" else "calls",
        "attributes": {"service.name": "checkout"} if kind == "node" else {},
    }
    if kind == "edge":
        element.update(
            {
                "source_id": "service:storefront",
                "target_id": "service:checkout",
                "metrics": {"service_graph.request.total": 3.0},
            }
        )
    return json.dumps(
        {
            "schema_version": "1",
            "event_id": "event-1",
            "event_type": "graph_element_state_changed",
            "operation": "upsert",
            "element_id": element_id,
            "payload_hash": "hash-1",
            "observed_at_unix_nano": 123,
            "emitted_at_unix_ms": 456,
            "element": element,
        }
    ).encode()


def _delete(element_id: str = "service:checkout") -> bytes:
    return json.dumps(
        {
            "schema_version": "1",
            "event_id": "event-2",
            "event_type": "graph_element_state_changed",
            "operation": "delete",
            "element_id": element_id,
            "payload_hash": None,
            "observed_at_unix_nano": 789,
            "emitted_at_unix_ms": 999,
            "element": None,
        }
    ).encode()


def test_node_upsert_becomes_complete_index_document() -> None:
    operations = event_to_bulk_operations(_upsert(), "servicegraph-elements")

    assert operations[0] == {
        "index": {"_index": "servicegraph-elements", "_id": "service:checkout"}
    }
    assert operations[1] == {
        "schema_version": "1",
        "event_id": "event-1",
        "payload_hash": "hash-1",
        "id": "service:checkout",
        "kind": "node",
        "type": "service",
        "attributes": {"service.name": "checkout"},
        "metrics": {},
        "observed_at_unix_nano": 123,
        "emitted_at_unix_ms": 456,
    }


def test_edge_upsert_is_flattened_and_delete_uses_element_id() -> None:
    edge = event_to_bulk_operations(_upsert(kind="edge", element_id="edge:1"), "elements")
    assert edge[1]["source_id"] == "service:storefront"
    assert edge[1]["target_id"] == "service:checkout"
    assert edge[1]["metrics"] == {"service_graph.request.total": 3.0}

    assert event_to_bulk_operations(_delete("edge:1"), "elements") == (
        {"delete": {"_index": "elements", "_id": "edge:1"}},
    )


def test_one_poll_uses_one_bulk_request_then_commits_partition_offsets() -> None:
    first = TopicPartition("graph.elements.events", 0)
    second = TopicPartition("graph.elements.events", 1)
    consumer = Mock()
    client = FakeBulkClient(
        {
            "errors": False,
            "items": [
                {"index": {"status": 201}},
                {"delete": {"status": 200}},
                {"index": {"status": 200}},
            ],
        }
    )
    records = {
        first: [Record(4, _upsert()), Record(5, _delete())],
        second: [Record(11, _upsert(element_id="service:catalog"))],
    }

    assert project_poll(
        cast(Mapping[TopicPartition, Sequence[KafkaRecord]], records),
        consumer,
        cast(BulkClient, client),
        "elements",
    ) == 3

    assert len(client.calls) == 1
    operations, refresh = client.calls[0]
    assert len(operations) == 5
    assert refresh is False
    offsets = consumer.commit.call_args.kwargs["offsets"]
    assert offsets[first].offset == 6
    assert offsets[second].offset == 12


@pytest.mark.parametrize(
    "response",
    [
        {"items": [{"index": {"status": 400, "error": {"type": "strict_dynamic_mapping_exception"}}}]},
        {"items": []},
        {},
    ],
)
def test_bulk_item_failure_does_not_commit(response: Mapping[str, object]) -> None:
    consumer = Mock()
    client = FakeBulkClient(response)
    records = {TopicPartition("graph.elements.events", 0): [Record(2, _upsert())]}

    with pytest.raises(ProjectionError):
        project_poll(
            cast(Mapping[TopicPartition, Sequence[KafkaRecord]], records),
            consumer,
            cast(BulkClient, client),
            "elements",
        )

    consumer.commit.assert_not_called()


def test_delete_404_is_an_idempotent_success() -> None:
    consumer = Mock()
    client = FakeBulkClient({"errors": True, "items": [{"delete": {"status": 404}}]})
    records = {TopicPartition("graph.elements.events", 0): [Record(0, _delete())]}

    assert project_poll(
        cast(Mapping[TopicPartition, Sequence[KafkaRecord]], records),
        consumer,
        cast(BulkClient, client),
        "elements",
    ) == 1
    consumer.commit.assert_called_once()


def test_elasticsearch_auth_ca_and_retries_are_forwarded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    constructor = Mock(return_value=FakeBulkClient({"items": []}))
    monkeypatch.setattr(projector_module, "Elasticsearch", constructor)
    settings = ProjectorSettings(
        elasticsearch_urls="https://es:9200",
        elasticsearch_username="projector",
        elasticsearch_password=SecretStr("secret"),
        elasticsearch_ca_file=tmp_path / "es-ca.crt",
    )

    create_elasticsearch_client(settings)

    constructor.assert_called_once_with(
        ("https://es:9200",),
        request_timeout=10,
        max_retries=3,
        retry_on_status=(429, 502, 503, 504),
        retry_on_timeout=True,
        basic_auth=("projector", "secret"),
        ca_certs=str(tmp_path / "es-ca.crt"),
    )


def test_kafka_plaintext_and_sasl_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(projector_module, "KafkaConsumer", constructor)
    create_consumer(ProjectorSettings(kafka_bootstrap_servers="streaming:9093"))
    constructor.assert_called_once_with(
        "graph.elements.events",
        bootstrap_servers="streaming:9093",
        group_id="servicegraph-elasticsearch-projector",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=None,
        security_protocol="PLAINTEXT",
    )

    constructor.reset_mock()
    ca_file = tmp_path / "kafka-ca.crt"
    create_consumer(
        ProjectorSettings(
            kafka_security_protocol=KafkaSecurityProtocol.SASL_SSL,
            kafka_sasl_mechanism="SCRAM-SHA-256",
            kafka_sasl_username="projector",
            kafka_sasl_password=SecretStr("secret"),
            kafka_ssl_ca_file=ca_file,
        )
    )
    assert constructor.call_args.kwargs["sasl_plain_password"] == "secret"
    assert constructor.call_args.kwargs["ssl_cafile"] == ca_file.as_posix()

    with pytest.raises(ValidationError, match="require SASL_SSL"):
        ProjectorSettings(kafka_sasl_username="invalid")
