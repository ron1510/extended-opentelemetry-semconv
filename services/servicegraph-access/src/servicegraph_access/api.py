"""Typed HTTP query API over the Elasticsearch graph-element projection."""

# FastAPI registers local endpoint functions through decorators.
# Elasticsearch response bodies contain dynamically typed JSON values.
# pyright: reportUnusedFunction=false, reportUnknownMemberType=false

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Annotated, Literal, Protocol, cast

import uvicorn
from elastic_transport import ConnectionError as ElasticsearchConnectionError
from elastic_transport import ConnectionTimeout
from elasticsearch import ApiError, BadRequestError, Elasticsearch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from servicegraph_access.index import AccessSettings, IndicesClient, load_generated_mapping

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type ScalarValue = StrictBool | StrictInt | StrictFloat | StrictStr
type FieldType = Literal["keyword", "long", "double", "boolean"]


class QueryValidationError(ValueError):
    """Raised when a query is incompatible with the generated mapping."""


class ApiSettings(AccessSettings):
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8080, ge=1, le=65_535)
    elasticsearch_page_size: int = Field(default=1_000, gt=0, le=10_000)


class QueryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AndExpression(QueryModel):
    op: Literal["and"] = "and"
    operands: tuple[Expression, ...] = Field(min_length=1)


class OrExpression(QueryModel):
    op: Literal["or"] = "or"
    operands: tuple[Expression, ...] = Field(min_length=1)


class NotExpression(QueryModel):
    op: Literal["not"] = "not"
    operand: Expression


class EqualExpression(QueryModel):
    op: Literal["eq"] = "eq"
    field: str = Field(min_length=1)
    value: ScalarValue


class InExpression(QueryModel):
    op: Literal["in"] = "in"
    field: str = Field(min_length=1)
    values: tuple[ScalarValue, ...] = Field(min_length=1)


class RangeExpression(QueryModel):
    op: Literal["range"] = "range"
    field: str = Field(min_length=1)
    gt: StrictInt | StrictFloat | None = None
    gte: StrictInt | StrictFloat | None = None
    lt: StrictInt | StrictFloat | None = None
    lte: StrictInt | StrictFloat | None = None

    @model_validator(mode="after")
    def require_bound(self) -> RangeExpression:
        if all(value is None for value in (self.gt, self.gte, self.lt, self.lte)):
            raise ValueError("range requires at least one bound")
        return self


class ExistsExpression(QueryModel):
    op: Literal["exists"] = "exists"
    field: str = Field(min_length=1)


class RegexExpression(QueryModel):
    op: Literal["regex"] = "regex"
    field: str = Field(min_length=1)
    pattern: str = Field(min_length=1)


type Expression = Annotated[
    AndExpression
    | OrExpression
    | NotExpression
    | EqualExpression
    | InExpression
    | RangeExpression
    | ExistsExpression
    | RegexExpression,
    Field(discriminator="op"),
]

AndExpression.model_rebuild()
OrExpression.model_rebuild()
NotExpression.model_rebuild()


class SearchRequest(QueryModel):
    pattern: Expression


class SearchResponse(QueryModel):
    total: int = Field(ge=0)
    elements: tuple[dict[str, JsonValue], ...]


class QueryClient(Protocol):
    indices: IndicesClient

    def ping(self) -> bool: ...

    def open_point_in_time(self, *, index: str, keep_alive: str) -> Mapping[str, object]: ...

    def search(
        self,
        *,
        query: Mapping[str, object],
        pit: Mapping[str, object],
        size: int,
        sort: Sequence[str],
        search_after: Sequence[JsonValue] | None = None,
        track_total_hits: bool,
    ) -> Mapping[str, object]: ...

    def close_point_in_time(self, *, id: str) -> Mapping[str, object]: ...

    def close(self) -> None: ...


