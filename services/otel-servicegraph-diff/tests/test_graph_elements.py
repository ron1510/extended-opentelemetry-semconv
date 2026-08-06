from __future__ import annotations

from pydantic import TypeAdapter

from extended_otel_semconv.graph.elements import (
    GRAPH_REQUEST_FAILED_TOTAL,
    GRAPH_REQUEST_TOTAL,
    GraphContributionRetract,
    GraphContributionUpsert,
    GraphEdge,
    GraphElementEvent,
    GraphElementUpsertEvent,
    GraphNode,
    apply_contribution,
    edge_id,
)
from extended_otel_semconv.graph.interaction import (
    InteractionState,
    apply_observation,
    build_interaction_id,
    contributions_for_transition,
    observation_from_servicegraph_datapoint,
    retract_contributions,
    state_has_expired,
)
from extended_otel_semconv.graph.metrics import SERVICE_GRAPH_REQUEST_TOTAL


def test_node_contributors_complete_each_others_optional_attributes() -> None:
    first = apply_contribution(None, _node_upsert("a", 10, {"zone": "eu-1"}), emitted_at_unix_ms=100)
    second = apply_contribution(
        first.state,
        _node_upsert("b", 20, {"version": "2.4"}),
        emitted_at_unix_ms=101,
    )

    assert isinstance(second.event, GraphElementUpsertEvent)
    assert isinstance(second.event.element, GraphNode)
    assert second.event.element.attributes == {"version": "2.4", "zone": "eu-1"}


def test_node_attribute_conflicts_use_timestamp_then_contributor_id() -> None:
    state = apply_contribution(None, _node_upsert("z", 10, {"version": "old"})).state
    state = apply_contribution(state, _node_upsert("z", 20, {"version": "new"})).state
    result = apply_contribution(state, _node_upsert("a", 20, {"version": "tie-winner"}))

    assert isinstance(result.event, GraphElementUpsertEvent)
    assert isinstance(result.event.element, GraphNode)
    assert result.event.element.attributes["version"] == "tie-winner"


def test_retraction_recomputes_attributes_and_final_retraction_deletes() -> None:
    first = apply_contribution(None, _node_upsert("a", 10, {"zone": "eu-1", "version": "1"}))
    second = apply_contribution(first.state, _node_upsert("b", 20, {"version": "2"}))

    fallback = apply_contribution(second.state, _retract("b", 30), emitted_at_unix_ms=103)
    assert isinstance(fallback.event, GraphElementUpsertEvent)
    assert isinstance(fallback.event.element, GraphNode)
    assert fallback.event.element.attributes == {"version": "1", "zone": "eu-1"}

    deleted = apply_contribution(fallback.state, _retract("a", 40), emitted_at_unix_ms=104)
    assert deleted.state is None
    assert deleted.event is not None
    assert deleted.event.operation == "delete"
    assert deleted.event.element is None


def test_unknown_retraction_and_unchanged_snapshot_emit_nothing() -> None:
    first = apply_contribution(None, _node_upsert("a", 10, {"zone": "eu-1"}))
    unchanged = apply_contribution(first.state, _node_upsert("a", 10, {"zone": "eu-1"}))
    unknown = apply_contribution(unchanged.state, _retract("missing", 20))

    assert unchanged.event is None
    assert unknown.event is None
    assert unknown.state == unchanged.state


def test_edge_metrics_accumulate_without_decreasing_on_partial_expiry() -> None:
    element_id = edge_id("service:a", "calls", "service:b")
    edge = GraphEdge(
        id=element_id,
        type="calls",
        source_id="service:a",
        target_id="service:b",
    )
    first = apply_contribution(None, _edge_upsert(edge, "a", 10, requests=3, failures=1))
    second = apply_contribution(first.state, _edge_upsert(edge, "b", 20, requests=5, failures=0))

    assert second.state is not None
    assert second.state.metrics == {
        GRAPH_REQUEST_FAILED_TOTAL: 1,
        GRAPH_REQUEST_TOTAL: 8,
    }
    partial = apply_contribution(second.state, _edge_retract(edge, "a", 30))
    assert partial.state is not None
    assert partial.state.metrics == second.state.metrics
    assert partial.event is None


def test_edge_delete_and_recreation_reset_metric_lifetime() -> None:
    element_id = edge_id("service:a", "calls", "service:b")
    edge = GraphEdge(id=element_id, type="calls", source_id="service:a", target_id="service:b")
    active = apply_contribution(None, _edge_upsert(edge, "a", 10, requests=7))
    deleted = apply_contribution(active.state, _edge_retract(edge, "a", 20))
    recreated = apply_contribution(deleted.state, _edge_upsert(edge, "b", 30, requests=2))

    assert recreated.state is not None
    assert recreated.state.metrics == {GRAPH_REQUEST_TOTAL: 2}


