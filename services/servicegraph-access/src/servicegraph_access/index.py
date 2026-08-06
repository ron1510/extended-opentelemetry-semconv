"""Create or verify the Elasticsearch graph-elements index."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from collections.abc import Callable, Mapping
from importlib.resources import files
from pathlib import Path
from typing import Protocol, cast

from elastic_transport import ConnectionError as ElasticsearchConnectionError
from elastic_transport import ConnectionTimeout
from elasticsearch import ConflictError, Elasticsearch
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_INDEX_NAME = "servicegraph-elements"
MAPPING_RESOURCE = "metadata/elasticsearch-graph-elements-index.json"
SUPPORTED_MINIMUM_VERSION = (8, 15)
REFRESH_INTERVAL_PATTERN = re.compile(r"^(?:-1|[1-9][0-9]*(?:ms|s|m|h|d))$")


class IndexInitializationError(RuntimeError):
    """Raised when Elasticsearch cannot safely use the requested index."""


class IndexSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = DEFAULT_INDEX_NAME
    number_of_shards: int = Field(default=1, gt=0)
    number_of_replicas: int = Field(default=1, ge=0)
    refresh_interval: str = "5s"

    @model_validator(mode="after")
    def validate_refresh_interval(self) -> IndexSettings:
        if not REFRESH_INTERVAL_PATTERN.fullmatch(self.refresh_interval):
            raise ValueError("refresh_interval must be -1 or a positive Elasticsearch time value")
        return self


class AccessSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SERVICEGRAPH_ACCESS_", extra="ignore", frozen=True)

    elasticsearch_urls: str = "http://localhost:9200"
    elasticsearch_username: str | None = None
    elasticsearch_password: SecretStr | None = None
    elasticsearch_ca_file: Path | None = None
    index_name: str = DEFAULT_INDEX_NAME
    number_of_shards: int = Field(default=1, gt=0)
    number_of_replicas: int = Field(default=1, ge=0)
    refresh_interval: str = "5s"
    connection_deadline_seconds: float = Field(default=300, gt=0)

    @property
    def urls(self) -> tuple[str, ...]:
        return tuple(item.strip().rstrip("/") for item in self.elasticsearch_urls.split(",") if item.strip())

    @property
    def index(self) -> IndexSettings:
        return IndexSettings(
            name=self.index_name,
            number_of_shards=self.number_of_shards,
            number_of_replicas=self.number_of_replicas,
            refresh_interval=self.refresh_interval,
        )

    @model_validator(mode="after")
    def validate_connection(self) -> AccessSettings:
        if not self.urls:
            raise ValueError("at least one Elasticsearch URL is required")
        if any(not url.startswith(("http://", "https://")) for url in self.urls):
            raise ValueError("Elasticsearch URLs must use http or https")
        has_username = self.elasticsearch_username is not None
        has_password = self.elasticsearch_password is not None
        if has_username != has_password:
            raise ValueError("Elasticsearch username and password must be configured together")
        if has_username and any(url.startswith("http://") for url in self.urls):
            raise ValueError("Elasticsearch credentials require HTTPS")
        return self


class IndicesClient(Protocol):
    def exists(self, *, index: str) -> object: ...

    def create(self, *, index: str, mappings: Mapping[str, object], settings: Mapping[str, object]) -> object: ...

    def get_mapping(self, *, index: str) -> Mapping[str, object]: ...

    def get_settings(
        self,
        *,
        index: str,
        flat_settings: bool,
        include_defaults: bool,
    ) -> Mapping[str, object]: ...


class ElasticsearchClient(Protocol):
    indices: IndicesClient

    def info(self) -> Mapping[str, object]: ...

    def close(self) -> None: ...


def load_generated_mapping() -> dict[str, object]:
    resource = files("extended_otel_semconv").joinpath(MAPPING_RESOURCE)
    document = json.loads(resource.read_text(encoding="utf-8"))
    mappings = document.get("mappings")
    if not isinstance(mappings, dict):
        raise IndexInitializationError(f"generated resource {MAPPING_RESOURCE} has no mappings object")
    typed_mappings = cast(dict[str, object], mappings)
    declared_hash = _mapping_hash(typed_mappings)
    computed_hash = _computed_mapping_hash(typed_mappings)
    if declared_hash != computed_hash:
        raise IndexInitializationError(
            f"generated resource {MAPPING_RESOURCE} has invalid mapping hash: "
            f"declared {declared_hash!r}, computed {computed_hash!r}"
        )
    return typed_mappings


def create_client(settings: AccessSettings) -> ElasticsearchClient:
    basic_auth: tuple[str, str] | None = None
    if settings.elasticsearch_username is not None and settings.elasticsearch_password is not None:
        basic_auth = (
            settings.elasticsearch_username,
            settings.elasticsearch_password.get_secret_value(),
        )
    if settings.elasticsearch_ca_file is None:
        client = Elasticsearch(
            settings.urls,
            request_timeout=30,
            max_retries=0,
            retry_on_timeout=False,
            basic_auth=basic_auth,
        )
    else:
        client = Elasticsearch(
            settings.urls,
            request_timeout=30,
            max_retries=0,
            retry_on_timeout=False,
            basic_auth=basic_auth,
            ca_certs=str(settings.elasticsearch_ca_file),
        )
    return cast(ElasticsearchClient, client)


def wait_for_elasticsearch(
    client: ElasticsearchClient,
    deadline_seconds: float,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Mapping[str, object]:
    deadline = monotonic() + deadline_seconds
    last_error: Exception | None = None
    while monotonic() < deadline:
        try:
            return client.info()
        except (ElasticsearchConnectionError, ConnectionTimeout, OSError) as error:
            last_error = error
            sleep(min(1.0, max(0.0, deadline - monotonic())))
    detail = f": {last_error}" if last_error is not None else ""
    raise IndexInitializationError(f"Elasticsearch did not become available within {deadline_seconds:g}s{detail}")


def validate_server_version(info: Mapping[str, object]) -> None:
    version = info.get("version")
    version_mapping: Mapping[str, object]
    if isinstance(version, Mapping):  # noqa: SIM108 - explicit branches preserve strict generic typing
        version_mapping = cast(Mapping[str, object], version)
    else:
        version_mapping = {}
    number = version_mapping.get("number")
    if not isinstance(number, str):
        raise IndexInitializationError("Elasticsearch response does not contain version.number")
    try:
        major, minor = (int(part) for part in number.split(".", maxsplit=2)[:2])
    except ValueError as error:
        raise IndexInitializationError(f"invalid Elasticsearch version: {number}") from error
    if major != 8 or minor < SUPPORTED_MINIMUM_VERSION[1]:
        raise IndexInitializationError(
            f"Elasticsearch {number} is incompatible; expected 8.15 or a later 8.x release"
        )


def ensure_index(
    client: ElasticsearchClient,
    index: IndexSettings,
    mappings: Mapping[str, object],
) -> str:
    if not bool(client.indices.exists(index=index.name)):
        try:
            client.indices.create(index=index.name, mappings=mappings, settings=_desired_settings(index))
            return "created"
        except ConflictError:
            # The initializer Job and projector can race on the first chart install.
            pass

    response = client.indices.get_mapping(index=index.name)
    existing_mappings = _index_section(response, index.name, "mappings")
    _verify_mapping(mappings, existing_mappings)

    settings_response = client.indices.get_settings(
        index=index.name,
        flat_settings=True,
        include_defaults=False,
    )
    existing_settings = _index_section(settings_response, index.name, "settings")
    _verify_settings(index, existing_settings)
    return "unchanged"


def initialize(settings: AccessSettings, client: ElasticsearchClient | None = None) -> str:
    owned_client = client is None
    active_client = client or create_client(settings)
    try:
        info = wait_for_elasticsearch(active_client, settings.connection_deadline_seconds)
        validate_server_version(info)
        return ensure_index(active_client, settings.index, load_generated_mapping())
    finally:
        if owned_client:
            active_client.close()


def main() -> int:
    try:
        settings = AccessSettings()
        result = initialize(settings)
    except Exception as error:
        print(f"servicegraph index initialization failed: {error}", file=sys.stderr)
        return 1
    print(f"Elasticsearch index {settings.index_name} is {result}")
    return 0


def _desired_settings(index: IndexSettings) -> dict[str, object]:
    return {
        "number_of_shards": index.number_of_shards,
        "number_of_replicas": index.number_of_replicas,
        "refresh_interval": index.refresh_interval,
    }


def _index_section(response: Mapping[str, object], index_name: str, section: str) -> Mapping[str, object]:
    index = response.get(index_name)
    index_mapping: Mapping[str, object]
    if isinstance(index, Mapping):  # noqa: SIM108 - explicit branches preserve strict generic typing
        index_mapping = cast(Mapping[str, object], index)
    else:
        index_mapping = {}
    value = index_mapping.get(section)
    if not isinstance(value, Mapping):
        raise IndexInitializationError(f"Elasticsearch response has no {section} for index {index_name}")
    return cast(Mapping[str, object], value)


def _verify_mapping(expected: Mapping[str, object], actual: Mapping[str, object]) -> None:
    expected_hash = _mapping_hash(expected)
    actual_hash = _mapping_hash(actual)
    if actual_hash != expected_hash:
        raise IndexInitializationError(
            f"mapping hash mismatch: expected {expected_hash!r}, found {actual_hash!r}"
        )
    if actual != expected:
        difference = _first_mapping_difference(expected, actual)
        raise IndexInitializationError(f"mapping field definitions do not match the generated contract: {difference}")


def _mapping_hash(mappings: Mapping[str, object]) -> object:
    metadata = mappings.get("_meta")
    metadata_mapping: Mapping[str, object]
    if isinstance(metadata, Mapping):  # noqa: SIM108 - explicit branches preserve strict generic typing
        metadata_mapping = cast(Mapping[str, object], metadata)
    else:
        metadata_mapping = {}
    return metadata_mapping.get("mapping_hash")


def _computed_mapping_hash(mappings: Mapping[str, object]) -> str:
    normalized_value: object = json.loads(json.dumps(mappings))
    if not isinstance(normalized_value, dict):
        raise IndexInitializationError("generated mappings are not a JSON object")
    normalized = cast(dict[str, object], normalized_value)
    metadata_value = normalized.get("_meta")
    if not isinstance(metadata_value, dict):
        raise IndexInitializationError("generated mappings have no _meta object")
    metadata = cast(dict[str, object], metadata_value)
    metadata.pop("mapping_hash", None)
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _first_mapping_difference(expected: object, actual: object, path: str = "mappings") -> str:
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        expected_mapping = cast(Mapping[str, object], expected)
        actual_mapping = cast(Mapping[str, object], actual)
        for key in sorted(set(expected_mapping) | set(actual_mapping)):
            child_path = f"{path}.{key}"
            if key not in expected_mapping:
                return f"{child_path} is unexpected"
            if key not in actual_mapping:
                return f"{child_path} is missing"
            difference = _first_mapping_difference(expected_mapping[key], actual_mapping[key], child_path)
            if difference:
                return difference
        return ""
    if expected != actual:
        return f"{path}: expected {expected!r}, found {actual!r}"
    return ""


def _verify_settings(index: IndexSettings, actual: Mapping[str, object]) -> None:
    expected = {
        "index.number_of_shards": str(index.number_of_shards),
        "index.number_of_replicas": str(index.number_of_replicas),
        "index.refresh_interval": index.refresh_interval,
    }
    mismatches = [
        f"{name}: expected {value!r}, found {actual.get(name)!r}"
        for name, value in expected.items()
        if str(actual.get(name)) != value
    ]
    if mismatches:
        raise IndexInitializationError("index settings mismatch: " + "; ".join(mismatches))


if __name__ == "__main__":
    raise SystemExit(main())