def field_catalog(mapping: Mapping[str, object] | None = None) -> dict[str, FieldType]:
    active_mapping = mapping or load_generated_mapping()
    properties = _mapping_value(active_mapping, "properties", "mapping")
    fields: dict[str, FieldType] = {}
    for name, definition_value in properties.items():
        if not isinstance(definition_value, Mapping):
            continue
        definition = cast(Mapping[str, object], definition_value)
        field_type = definition.get("type")
        if field_type in {"keyword", "long", "double", "boolean"}:
            fields[name] = cast(FieldType, field_type)
            continue
        children_value = definition.get("properties")
        if not isinstance(children_value, Mapping):
            continue
        children = cast(Mapping[str, object], children_value)
        for child_name, child_definition_value in children.items():
            if not isinstance(child_definition_value, Mapping):
                continue
            child_type = cast(Mapping[str, object], child_definition_value).get("type")
            if child_type in {"keyword", "long", "double", "boolean"}:
                fields[f"{name}.{child_name}"] = cast(FieldType, child_type)
    return dict(sorted(fields.items()))


def translate_expression(expression: Expression, fields: Mapping[str, FieldType]) -> dict[str, object]:
    if isinstance(expression, AndExpression):
        return {"bool": {"filter": [translate_expression(operand, fields) for operand in expression.operands]}}
    if isinstance(expression, OrExpression):
        return {
            "bool": {
                "should": [translate_expression(operand, fields) for operand in expression.operands],
                "minimum_should_match": 1,
            }
        }
    if isinstance(expression, NotExpression):
        return {"bool": {"must_not": [translate_expression(expression.operand, fields)]}}

    field_type = _field_type(expression.field, fields)
    if isinstance(expression, EqualExpression):
        return {"term": {expression.field: _typed_value(expression.field, expression.value, field_type)}}
    if isinstance(expression, InExpression):
        values = [_typed_value(expression.field, value, field_type) for value in expression.values]
        return {"terms": {expression.field: values}}
    if isinstance(expression, RangeExpression):
        if field_type not in {"long", "double"}:
            raise QueryValidationError(f"range requires a numeric field, found {expression.field!r}")
        bounds = {
            name: _numeric_value(expression.field, value, field_type)
            for name in ("gt", "gte", "lt", "lte")
            if (value := getattr(expression, name)) is not None
        }
        return {"range": {expression.field: bounds}}
    if isinstance(expression, ExistsExpression):
        return {"exists": {"field": expression.field}}
    if field_type != "keyword":
        raise QueryValidationError(f"regex requires a keyword field, found {expression.field!r}")
    return {"regexp": {expression.field: {"value": expression.pattern}}}


def execute_search(
    client: QueryClient,
    settings: ApiSettings,
    pattern: Expression,
    fields: Mapping[str, FieldType] | None = None,
) -> SearchResponse:
    query = translate_expression(pattern, fields or field_catalog())
    opened = client.open_point_in_time(index=settings.index_name, keep_alive="1m")
    pit_id = _required_string(opened, "id", "open point-in-time response")
    elements: list[dict[str, JsonValue]] = []
    search_after: tuple[JsonValue, ...] | None = None
    try:
        while True:
            response = client.search(
                query=query,
                pit={"id": pit_id, "keep_alive": "1m"},
                size=settings.elasticsearch_page_size,
                sort=("_shard_doc",),
                search_after=search_after,
                track_total_hits=True,
            )
            if isinstance(response.get("pit_id"), str):
                pit_id = cast(str, response["pit_id"])
            hits = _search_hits(response)
            if not hits:
                break
            for hit in hits:
                source = hit.get("_source")
                if not isinstance(source, dict):
                    raise RuntimeError("Elasticsearch search hit has no _source object")
                elements.append(cast(dict[str, JsonValue], source))
            sort_value = hits[-1].get("sort")
            if not isinstance(sort_value, Sequence) or isinstance(sort_value, (str, bytes)):
                raise RuntimeError("Elasticsearch search hit has no sort values")
            search_after = tuple(cast(Sequence[JsonValue], sort_value))
        return SearchResponse(total=len(elements), elements=tuple(elements))
    finally:
        client.close_point_in_time(id=pit_id)


