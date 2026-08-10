from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import cast
from unittest.mock import Mock

import pytest
from kafka.structs import TopicPartition
from pydantic import SecretStr, ValidationError

import servicegraph_indexer.indexer as indexer_module
from servicegraph_indexer.indexer import (
    ConsumerBoundary,
    IndexerSettings,
    IndexingError,
    KafkaRecord,
    KafkaSecurityProtocol,
    WriterBoundary,
    create_consumer,
    element_key,
    event_to_document,
    project_poll,
)
from servicegraph_indexer.schema import load_graph_schema


class Record:
    def __init__(self, offset: int, value: bytes) -> None:
        self.offset = offset
        self.value = value


class FakeWriter:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.replacements: list[tuple[str, Sequence[Mapping[str, object]]]] = []
        self.deletions: list[tuple[str, Sequence[str]]] = []

    def replace_many(self, collection: str, documents: Sequence[Mapping[str, object]]) -> None:
        if self.fail:
            raise RuntimeError("database failed")
        self.replacements.append((collection, documents))

    def delete_many(self, collection: str, keys: Sequence[str]) -> None:
        if self.fail:
            raise RuntimeError("database failed")
        self.deletions.append((collection, keys))


def _upsert(*, kind: str = "node", element_id: str = "service:checkout", event_id: str = "event-1") -> bytes:
    element: dict[str, object] = {
        "id": element_id,
        "kind": kind,
        "type": "service" if kind == "node" else "calls",
        "attributes": {"service.name": "checkout", "service.version": "1.4.0"} if kind == "node" else {},
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
            "schema_version": "2.0",
            "event_id": event_id,
            "event_type": "graph_element_state_changed",
            "operation": "upsert",
            "element_id": element_id,
            "payload_hash": "hash-1",
            "observed_at_unix_nano": 123,
            "emitted_at_unix_ms": 456,
            "element": element,
        }
    ).encode()


def _delete(element_id: str) -> bytes:
    return json.dumps(
        {
            "schema_version": "2.0",
            "event_id": "event-delete",
            "event_type": "graph_element_state_changed",
            "operation": "delete",
            "element_id": element_id,
            "payload_hash": None,
            "observed_at_unix_nano": 789,
            "emitted_at_unix_ms": 999,
            "element": None,
        }
    ).encode()


def test_node_and_edge_documents_preserve_maps_and_add_aliases() -> None:
    schema = load_graph_schema()
    node_event = cast(Mapping[str, object], json.loads(_upsert()))
    collection, node = event_to_document(node_event, schema)
    assert collection == "service"
    assert node["_key"] == element_key("service:checkout")
    assert node["attributes"] == {"service.name": "checkout", "service.version": "1.4.0"}
    assert node["service_name"] == "checkout"
    assert node["service_version"] == "1.4.0"

    edge_event = cast(Mapping[str, object], json.loads(_upsert(kind="edge", element_id="edge:one")))
    edge_collection, edge = event_to_document(edge_event, schema)
    assert edge_collection == "calls"
    assert edge["_from"] == f"service/{element_key('service:storefront')}"
    assert edge["_to"] == f"service/{element_key('service:checkout')}"
    assert edge["service_graph_request_total"] == 3.0


def test_poll_coalesces_events_routes_deletes_and_commits_after_writes() -> None:
    partition = TopicPartition("graph.elements.events", 0)
    consumer = Mock(spec=ConsumerBoundary)
    writer = FakeWriter()
    records = {
        partition: [
            Record(2, _upsert(event_id="old")),
            Record(3, _upsert(event_id="new")),
            Record(4, _delete("k8s.pod:pod-1")),
            Record(5, _delete("edge:dead")),
        ]
    }

    assert project_poll(
        cast(Mapping[TopicPartition, Sequence[KafkaRecord]], records),
        consumer,
        cast(WriterBoundary, writer),
        load_graph_schema(),
    ) == 4
    assert len(writer.replacements) == 1
    assert writer.replacements[0][1][0]["event_id"] == "new"
    assert ("k8s_pod", [element_key("k8s.pod:pod-1")]) in writer.deletions
    edge_deletes = [item for item in writer.deletions if item[0] != "k8s_pod"]
    assert len(edge_deletes) == 9
    assert all(keys == [element_key("edge:dead")] for _, keys in edge_deletes)
    offsets = consumer.commit.call_args.kwargs["offsets"]
    assert offsets[partition].offset == 6
    assert offsets[partition].metadata == ""


def test_database_failure_does_not_commit() -> None:
    partition = TopicPartition("graph.elements.events", 0)
    consumer = Mock(spec=ConsumerBoundary)
    records = {partition: [Record(0, _upsert())]}
    with pytest.raises(RuntimeError, match="database failed"):
        project_poll(
            cast(Mapping[TopicPartition, Sequence[KafkaRecord]], records),
            consumer,
            cast(WriterBoundary, FakeWriter(fail=True)),
            load_graph_schema(),
        )
    consumer.commit.assert_not_called()


def test_invalid_events_fail_visibly() -> None:
    schema = load_graph_schema()
    with pytest.raises(IndexingError, match="only upsert"):
        event_to_document(cast(Mapping[str, object], json.loads(_delete("service:checkout"))), schema)
    event = cast(dict[str, object], json.loads(_upsert()))
    cast(dict[str, object], event["element"])["type"] = "unknown"
    with pytest.raises(IndexingError, match="unknown node"):
        event_to_document(event, schema)


def test_kafka_plaintext_and_sasl_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    constructor = Mock(return_value=Mock())
    monkeypatch.setattr(indexer_module, "KafkaConsumer", constructor)
    create_consumer(
        IndexerSettings(arango_password=SecretStr("arango"), kafka_bootstrap_servers="streaming:9093")
    )
    constructor.assert_called_once_with(
        "graph.elements.events",
        bootstrap_servers="streaming:9093",
        group_id="servicegraph-arangodb-indexer",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=None,
        security_protocol="PLAINTEXT",
    )

    for protocol in (KafkaSecurityProtocol.SASL_PLAINTEXT, KafkaSecurityProtocol.SASL_SSL):
        constructor.reset_mock()
        create_consumer(
            IndexerSettings(
                arango_password=SecretStr("arango"),
                kafka_security_protocol=protocol,
                kafka_sasl_mechanism="SCRAM-SHA-256",
                kafka_sasl_username="indexer",
                kafka_sasl_password=SecretStr("secret"),
            )
        )
        assert constructor.call_args.kwargs["security_protocol"] == protocol.value
        assert constructor.call_args.kwargs["sasl_plain_password"] == "secret"

    with pytest.raises(ValidationError, match="require SASL_PLAINTEXT or SASL_SSL"):
        IndexerSettings(arango_password=SecretStr("arango"), kafka_sasl_username="invalid")
