# Framework operators are intentionally exercised through their private state seams.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import logging
from typing import cast

import pytest

pytest.importorskip("pyflink")

from pyflink.datastream.functions import KeyedProcessFunction, TimeDomain
from pyflink.datastream.state import ValueState

from extended_otel_servicegraph_engine.elements import (
    GraphContributionRetract,
    GraphContributionUpsert,
    GraphElementAggregateState,
    GraphElementUpsertEvent,
)
from extended_otel_servicegraph_engine.interaction import InteractionState
from extended_otel_servicegraph_engine.metrics import SERVICE_GRAPH_REQUEST_TOTAL
from extended_otel_servicegraph_ingest.interaction import observation_from_servicegraph_datapoint
from otel_servicegraph_diff.flink_job import (
    Counter,
    OnTimerProcessContext,
    ProcessContext,
    _GraphElementAggregateProcess,
    _InteractionContributionProcess,
    _PayloadParser,
)
from otel_servicegraph_diff.runner import ParsedObservation


class FakeValueState[T]:
    def __init__(self) -> None:
        self.serialized: T | None = None

    def value(self) -> T | None:
        return self.serialized

    def update(self, value: T) -> None:
        self.serialized = value

    def clear(self) -> None:
        self.serialized = None


class FakeCounter:
    def __init__(self) -> None:
        self.value = 0

    def inc(self, n: int = 1) -> None:
        self.value += n


class FakeTimerService:
    def __init__(self, watermark: int = 0, processing_time: int = 10_000) -> None:
        self.watermark = watermark
        self.processing_time = processing_time
        self.registered_event: list[int] = []
        self.deleted_event: list[int] = []
        self.registered_processing: list[int] = []
        self.deleted_processing: list[int] = []

    def current_processing_time(self) -> int:
        return self.processing_time

    def current_watermark(self) -> int:
        return self.watermark

    def register_event_time_timer(self, timestamp: int) -> None:
        self.registered_event.append(timestamp)

    def delete_event_time_timer(self, timestamp: int) -> None:
        self.deleted_event.append(timestamp)

    def register_processing_time_timer(self, timestamp: int) -> None:
        self.registered_processing.append(timestamp)

    def delete_processing_time_timer(self, timestamp: int) -> None:
        self.deleted_processing.append(timestamp)


class FakeProcessContext:
    def __init__(self, timer_service: FakeTimerService) -> None:
        self._timer_service = timer_service

    def timer_service(self) -> FakeTimerService:
        return self._timer_service


class FakeOnTimerContext(FakeProcessContext):
    def __init__(self, timer_service: FakeTimerService, time_domain: TimeDomain) -> None:
        super().__init__(timer_service)
        self._time_domain = time_domain

    def time_domain(self) -> TimeDomain:
        return self._time_domain


def test_interaction_operator_replaces_timers_and_retracts_every_element() -> None:
    state = FakeValueState[str]()
    processing_timer = FakeValueState[int]()
    timers = FakeTimerService()
    operator = _interaction_operator(state, processing_timer)
    context = _process_context(timers)

    upserts = tuple(operator.process_element(_parsed(1, 1_000_000_001), context))

    assert len(upserts) == 3
    assert all(isinstance(item, GraphContributionUpsert) for item in upserts)
    assert timers.registered_event == [6_001]
    assert timers.registered_processing == [15_000]
    assert state.serialized is not None
    assert InteractionState.model_validate_json(state.serialized).last_seen_unix_nano == 1_000_000_001

    timers.processing_time = 11_000
    tuple(operator.process_element(_parsed(2, 2_000_000_001), context))
    assert timers.deleted_event == [6_001]
    assert timers.deleted_processing == [15_000]
    assert timers.registered_event == [6_001, 7_001]

    retractions = tuple(operator.on_timer(7_001, _timer_context(timers, TimeDomain.EVENT_TIME)))
    assert len(retractions) == 3
    assert all(isinstance(item, GraphContributionRetract) for item in retractions)
    assert state.serialized is not None
    assert not InteractionState.model_validate_json(state.serialized).active
    assert processing_timer.serialized is None


