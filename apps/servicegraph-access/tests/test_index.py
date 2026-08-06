# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from pydantic import SecretStr, ValidationError

import servicegraph_access.index as index_module
from servicegraph_access.index import (
    AccessSettings,
    ElasticsearchClient,
    IndexInitializationError,
    IndexSettings,
    _computed_mapping_hash,
    _mapping_hash,
    create_client,
    ensure_index,
    initialize,
    load_generated_mapping,
    validate_server_version,
    wait_for_elasticsearch,
)


class FakeIndices:
    def __init__(self, *, exists: bool = False) -> None:
        self.index_exists = exists
        self.mappings: Mapping[str, object] | None = None
        self.settings: Mapping[str, object] | None = None
        self.created: tuple[str, Mapping[str, object], Mapping[str, object]] | None = None

    def exists(self, *, index: str) -> object:
        return self.index_exists

    def create(self, *, index: str, mappings: Mapping[str, object], settings: Mapping[str, object]) -> object:
        self.created = (index, mappings, settings)
        return {"acknowledged": True}

    def get_mapping(self, *, index: str) -> Mapping[str, object]:
        return {index: {"mappings": self.mappings}}

    def get_settings(
        self,
        *,
        index: str,
        flat_settings: bool,
        include_defaults: bool,
    ) -> Mapping[str, object]:
        assert flat_settings is True
        assert include_defaults is False
        return {index: {"settings": self.settings}}


class FakeClient:
    def __init__(self, responses: list[object] | None = None, *, exists: bool = False) -> None:
        self.indices = FakeIndices(exists=exists)
        self.responses = responses or [{"version": {"number": "8.15.5"}}]
        self.info_calls = 0
        self.closed = False

    def info(self) -> Mapping[str, object]:
        response = self.responses[min(self.info_calls, len(self.responses) - 1)]
        self.info_calls += 1
        if isinstance(response, Exception):
            raise response
        return cast(Mapping[str, object], response)

    def close(self) -> None:
        self.closed = True


def _existing_client() -> FakeClient:
    client = FakeClient(exists=True)
    client.indices.mappings = load_generated_mapping()
    client.indices.settings = {
        "index.number_of_shards": "1",
        "index.number_of_replicas": "1",
        "index.refresh_interval": "5s",
    }
    return client


def test_missing_index_is_created_with_generated_contract() -> None:
    client = FakeClient()
    settings = AccessSettings(connection_deadline_seconds=1)

    assert initialize(settings, cast(ElasticsearchClient, client)) == "created"

    created = client.indices.created
    assert created is not None
    assert created[0] == "servicegraph-elements"
    assert created[1] == load_generated_mapping()
    assert created[2] == {"number_of_shards": 1, "number_of_replicas": 1, "refresh_interval": "5s"}
    assert client.closed is False


def test_generated_mapping_hash_detects_field_tampering() -> None:
    mapping = load_generated_mapping()
    assert _computed_mapping_hash(mapping) == _mapping_hash(mapping)

    tampered = copy.deepcopy(mapping)
    properties = cast(dict[str, object], tampered["properties"])
    cast(dict[str, object], properties["id"])["type"] = "text"
    assert _computed_mapping_hash(tampered) != _mapping_hash(tampered)


def test_exact_existing_index_is_unchanged() -> None:
    client = _existing_client()

    assert ensure_index(cast(ElasticsearchClient, client), IndexSettings(), load_generated_mapping()) == "unchanged"
    assert client.indices.created is None


def test_connection_wait_retries_and_times_out() -> None:
    recovering = FakeClient([OSError("not ready"), {"version": {"number": "8.15.5"}}])

    assert wait_for_elasticsearch(cast(ElasticsearchClient, recovering), 2, sleep=lambda _: None) == {
        "version": {"number": "8.15.5"}
    }
    assert recovering.info_calls == 2

    clock_value = 0.0

    def clock() -> float:
        nonlocal clock_value
        clock_value += 0.1
        return clock_value

    unavailable = FakeClient([OSError("still unavailable")])
    with pytest.raises(IndexInitializationError, match="did not become available"):
        wait_for_elasticsearch(
            cast(ElasticsearchClient, unavailable),
            0.2,
            monotonic=clock,
            sleep=lambda _: None,
        )


@pytest.mark.parametrize("version", ["7.17.0", "8.14.3", "9.0.0", "invalid"])
def test_incompatible_versions_are_rejected(version: str) -> None:
    with pytest.raises(IndexInitializationError, match="incompatible|invalid"):
        validate_server_version({"version": {"number": version}})


@pytest.mark.parametrize("version", ["8.15.0", "8.19.2"])
def test_supported_versions_are_accepted(version: str) -> None:
    validate_server_version({"version": {"number": version}})


def test_mapping_hash_and_field_mismatches_are_rejected() -> None:
    expected = load_generated_mapping()
    hash_mismatch = copy.deepcopy(expected)
    cast(dict[str, object], hash_mismatch["_meta"])["mapping_hash"] = "different"
    client = _existing_client()
    client.indices.mappings = hash_mismatch
    with pytest.raises(IndexInitializationError, match="mapping hash mismatch"):
        ensure_index(cast(ElasticsearchClient, client), IndexSettings(), expected)

    field_mismatch = copy.deepcopy(expected)
    properties = cast(dict[str, object], field_mismatch["properties"])
    cast(dict[str, object], properties["id"])["type"] = "text"
    client.indices.mappings = field_mismatch
    with pytest.raises(IndexInitializationError, match="field definitions"):
        ensure_index(cast(ElasticsearchClient, client), IndexSettings(), expected)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("index.number_of_shards", "2"),
        ("index.number_of_replicas", "0"),
        ("index.refresh_interval", "1s"),
    ],
)
def test_setting_mismatches_are_rejected(name: str, value: str) -> None:
    client = _existing_client()
    assert client.indices.settings is not None
    client.indices.settings = {**client.indices.settings, name: value}

    with pytest.raises(IndexInitializationError, match=name):
        ensure_index(cast(ElasticsearchClient, client), IndexSettings(), load_generated_mapping())


def test_authentication_and_ca_are_forwarded_to_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    constructor = Mock(return_value=FakeClient())
    monkeypatch.setattr(index_module, "Elasticsearch", constructor)
    ca_file = tmp_path / "ca.crt"
    settings = AccessSettings(
        elasticsearch_urls="https://es-0:9200, https://es-1:9200/",
        elasticsearch_username="servicegraph",
        elasticsearch_password=SecretStr("secret"),
        elasticsearch_ca_file=ca_file,
    )

    create_client(settings)

    constructor.assert_called_once_with(
        ("https://es-0:9200", "https://es-1:9200"),
        request_timeout=30,
        max_retries=0,
        retry_on_timeout=False,
        basic_auth=("servicegraph", "secret"),
        ca_certs=str(ca_file),
    )


def test_plain_http_rejects_credentials_but_supports_local_no_auth() -> None:
    assert AccessSettings(elasticsearch_urls="http://localhost:9200").urls == ("http://localhost:9200",)
    with pytest.raises(ValidationError, match="credentials require HTTPS"):
        AccessSettings(
            elasticsearch_urls="http://localhost:9200",
            elasticsearch_username="user",
            elasticsearch_password=SecretStr("password"),
        )
