"""Load and verify the generated ArangoDB graph topology."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_RESOURCE = "metadata/arangodb-graph-schema.json"


class SchemaError(RuntimeError):
    """Raised when the generated graph schema is invalid."""


class IdentifyingProperty(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attribute: str
    property: str


class VertexCollection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    semantic_type: str
    collection: str
    identifying_properties: tuple[IdentifyingProperty, ...] = ()


class EdgeCollection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    semantic_type: str
    collection: str
    from_collections: tuple[str, ...] = Field(alias="from")
    to_collections: tuple[str, ...] = Field(alias="to")


class PropertyAliases(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attributes: dict[str, str]
    metrics: dict[str, str]


class SchemaMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    upstream_registry_lock_sha256: str
    schema_hash: str


class GraphSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: SchemaMetadata = Field(alias="_meta")
    graph_name: str
    vertex_collections: tuple[VertexCollection, ...]
    edge_collections: tuple[EdgeCollection, ...]
    property_aliases: PropertyAliases
    reserved_properties: tuple[str, ...]

    @property
    def vertices_by_type(self) -> dict[str, VertexCollection]:
        return {item.semantic_type: item for item in self.vertex_collections}

    @property
    def edges_by_type(self) -> dict[str, EdgeCollection]:
        return {item.semantic_type: item for item in self.edge_collections}


def load_graph_schema() -> GraphSchema:
    resource = files("servicegraph_indexer").joinpath(SCHEMA_RESOURCE)
    decoded = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise SchemaError(f"generated resource {SCHEMA_RESOURCE} must be an object")
    document = cast(dict[str, object], decoded)
    metadata = document.get("_meta")
    if not isinstance(metadata, dict):
        raise SchemaError(f"generated resource {SCHEMA_RESOURCE} has no _meta object")
    typed_metadata = cast(dict[str, object], metadata)
    declared = typed_metadata.get("schema_hash")
    normalized = cast(dict[str, object], json.loads(json.dumps(document)))
    normalized_metadata = cast(dict[str, object], normalized["_meta"])
    normalized_metadata.pop("schema_hash", None)
    computed = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if declared != computed:
        raise SchemaError(f"generated resource {SCHEMA_RESOURCE} has invalid schema hash")
    return GraphSchema.model_validate(document)