def test_processing_timer_expires_when_event_time_is_idle() -> None:
    state = FakeValueState[str]()
    processing_timer = FakeValueState[int]()
    timers = FakeTimerService(processing_time=20_000)
    operator = _interaction_operator(state, processing_timer)
    tuple(operator.process_element(_parsed(1, 1_000_000_001), _process_context(timers)))

    retractions = tuple(operator.on_timer(25_000, _timer_context(timers, TimeDomain.PROCESSING_TIME)))

    assert len(retractions) == 3
    assert timers.deleted_event == [6_001]
    assert processing_timer.serialized is None


def test_stale_timer_and_empty_state_emit_nothing() -> None:
    state = FakeValueState[str]()
    timer_state = FakeValueState[int]()
    timers = FakeTimerService(processing_time=20_000)
    operator = _interaction_operator(state, timer_state)
    context = _timer_context(timers, TimeDomain.PROCESSING_TIME)

    assert tuple(operator.on_timer(25_000, context)) == ()
    tuple(operator.process_element(_parsed(1, 1_000_000_001), _process_context(timers)))
    timer_state.update(30_000)
    assert tuple(operator.on_timer(29_000, context)) == ()


def test_graph_element_operator_persists_and_clears_aggregate_state() -> None:
    state = FakeValueState[str]()
    operator = _GraphElementAggregateProcess(state_ttl_seconds=60)
    operator._state = cast(ValueState[str], state)
    contribution = next(
        item
        for item in _interaction_contributions()
        if isinstance(item, GraphContributionUpsert) and item.element.kind == "node"
    )

    events = tuple(operator.process_element(contribution, cast(KeyedProcessFunction.Context, object())))

    assert len(events) == 1
    assert isinstance(events[0], GraphElementUpsertEvent)
    assert state.serialized is not None
    aggregate = GraphElementAggregateState.model_validate_json(state.serialized)
    assert aggregate.element_id == contribution.element_id

    retract = GraphContributionRetract(
        element_id=contribution.element_id,
        contributor_id=contribution.contributor_id,
        observed_at_unix_nano=2_000_000_000,
    )
    deleted = tuple(operator.process_element(retract, cast(KeyedProcessFunction.Context, object())))
    assert deleted[0].operation == "delete"
    assert state.serialized is None


def test_payload_parser_counts_warns_and_discards_rejected_records(caplog: pytest.LogCaptureFixture) -> None:
    parser = _PayloadParser()
    counter = FakeCounter()
    parser._rejected_records = cast(Counter, counter)

    with caplog.at_level(logging.WARNING):
        assert tuple(parser.flat_map("{not-json")) == ()

    assert counter.value == 1
    assert "discarding rejected servicegraph record" in caplog.text


def test_operators_require_runtime_initialization() -> None:
    interaction = _InteractionContributionProcess(ttl_seconds=5, state_ttl_seconds=60)
    aggregate = _GraphElementAggregateProcess(state_ttl_seconds=60)

    with pytest.raises(RuntimeError, match="state accessed before operator initialization"):
        interaction._require_state()
    with pytest.raises(RuntimeError, match="processing timer state accessed before operator initialization"):
        interaction._require_processing_timer()
    with pytest.raises(RuntimeError, match="graph element state accessed before operator initialization"):
        aggregate._require_state()


def _interaction_operator(
    state: FakeValueState[str],
    timer: FakeValueState[int],
) -> _InteractionContributionProcess:
    operator = _InteractionContributionProcess(ttl_seconds=5, state_ttl_seconds=60)
    operator._state = cast(ValueState[str], state)
    operator._processing_timer = cast(ValueState[int], timer)
    return operator


def _process_context(timers: FakeTimerService) -> KeyedProcessFunction.Context:
    return cast(KeyedProcessFunction.Context, cast(ProcessContext, FakeProcessContext(timers)))


def _timer_context(timers: FakeTimerService, domain: TimeDomain) -> KeyedProcessFunction.OnTimerContext:
    return cast(
        KeyedProcessFunction.OnTimerContext,
        cast(OnTimerProcessContext, FakeOnTimerContext(timers, domain)),
    )


def _parsed(value: int, observed_at: int) -> ParsedObservation:
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {"client": "frontend", "server": "checkout-api"},
        value,
        observed_at,
        temporality="delta",
        start_time_unix_nano=1,
    )
    assert observation is not None
    return ParsedObservation(observation=observation)


def _interaction_contributions():
    state = FakeValueState[str]()
    timer = FakeValueState[int]()
    operator = _interaction_operator(state, timer)
    return tuple(operator.process_element(_parsed(1, 1_000_000_001), _process_context(FakeTimerService())))
