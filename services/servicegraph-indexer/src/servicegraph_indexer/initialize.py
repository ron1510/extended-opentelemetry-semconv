"""Create or verify the generated ArangoDB service graph topology."""

# python-arango exposes dynamic response types at this adapter boundary.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportMissingModuleSource=false

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol, cast

from arango.client import ArangoClient
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from servicegraph_indexer.schema import EdgeCollection, GraphSchema, VertexCollection, load_graph_schema

DOCUMENT_COLLECTION_TYPE = 2
EDGE_COLLECTION_TYPE = 3
TINKERPOP_VARIABLES_COLLECTION = "TINKERPOP-GRAPH-VARIABLES"
TINKERPOP_PROVIDER_VERSION = "4.0.0"


class TopologyInitializationError(RuntimeError):
    """Raised when existing ArangoDB topology is incompatible."""


class ArangoSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SERVICEGRAPH_INDEXER_", extra="ignore", frozen=True)

    arango_urls: str = "http://localhost:8529"
    arango_database: str = "servicegraph"
    arango_graph: str = "servicegraph"
    arango_username: str = "root"
    arango_password: SecretStr
    arango_verify_tls: bool = True
    allow_database_creation: bool = False
    connection_deadline_seconds: float = Field(default=300, gt=0)

    @property
    def urls(self) -> tuple[str, ...]:
        return tuple(item.strip().rstrip("/") for item in self.arango_urls.split(",") if item.strip())

    @model_validator(mode="after")
    def validate_urls(self) -> ArangoSettings:
        if not self.urls:
            raise ValueError("at least one ArangoDB URL is required")
        if any(not url.startswith(("http://", "https://")) for url in self.urls):
            raise ValueError("ArangoDB URLs must use http or https")
        return self


class CollectionBoundary(Protocol):
    def properties(self) -> Mapping[str, object]: ...

    def indexes(self) -> Sequence[Mapping[str, object]]: ...

    def add_persistent_index(
        self,
        *,
        fields: Sequence[str],
        unique: bool,
        sparse: bool,
        name: str,
    ) -> object: ...

    def get(self, document: str) -> Mapping[str, object] | None: ...

    def insert(self, document: Mapping[str, object]) -> object: ...


class GraphBoundary(Protocol):
    def edge_definitions(self) -> Sequence[Mapping[str, object]]: ...

    def create_edge_definition(
        self,
        *,
        edge_collection: str,
        from_vertex_collections: Sequence[str],
        to_vertex_collections: Sequence[str],
    ) -> object: ...


class DatabaseBoundary(Protocol):
    def version(self) -> str: ...

    def has_collection(self, name: str) -> bool: ...

    def create_collection(self, name: str, *, edge: bool = False) -> object: ...

    def collection(self, name: str) -> CollectionBoundary: ...

    def has_graph(self, name: str) -> bool: ...

    def create_graph(
        self,
        name: str,
        *,
        edge_definitions: Sequence[Mapping[str, object]],
        orphan_collections: Sequence[str],
    ) -> GraphBoundary: ...

    def graph(self, name: str) -> GraphBoundary: ...


def create_database(settings: ArangoSettings) -> DatabaseBoundary:
    client = ArangoClient(hosts=list(settings.urls), verify_override=settings.arango_verify_tls)
    password = settings.arango_password.get_secret_value()
    system = client.db("_system", username=settings.arango_username, password=password)
    if not system.has_database(settings.arango_database):
        if not settings.allow_database_creation:
            raise TopologyInitializationError(
                f"ArangoDB database {settings.arango_database!r} does not exist and creation is disabled"
            )
        system.create_database(settings.arango_database)
    database = client.db(
        settings.arango_database,
        username=settings.arango_username,
        password=password,
    )
    return cast(DatabaseBoundary, database)


