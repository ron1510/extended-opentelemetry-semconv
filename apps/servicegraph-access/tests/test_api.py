# pyright: reportUnknownMemberType=false

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from servicegraph_access.api import (
    ApiSettings,
    Expression,
    QueryClient,
    QueryValidationError,
    SearchRequest,
    create_app,
    execute_search,
    field_catalog,
    translate_expression,
)


class FakeIndices:
    def __init__(self, exists: bool = True) -> None:
        self.index_exists = exists

    def exists(self, *, index: str) -> object:
        return self.index_exists


class FakeQueryClient:
    def __init__(self, responses: Sequence[Mapping[str, object] | Exception] = ()) -> None:
        self.indices = FakeIndices()
        self.responses = list(responses)
        self.search_calls: list[dict[str, object]] = []
        self.closed_pits: list[str] = []
        self.client_closed = False
        self.ping_result = True

    def ping(self) -> bool:
        return self.ping_result

    def open_point_in_time(self, *, index: str, keep_alive: str) -> Mapping[str, object]:
        assert index == "servicegraph-elements"
        assert keep_alive == "1m"
        return {"id": "pit-1"}

    def search(
        self,
        *,
        query: Mapping[str, object],
        pit: Mapping[str, object],
        size: int,
        sort: Sequence[str],
        search_after: Sequence[object] | None = None,
        track_total_hits: bool,
    ) -> Mapping[str, object]:
        self.search_calls.append(
            {
                "query": query,
                "pit": pit,
                "size": size,
                "sort": sort,
                "search_after": search_after,
                "track_total_hits": track_total_hits,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close_point_in_time(self, *, id: str) -> Mapping[str, object]:
        self.closed_pits.append(id)
        return {"succeeded": True}

    def close(self) -> None:
        self.client_closed = True


def _expression(document: Mapping[str, object]) -> Expression:
    return SearchRequest.model_validate({"pattern": document}).pattern


def test_generated_field_catalog_contains_root_semantic_and_metric_types() -> None:
    fields = field_catalog()

    assert fields["kind"] == "keyword"
    assert fields["attributes.service.name"] == "keyword"
    assert fields["attributes.process.pid"] == "long"
    assert fields["attributes.process.interactive"] == "boolean"
    assert fields["metrics.service_graph.request.total"] == "double"
    assert "attributes" not in fields


def test_nested_boolean_expression_translates_to_elasticsearch_dsl() -> None:
    expression = _expression(
        {
            "op": "and",
            "operands": [
                {"op": "eq", "field": "kind", "value": "node"},
                {
                    "op": "or",
                    "operands": [
                        {"op": "regex", "field": "attributes.service.name", "pattern": "checkout-.*"},
                        {"op": "in", "field": "type", "values": ["service", "app.endpoint"]},
                    ],
                },
                {"op": "not", "operand": {"op": "exists", "field": "attributes.k8s.pod.uid"}},
            ],
        }
    )

    assert translate_expression(expression, field_catalog()) == {
        "bool": {
            "filter": [
                {"term": {"kind": "node"}},
                {
                    "bool": {
                        "should": [
                            {"regexp": {"attributes.service.name": {"value": "checkout-.*"}}},
                            {"terms": {"type": ["service", "app.endpoint"]}},
                        ],
                        "minimum_should_match": 1,
                    }
                },
                {"bool": {"must_not": [{"exists": {"field": "attributes.k8s.pod.uid"}}]}},
            ]
        }
    }


def test_typed_values_and_numeric_ranges_are_enforced() -> None:
    fields = field_catalog()
    assert translate_expression(
        _expression({"op": "eq", "field": "attributes.process.pid", "value": 42}), fields
    ) == {"term": {"attributes.process.pid": 42}}
    assert translate_expression(
        _expression({"op": "eq", "field": "attributes.process.interactive", "value": False}), fields
    ) == {"term": {"attributes.process.interactive": False}}
    assert translate_expression(
        _expression(
            {
                "op": "range",
                "field": "metrics.service_graph.request.total",
                "gte": 10,
                "lt": 20.5,
            }
        ),
        fields,
    ) == {"range": {"metrics.service_graph.request.total": {"gte": 10, "lt": 20.5}}}

    invalid: tuple[dict[str, object], ...] = (
        {"op": "eq", "field": "attributes.process.pid", "value": "42"},
        {"op": "range", "field": "kind", "gte": 1},
        {"op": "regex", "field": "attributes.process.pid", "pattern": "4.*"},
        {"op": "exists", "field": "attributes.unknown"},
    )
    for document in invalid:
        with pytest.raises(QueryValidationError):
            translate_expression(_expression(document), fields)


def test_invalid_expression_structures_are_rejected_by_pydantic() -> None:
    invalid: tuple[dict[str, object], ...] = (
        {"op": "and", "operands": []},
        {"op": "in", "field": "kind", "values": []},
        {"op": "range", "field": "attributes.process.pid"},
        {"op": "unknown", "field": "kind"},
    )
    for document in invalid:
        with pytest.raises(ValidationError):
            _expression(document)


def test_execute_search_collects_all_pit_pages_and_closes_latest_pit() -> None:
    client = FakeQueryClient(
        (
            {
                "pit_id": "pit-2",
                "hits": {
                    "hits": [
                        {"_source": {"id": "a", "kind": "node"}, "sort": [1]},
                        {"_source": {"id": "b", "kind": "node"}, "sort": [2]},
                    ]
                },
            },
            {
                "pit_id": "pit-3",
                "hits": {"hits": [{"_source": {"id": "c", "kind": "node"}, "sort": [3]}]},
            },
            {"pit_id": "pit-4", "hits": {"hits": []}},
        )
    )

    result = execute_search(
        cast(QueryClient, client),
        ApiSettings(elasticsearch_page_size=2),
        _expression({"op": "eq", "field": "kind", "value": "node"}),
    )

    assert result.total == 3
    assert [element["id"] for element in result.elements] == ["a", "b", "c"]
    assert [call["search_after"] for call in client.search_calls] == [None, (2,), (3,)]
    assert [cast(Mapping[str, object], call["pit"])["id"] for call in client.search_calls] == [
        "pit-1",
        "pit-2",
        "pit-3",
    ]
    assert client.closed_pits == ["pit-4"]


def test_execute_search_closes_pit_when_search_fails() -> None:
    client = FakeQueryClient((RuntimeError("search failed"),))

    with pytest.raises(RuntimeError, match="search failed"):
        execute_search(
            cast(QueryClient, client),
            ApiSettings(),
            _expression({"op": "exists", "field": "id"}),
        )

    assert client.closed_pits == ["pit-1"]


def test_http_api_returns_results_and_maps_validation_and_readiness() -> None:
    client = FakeQueryClient(({"hits": {"hits": []}},))
    app = create_app(ApiSettings(), cast(QueryClient, client))
    http = TestClient(app)

    assert http.get("/health/live").json() == {"status": "live"}
    assert http.get("/health/ready").status_code == 200
    response = http.post(
        "/api/v1/elements/search",
        json={"pattern": {"op": "exists", "field": "id"}},
    )
    assert response.status_code == 200
    assert response.json() == {"total": 0, "elements": []}

    unknown = http.post(
        "/api/v1/elements/search",
        json={"pattern": {"op": "eq", "field": "unknown", "value": "value"}},
    )
    assert unknown.status_code == 400
    structurally_invalid = http.post(
        "/api/v1/elements/search",
        json={"pattern": {"op": "and", "operands": []}},
    )
    assert structurally_invalid.status_code == 422

    client.ping_result = False
    assert http.get("/health/ready").status_code == 503