def test_event_contract_round_trips_as_discriminated_union() -> None:
    result = apply_contribution(None, _node_upsert("a", 10, {"zone": "eu-1"}), emitted_at_unix_ms=100)
    assert result.event is not None

    adapter: TypeAdapter[GraphElementEvent] = TypeAdapter(GraphElementEvent)
    restored = adapter.validate_json(result.event.model_dump_json())

    assert restored == result.event
    assert restored.schema_version == "2.0"
    assert restored.event_type == "graph_element_state_changed"
    assert restored.element_id == "k8s.pod:pod-1"


def test_interaction_transition_extracts_nodes_edges_and_only_metric_deltas() -> None:
    observation = _observation(
        value=3,
        observed_at=1_000_000_000,
        attributes={
            "client": "frontend",
            "server": "checkout",
            "client_service.version": "1.0",
            "server_service.version": "2.0",
            "server_http.route": "/orders/{id}",
            "server_http.request.method": "GET",
        },
    )
    result = apply_observation(None, observation, ttl_seconds=5)
    contributions = contributions_for_transition(None, result.state, observation)

    assert result.changed
    assert any(
        isinstance(item, GraphContributionUpsert)
        and isinstance(item.element, GraphNode)
        and item.element.id == "service:frontend"
        for item in contributions
    )
    dependency = next(
        item
        for item in contributions
        if isinstance(item, GraphContributionUpsert)
        and isinstance(item.element, GraphEdge)
        and item.element.source_id == "service:frontend"
        and item.element.target_id == "service:checkout"
    )
    assert dependency.element.attributes == {}
    assert dependency.metric_deltas == {GRAPH_REQUEST_TOTAL: 3}


def test_interaction_expiry_retracts_every_current_element() -> None:
    observation = _observation(value=1, observed_at=1_000_000_000)
    state = apply_observation(None, observation, ttl_seconds=5).state

    retractions = retract_contributions(state)

    assert retractions
    assert {item.element_id for item in retractions} == {
        item.element_id for item in contributions_for_transition(None, state, observation)
    }
    assert not state_has_expired(state, 5_999_999_999)
    assert state_has_expired(state, 6_000_000_000)


def test_interaction_state_rejects_late_and_repeated_cumulative_samples() -> None:
    first_observation = _observation(value=10, observed_at=2_000_000_000)
    first = apply_observation(None, first_observation)
    repeated = apply_observation(first.state, _observation(value=10, observed_at=3_000_000_000))
    late = apply_observation(first.state, _observation(value=11, observed_at=1_000_000_000))

    assert not repeated.changed
    assert repeated.state == first.state
    assert not late.changed
    assert late.state == first.state
    assert InteractionState.model_validate_json(first.state.model_dump_json()) == first.state


def test_interaction_identity_is_stable_across_dimension_order() -> None:
    left = build_interaction_id("a", "b", "calls", {"route": "/x", "status": 200})
    right = build_interaction_id("a", "b", "calls", {"status": 200, "route": "/x"})

    assert left == right


def _node_upsert(contributor: str, observed_at: int, attributes: dict[str, object]) -> GraphContributionUpsert:
    node = GraphNode(id="k8s.pod:pod-1", type="k8s.pod", attributes=attributes)
    return GraphContributionUpsert(
        element_id=node.id,
        contributor_id=contributor,
        observed_at_unix_nano=observed_at,
        element=node,
    )


def _retract(contributor: str, observed_at: int) -> GraphContributionRetract:
    return GraphContributionRetract(
        element_id="k8s.pod:pod-1",
        contributor_id=contributor,
        observed_at_unix_nano=observed_at,
    )


def _edge_upsert(
    edge: GraphEdge,
    contributor: str,
    observed_at: int,
    *,
    requests: int,
    failures: int | None = None,
) -> GraphContributionUpsert:
    deltas: dict[str, int | float] = {GRAPH_REQUEST_TOTAL: requests}
    if failures is not None:
        deltas[GRAPH_REQUEST_FAILED_TOTAL] = failures
    return GraphContributionUpsert(
        element_id=edge.id,
        contributor_id=contributor,
        observed_at_unix_nano=observed_at,
        element=edge,
        metric_deltas=deltas,
    )


def _edge_retract(edge: GraphEdge, contributor: str, observed_at: int) -> GraphContributionRetract:
    return GraphContributionRetract(
        element_id=edge.id,
        contributor_id=contributor,
        observed_at_unix_nano=observed_at,
    )


def _observation(
    *,
    value: int,
    observed_at: int,
    attributes: dict[str, str | int | bool] | None = None,
):
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        attributes or {"client": "frontend", "server": "checkout"},
        value,
        observed_at,
        start_time_unix_nano=1,
    )
    assert observation is not None
    return observation