def create_query_client(settings: ApiSettings) -> QueryClient:
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
            max_retries=3,
            retry_on_status=(429, 502, 503, 504),
            retry_on_timeout=True,
            basic_auth=basic_auth,
        )
    else:
        client = Elasticsearch(
            settings.urls,
            request_timeout=30,
            max_retries=3,
            retry_on_status=(429, 502, 503, 504),
            retry_on_timeout=True,
            basic_auth=basic_auth,
            ca_certs=str(settings.elasticsearch_ca_file),
        )
    return cast(QueryClient, client)


def create_app(settings: ApiSettings | None = None, client: QueryClient | None = None) -> FastAPI:
    config = settings or ApiSettings()
    owned_client = client is None
    active_client = client or create_query_client(config)
    fields = field_catalog()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        if owned_client:
            active_client.close()

    app = FastAPI(title="Servicegraph Access API", version="1.0.0", lifespan=lifespan)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        try:
            available = active_client.ping() and bool(active_client.indices.exists(index=config.index_name))
        except (ElasticsearchConnectionError, ConnectionTimeout, OSError) as error:
            raise HTTPException(status_code=503, detail="Elasticsearch is unavailable") from error
        if not available:
            raise HTTPException(status_code=503, detail="Elasticsearch index is unavailable")
        return {"status": "ready"}

    @app.post("/api/v1/elements/search", response_model=SearchResponse)
    def search(request: SearchRequest) -> SearchResponse:
        try:
            return execute_search(active_client, config, request.pattern, fields)
        except QueryValidationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except BadRequestError as error:
            raise HTTPException(status_code=400, detail="Elasticsearch rejected the query") from error
        except (ElasticsearchConnectionError, ConnectionTimeout, OSError) as error:
            raise HTTPException(status_code=503, detail="Elasticsearch is unavailable") from error
        except ApiError as error:
            raise HTTPException(status_code=502, detail="Elasticsearch query failed") from error

    return app


def main() -> None:
    settings = ApiSettings()
    uvicorn.run(create_app(settings), host=settings.api_host, port=settings.api_port)


def _mapping_value(mapping: Mapping[str, object], key: str, context: str) -> Mapping[str, object]:
    value = mapping.get(key)
    if not isinstance(value, Mapping):
        raise RuntimeError(f"{context} has no {key} object")
    return cast(Mapping[str, object], value)


def _field_type(field: str, fields: Mapping[str, FieldType]) -> FieldType:
    field_type = fields.get(field)
    if field_type is None:
        raise QueryValidationError(f"unknown query field: {field!r}")
    return field_type


def _typed_value(field: str, value: ScalarValue, field_type: FieldType) -> ScalarValue:
    if field_type == "keyword" and type(value) is str:
        return value
    if field_type == "long" and type(value) is int:
        return value
    if field_type == "double" and type(value) in {int, float}:
        return value
    if field_type == "boolean" and type(value) is bool:
        return value
    raise QueryValidationError(f"value {value!r} is incompatible with {field!r} ({field_type})")


def _numeric_value(field: str, value: int | float, field_type: FieldType) -> int | float:
    typed = _typed_value(field, value, field_type)
    if not isinstance(typed, (int, float)) or isinstance(typed, bool):
        raise QueryValidationError(f"range value for {field!r} must be numeric")
    return typed


def _required_string(response: Mapping[str, object], key: str, context: str) -> str:
    value = response.get(key)
    if not isinstance(value, str):
        raise RuntimeError(f"{context} has no {key}")
    return value


def _search_hits(response: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    hits_section = _mapping_value(response, "hits", "search response")
    hits_value = hits_section.get("hits")
    if not isinstance(hits_value, Sequence) or isinstance(hits_value, (str, bytes)):
        raise RuntimeError("Elasticsearch search response has no hits array")
    hits: list[Mapping[str, object]] = []
    for value in cast(Sequence[object], hits_value):
        if not isinstance(value, Mapping):
            raise RuntimeError("Elasticsearch search hit is not an object")
        hits.append(cast(Mapping[str, object], value))
    return tuple(hits)


if __name__ == "__main__":
    main()
