from __future__ import annotations

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from extended_otel_semconv.graph.interaction import (
    InteractionMetric,
    InteractionPayload,
    InteractionState,
    TelemetryScalar,
    apply_observation,
    build_interaction_id,
    expire_state,
    observation_from_servicegraph_datapoint,
)
from extended_otel_semconv.graph.metrics import SERVICE_GRAPH_REQUEST_FAILED_TOTAL, SERVICE_GRAPH_REQUEST_TOTAL
from otel_servicegraph_diff.runner import RejectedRecord, iter_parsed_payloads


def test_servicegraph_datapoint_parses_into_interaction_observation() -> None:
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {
            "client": "frontend",
            "server": "checkout-api",
            "connection_type": "http",
            "server_service.namespace": "payments",
            "server_http.request.method": "POST",
            "server_http.route": "/checkout/{cart_id}",
        },
        7,
        1_784_215_260_000_000_000,
    )

    assert observation is not None
    assert observation.client.service == "frontend"
    assert observation.server.service == "checkout-api"
    assert observation.connection_type == "calls"
    assert observation.metric_name == SERVICE_GRAPH_REQUEST_TOTAL
    assert observation.dimensions["server_http.route"] == "/checkout/{cart_id}"
    assert {node.id for node in observation.graph.nodes} >= {
        "service:frontend",
        "service:checkout-api",
        "service.namespace:payments",
        "app.endpoint:checkout-api:payments:POST:%2Fcheckout%2F%7Bcart_id%7D",
    }
    assert {
        (edge.source, edge.target, edge.type)
        for edge in observation.graph.edges
    } >= {
        ("service:frontend", "service:checkout-api", "calls"),
        (
            "service:checkout-api",
            "app.endpoint:checkout-api:payments:POST:%2Fcheckout%2F%7Bcart_id%7D",
            "exposes",
        ),
    }


def test_metric_name_does_not_change_interaction_identity() -> None:
    attributes = {"client": "frontend", "server": "checkout-api", "connection_type": "http"}
    request_total = observation_from_servicegraph_datapoint(SERVICE_GRAPH_REQUEST_TOTAL, attributes, 10, 100)
    failed_total = observation_from_servicegraph_datapoint(SERVICE_GRAPH_REQUEST_FAILED_TOTAL, attributes, 1, 100)

    assert request_total is not None
    assert failed_total is not None
    assert request_total.interaction_id == failed_total.interaction_id


def test_state_emits_only_on_semantic_change_and_delete_on_expiry() -> None:
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {"client": "frontend", "server": "checkout-api", "connection_type": "http"},
        10,
        1_000_000_000,
    )
    assert observation is not None

    first = apply_observation(None, observation, ttl_seconds=5, emitted_at_unix_ms=100)
    second = apply_observation(first.state, observation, ttl_seconds=5, emitted_at_unix_ms=101)
    changed_observation = observation.model_copy(
        update={
            "metric": observation.metric.model_copy(update={"value": 11}),
            "observed_at_unix_nano": 2_000_000_000,
        }
    )
    changed = apply_observation(second.state, changed_observation, ttl_seconds=5, emitted_at_unix_ms=102)

    assert first.event is not None
    assert first.event.operation == "upsert"
    assert first.event.schema_version == "1.1"
    assert first.event.interaction.graph == first.state.graph
    assert second.event is None
    assert changed.event is not None
    assert changed.event.operation == "upsert"
    assert isinstance(changed.event.interaction, InteractionPayload)

    too_early = expire_state(changed.state, 6_000_000_000, emitted_at_unix_ms=103)
    expired = expire_state(changed.state, 7_000_000_000, emitted_at_unix_ms=104)

    assert too_early is None
    assert expired is not None
    assert expired.operation == "delete"
    assert expired.interaction is None


def test_unchanged_cumulative_observation_does_not_reactivate_deleted_state() -> None:
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {"client": "frontend", "server": "checkout-api"},
        1,
        1_000_000_000,
    )
    assert observation is not None

    first = apply_observation(None, observation, ttl_seconds=1, emitted_at_unix_ms=100)
    deleted = expire_state(first.state, 2_000_000_000, emitted_at_unix_ms=101)
    tombstone = first.state.model_copy(update={"active": False})
    repeated = apply_observation(tombstone, observation, ttl_seconds=1, emitted_at_unix_ms=102)
    advanced_observation = observation.model_copy(
        update={
            "metric": observation.metric.model_copy(update={"value": 2}),
            "observed_at_unix_nano": 3_000_000_000,
        }
    )
    reactivated = apply_observation(tombstone, advanced_observation, ttl_seconds=1, emitted_at_unix_ms=103)

    assert deleted is not None
    assert deleted.operation == "delete"
    assert repeated.event is None
    assert not repeated.state.active
    assert reactivated.event is not None
    assert reactivated.event.operation == "upsert"
    assert reactivated.state.active
    assert reactivated.state.interaction_id == first.state.interaction_id


def test_bad_payload_becomes_rejected_record() -> None:
    events = tuple(iter_parsed_payloads("{not-json"))

    assert len(events) == 1
    assert isinstance(events[0], RejectedRecord)
    assert events[0].rejection.event_type == "interaction_record_rejected"