def wait_for_database(
    database: DatabaseBoundary,
    deadline_seconds: float,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    deadline = monotonic() + deadline_seconds
    last_error: Exception | None = None
    while monotonic() < deadline:
        try:
            return database.version()
        except (OSError, RuntimeError) as error:
            last_error = error
            sleep(min(1.0, max(0.0, deadline - monotonic())))
    detail = f": {last_error}" if last_error is not None else ""
    raise TopologyInitializationError(f"ArangoDB did not become available within {deadline_seconds:g}s{detail}")


def ensure_topology(database: DatabaseBoundary, schema: GraphSchema, graph_name: str) -> str:
    changed = _ensure_tinkerpop_variables(database, graph_name)
    for vertex in schema.vertex_collections:
        changed = _ensure_collection(database, vertex.collection, edge=False) or changed
        changed = _ensure_indexes(database.collection(vertex.collection), vertex) or changed
    for edge in schema.edge_collections:
        changed = _ensure_collection(database, edge.collection, edge=True) or changed
        changed = _ensure_indexes(database.collection(edge.collection), edge) or changed

    desired_definitions = [_edge_definition(item) for item in schema.edge_collections]
    covered_vertices = {
        collection
        for definition in desired_definitions
        for field in ("from_vertex_collections", "to_vertex_collections")
        for collection in cast(Sequence[str], definition[field])
    }
    orphans = sorted({item.collection for item in schema.vertex_collections} - covered_vertices)
    if not database.has_graph(graph_name):
        database.create_graph(graph_name, edge_definitions=desired_definitions, orphan_collections=orphans)
        return "created"

    graph = database.graph(graph_name)
    existing = {_definition_name(item): _normalize_definition(item) for item in graph.edge_definitions()}
    desired = {_definition_name(item): _normalize_definition(item) for item in desired_definitions}
    unexpected = sorted(set(existing) - set(desired))
    if unexpected:
        raise TopologyInitializationError(f"graph {graph_name!r} has unexpected edge definitions: {unexpected}")
    for name, definition in desired.items():
        current = existing.get(name)
        if current is not None and current != definition:
            raise TopologyInitializationError(
                f"graph edge definition {name!r} does not match generated topology: {current!r}"
            )
        if current is None:
            graph.create_edge_definition(
                edge_collection=name,
                from_vertex_collections=cast(Sequence[str], definition["from_vertex_collections"]),
                to_vertex_collections=cast(Sequence[str], definition["to_vertex_collections"]),
            )
            changed = True
    return "updated" if changed else "unchanged"


def _ensure_tinkerpop_variables(database: DatabaseBoundary, graph_name: str) -> bool:
    changed = _ensure_collection(database, TINKERPOP_VARIABLES_COLLECTION, edge=False)
    collection = database.collection(TINKERPOP_VARIABLES_COLLECTION)
    if collection.get(graph_name) is None:
        collection.insert({"_key": graph_name, "_version": TINKERPOP_PROVIDER_VERSION})
        return True
    return changed


def initialize(settings: ArangoSettings, database: DatabaseBoundary | None = None) -> str:
    active_database = database or create_database(settings)
    wait_for_database(active_database, settings.connection_deadline_seconds)
    schema = load_graph_schema()
    graph_name = settings.arango_graph or schema.graph_name
    return ensure_topology(active_database, schema, graph_name)


def main() -> int:
    try:
        settings = ArangoSettings()  # pyright: ignore[reportCallIssue]
        result = initialize(settings)
    except Exception as error:
        print(f"service graph topology initialization failed: {error}", file=sys.stderr)
        return 1
    print(f"ArangoDB graph {settings.arango_graph} is {result}")
    return 0


def _ensure_collection(database: DatabaseBoundary, name: str, *, edge: bool) -> bool:
    if not database.has_collection(name):
        database.create_collection(name, edge=edge)
        return True
    properties = database.collection(name).properties()
    expected_type = EDGE_COLLECTION_TYPE if edge else DOCUMENT_COLLECTION_TYPE
    if properties.get("type") != expected_type:
        kind = "edge" if edge else "document"
        raise TopologyInitializationError(f"collection {name!r} exists but is not a {kind} collection")
    return False


def _ensure_indexes(collection: CollectionBoundary, definition: VertexCollection | EdgeCollection) -> bool:
    changed = _ensure_index(collection, "sg_element_id", ("element_id",), unique=True, sparse=False)
    if isinstance(definition, VertexCollection):
        for identifying in definition.identifying_properties:
            changed = _ensure_index(
                collection,
                f"sg_identity_{identifying.property}",
                (identifying.property,),
                unique=False,
                sparse=True,
            ) or changed
    return changed


def _ensure_index(
    collection: CollectionBoundary,
    name: str,
    fields: tuple[str, ...],
    *,
    unique: bool,
    sparse: bool,
) -> bool:
    for index in collection.indexes():
        index_name = str(index.get("name", "")).rsplit("/", maxsplit=1)[-1]
        if index_name != name:
            continue
        actual_fields = index.get("fields")
        if not isinstance(actual_fields, Sequence) or isinstance(actual_fields, str | bytes):
            raise TopologyInitializationError(f"index {name!r} has invalid fields: {actual_fields!r}")
        typed_fields = cast(Sequence[object], actual_fields)
        actual = (tuple(str(field) for field in typed_fields), bool(index.get("unique")), bool(index.get("sparse")))
        expected = (fields, unique, sparse)
        if actual != expected:
            raise TopologyInitializationError(
                f"index {name!r} is incompatible: expected {expected!r}, found {actual!r}"
            )
        return False
    collection.add_persistent_index(fields=fields, unique=unique, sparse=sparse, name=name)
    return True


def _edge_definition(edge: EdgeCollection) -> dict[str, object]:
    return {
        "edge_collection": edge.collection,
        "from_vertex_collections": list(edge.from_collections),
        "to_vertex_collections": list(edge.to_collections),
    }


def _definition_name(definition: Mapping[str, object]) -> str:
    name = definition.get("edge_collection") or definition.get("collection")
    if not isinstance(name, str):
        raise TopologyInitializationError(f"invalid graph edge definition: {definition!r}")
    return name


def _normalize_definition(definition: Mapping[str, object]) -> dict[str, object]:
    return {
        "edge_collection": _definition_name(definition),
        "from_vertex_collections": sorted(cast(Sequence[str], definition.get("from_vertex_collections", ()))),
        "to_vertex_collections": sorted(cast(Sequence[str], definition.get("to_vertex_collections", ()))),
    }


if __name__ == "__main__":
    raise SystemExit(main())
