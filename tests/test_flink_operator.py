from __future__ import annotations

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
from extended_otel_semconv.services.interaction_diff.flink_job import (
    OnTimerProcessContext,
    ProcessContext,
    _InteractionDiffProcess,  # pyright: ignore[reportPrivateUsage]
)
from extended_otel_semconv.services.interaction_diff.runner import ParsedObservation


class FakeValueState[T]:
    def __init__(self) -> None:
        self.serialized: T | None = None

    def value(self) -> T | None:
        return self.serialized

    def update(self, value: T) -> None:
        self.serialized = value

    def clear(self) -> None:
        self.serialized = None


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
    assert state.serialized is None
    assert processing_timer.serialized is None
    assert timers.deleted_processing == [15_000, 16_000]


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
    assert state.serialized is None
    assert processing_timer.serialized is None
    assert timers.deleted_event == [6_001]


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