def test_unsupported_service_graph_metric_is_ignored() -> None:
    payload = json.dumps(
        {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {"name": "traces_service_graph_request_duration_seconds"},
                            ]
                        }
                    ]
                }
            ]
        }
    )

    assert tuple(iter_parsed_payloads(payload)) == ()


def test_repeated_cumulative_sample_does_not_refresh_expiry() -> None:
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {"client": "frontend", "server": "checkout-api"},
        10,
        1_000_000_000,
        start_time_unix_nano=100,
    )
    assert observation is not None
    first = apply_observation(None, observation, ttl_seconds=5, emitted_at_unix_ms=100)
    repeated = observation.model_copy(update={"observed_at_unix_nano": 4_000_000_000})

    result = apply_observation(first.state, repeated, ttl_seconds=5, emitted_at_unix_ms=101)

    assert result.event is None
    assert result.state.expires_at_unix_nano == 6_000_000_000
    assert result.state.last_seen_unix_nano == 1_000_000_000


def test_interaction_state_json_round_trip_is_strict() -> None:
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {"client": "frontend", "server": "checkout-api"},
        1,
        1_000_000_000,
    )
    assert observation is not None
    state = apply_observation(None, observation, emitted_at_unix_ms=100).state

    assert InteractionState.model_validate_json(state.model_dump_json()) == state


def test_checkpoint_recovery_does_not_duplicate_unchanged_transition() -> None:
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {"client": "frontend", "server": "checkout-api"},
        1,
        1_000_000_000,
    )
    assert observation is not None
    before_restart = apply_observation(None, observation, emitted_at_unix_ms=100)
    restored = InteractionState.model_validate_json(before_restart.state.model_dump_json())

    after_restart = apply_observation(restored, observation, emitted_at_unix_ms=101)

    assert after_restart.event is None
    assert after_restart.state == restored


def test_expiry_waits_until_fractional_millisecond_has_elapsed() -> None:
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {"client": "frontend", "server": "checkout-api"},
        1,
        1_000_000_001,
    )
    assert observation is not None
    state = apply_observation(
        None,
        observation,
        ttl_seconds=5,
        emitted_at_unix_ms=100,
    ).state

    assert expire_state(state, 6_000_000_000, emitted_at_unix_ms=101) is None
    assert expire_state(state, 6_001_000_000, emitted_at_unix_ms=101) is not None


def test_cumulative_counter_reset_is_activity() -> None:
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {"client": "frontend", "server": "checkout-api"},
        10,
        1_000_000_000,
        start_time_unix_nano=100,
    )
    assert observation is not None
    first = apply_observation(None, observation, emitted_at_unix_ms=100)
    reset = observation.model_copy(
        update={
            "metric": InteractionMetric(value=1, temporality="cumulative", start_time_unix_nano=200),
            "observed_at_unix_nano": 2_000_000_000,
        }
    )

    result = apply_observation(first.state, reset, emitted_at_unix_ms=101)

    assert result.event is not None
    assert result.state.metrics_by_name[SERVICE_GRAPH_REQUEST_TOTAL].value == 1


def test_late_recreated_observation_expires_from_watermark() -> None:
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {"client": "frontend", "server": "checkout-api"},
        1,
        1_000_000_000,
    )
    assert observation is not None

    result = apply_observation(
        None,
        observation,
        ttl_seconds=5,
        expiry_base_unix_nano=10_000_000_000,
        emitted_at_unix_ms=100,
    )

    assert result.state.expires_at_unix_nano == 15_000_000_000


def test_missing_timestamp_is_rejected() -> None:
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {"client": "frontend", "server": "checkout-api"},
        1,
        None,
    )

    assert observation is None


def test_domain_models_are_immutable() -> None:
    metric = InteractionMetric(value=1, temporality="cumulative")

    with pytest.raises(ValidationError):
        metric.value = 2


@settings(max_examples=50)
@given(st.text())
def test_arbitrary_external_text_never_escapes_the_parse_boundary(payload: str) -> None:
    results = tuple(iter_parsed_payloads(payload))

    assert results


@given(
    st.dictionaries(
        st.text(min_size=1),
        st.one_of(st.text(), st.integers(), st.booleans()),
        min_size=1,
        max_size=20,
    )
)
def test_interaction_id_is_stable_across_attribute_order(dimensions: dict[str, TelemetryScalar]) -> None:
    left = build_interaction_id("client", "server", "calls", dimensions)
    right = build_interaction_id("client", "server", "calls", dict(reversed(list(dimensions.items()))))

    assert left == right


@given(
    dimensions=st.dictionaries(st.text(min_size=1), st.text(), min_size=1, max_size=20),
    key=st.text(min_size=1),
    value=st.text(min_size=1),
)
def test_dimension_mutation_changes_interaction_id(dimensions: dict[str, str], key: str, value: str) -> None:
    mutated = dict(dimensions)
    mutated[key] = value
    if mutated == dimensions:
        return

    assert build_interaction_id("client", "server", "calls", dimensions) != build_interaction_id(
        "client", "server", "calls", mutated
    )
