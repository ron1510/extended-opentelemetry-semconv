from __future__ import annotations

import logging
from typing import cast

import pytest

pytest.importorskip("pyflink")

from pyflink.datastream.functions import KeyedProcessFunction, TimeDomain
from pyflink.datastream.state import ValueState

from extended_otel_semconv.graph.interaction import (
    InteractionDeleteEvent,
    InteractionState,
    InteractionUpsertEvent,
    observation_from_servicegraph_datapoint,
)
from extended_otel_semconv.graph.metrics import SERVICE_GRAPH_REQUEST_TOTAL
from otel_servicegraph_diff.flink_job import (
    Counter,
    OnTimerProcessContext,
    ProcessContext,
    _InteractionDiffProcess,  # pyright: ignore[reportPrivateUsage]
    _PayloadParser,  # pyright: ignore[reportPrivateUsage]
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


def test_operator_replaces_timer_and_emits_delete() -> None:
    state = FakeValueState[str]()
    processing_timer = FakeValueState[int]()
    timers = FakeTimerService()
    context = FakeProcessContext(timers)
    operator = _InteractionDiffProcess(ttl_seconds=5, state_ttl_seconds=60)
    operator._state = cast(ValueState[str], state)  # pyright: ignore[reportPrivateUsage]
    operator._processing_timer = cast(ValueState[int], processing_timer)  # pyright: ignore[reportPrivateUsage]
    first = _parsed_observation(value=1, observed_at_unix_nano=1_000_000_001)

    upserts = tuple(
        operator.process_element(
            first,
            cast(KeyedProcessFunction.Context, cast(ProcessContext, context)),
        )
    )

    assert len(upserts) == 1
    assert isinstance(upserts[0], InteractionUpsertEvent)
    assert timers.registered_event == [6_001]
    assert timers.registered_processing == [15_000]
    assert state.serialized is not None
    assert InteractionState.model_validate_json(state.serialized).last_seen_unix_nano == 1_000_000_001

    second = _parsed_observation(value=2, observed_at_unix_nano=2_000_000_001)
    timers.processing_time = 11_000
    tuple(
        operator.process_element(
            second,
            cast(KeyedProcessFunction.Context, cast(ProcessContext, context)),
        )
    )

    assert timers.deleted_event == [6_001]
    assert timers.deleted_processing == [15_000]
    assert timers.registered_event == [6_001, 7_001]
    assert timers.registered_processing == [15_000, 16_000]

    on_timer_context = FakeOnTimerContext(timers, TimeDomain.EVENT_TIME)
    deletes = tuple(
        operator.on_timer(
            7_001,
            cast(KeyedProcessFunction.OnTimerContext, cast(OnTimerProcessContext, on_timer_context)),
        )
    )

    assert len(deletes) == 1
    assert isinstance(deletes[0], InteractionDeleteEvent)
    assert state.serialized is not None
    assert not InteractionState.model_validate_json(state.serialized).active
    assert processing_timer.serialized is None
    assert timers.deleted_processing == [15_000, 16_000]

    repeated = tuple(
        operator.process_element(
            second,
            cast(KeyedProcessFunction.Context, cast(ProcessContext, context)),
        )
    )

    assert repeated == ()
    assert state.serialized is not None
    assert not InteractionState.model_validate_json(state.serialized).active
    assert timers.registered_event == [6_001, 7_001]
    assert timers.registered_processing == [15_000, 16_000]


def test_operator_processing_timer_deletes_when_event_time_is_idle() -> None:
    state = FakeValueState[str]()
    processing_timer = FakeValueState[int]()
    timers = FakeTimerService(processing_time=20_000)
    context = FakeProcessContext(timers)
    operator = _InteractionDiffProcess(ttl_seconds=5, state_ttl_seconds=60)
    operator._state = cast(ValueState[str], state)  # pyright: ignore[reportPrivateUsage]
    operator._processing_timer = cast(ValueState[int], processing_timer)  # pyright: ignore[reportPrivateUsage]

    tuple(
        operator.process_element(
            _parsed_observation(value=1, observed_at_unix_nano=1_000_000_001),
            cast(KeyedProcessFunction.Context, cast(ProcessContext, context)),
        )
    )

    on_timer_context = FakeOnTimerContext(timers, TimeDomain.PROCESSING_TIME)
    deletes = tuple(
        operator.on_timer(
            25_000,
            cast(KeyedProcessFunction.OnTimerContext, cast(OnTimerProcessContext, on_timer_context)),
        )
    )

    assert len(deletes) == 1
    assert isinstance(deletes[0], InteractionDeleteEvent)
    assert state.serialized is not None
    assert not InteractionState.model_validate_json(state.serialized).active
    assert processing_timer.serialized is None
    assert timers.deleted_event == [6_001]


def test_payload_parser_counts_warns_and_discards_rejected_records(caplog: pytest.LogCaptureFixture) -> None:
    parser = _PayloadParser()
    counter = FakeCounter()
    parser._rejected_records = cast(Counter, counter)  # pyright: ignore[reportPrivateUsage]

    with caplog.at_level(logging.WARNING):
        assert tuple(parser.flat_map("{not-json")) == ()

    assert counter.value == 1
    assert "discarding rejected servicegraph record" in caplog.text


def test_operator_ignores_stale_processing_timer_and_empty_state() -> None:
    state = FakeValueState[str]()
    processing_timer = FakeValueState[int]()
    timers = FakeTimerService(processing_time=20_000)
    operator = _InteractionDiffProcess(ttl_seconds=5, state_ttl_seconds=60)
    operator._state = cast(ValueState[str], state)  # pyright: ignore[reportPrivateUsage]
    operator._processing_timer = cast(ValueState[int], processing_timer)  # pyright: ignore[reportPrivateUsage]
    context = FakeOnTimerContext(timers, TimeDomain.PROCESSING_TIME)

    assert tuple(
        operator.on_timer(
            25_000,
            cast(KeyedProcessFunction.OnTimerContext, cast(OnTimerProcessContext, context)),
        )
    ) == ()

    process_context = FakeProcessContext(timers)
    tuple(
        operator.process_element(
            _parsed_observation(value=1, observed_at_unix_nano=1_000_000_001),
            cast(KeyedProcessFunction.Context, cast(ProcessContext, process_context)),
        )
    )
    processing_timer.update(30_000)

    assert tuple(
        operator.on_timer(
            29_000,
            cast(KeyedProcessFunction.OnTimerContext, cast(OnTimerProcessContext, context)),
        )
    ) == ()
    assert state.serialized is not None
    assert InteractionState.model_validate_json(state.serialized).active


def test_operator_requires_runtime_state_initialization() -> None:
    operator = _InteractionDiffProcess(ttl_seconds=5, state_ttl_seconds=60)

    with pytest.raises(RuntimeError, match="state accessed before operator initialization"):
        operator._require_state()  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(RuntimeError, match="processing timer state accessed before operator initialization"):
        operator._require_processing_timer()  # pyright: ignore[reportPrivateUsage]


def _parsed_observation(*, value: int, observed_at_unix_nano: int) -> ParsedObservation:
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {"client": "frontend", "server": "checkout-api"},
        value,
        observed_at_unix_nano,
        start_time_unix_nano=1,
    )
    assert observation is not None
    return ParsedObservation(observation=observation)
