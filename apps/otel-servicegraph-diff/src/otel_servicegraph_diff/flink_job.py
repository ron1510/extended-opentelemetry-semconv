"""PyFlink 2.2.1 wiring for the servicegraph interaction diff engine."""

# PyFlink's Python stubs erase DataStream element types and incorrectly declare
# generator-based function overrides as returning None. Keep that unsoundness
# contained in this adapter; domain and wire models remain strict.
# pyright: reportUnknownMemberType=false, reportUnknownLambdaType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportUnknownParameterType=false, reportIncompatibleMethodOverride=false

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, cast

from pyflink.common import Configuration, Duration, Row, Types, WatermarkStrategy
from pyflink.common.serialization import SerializationSchema, SimpleStringSchema
from pyflink.common.time import Time
from pyflink.common.watermark_strategy import TimestampAssigner
from pyflink.datastream import RuntimeExecutionMode, StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import (
    DeliveryGuarantee,
    KafkaOffsetResetStrategy,
    KafkaOffsetsInitializer,
    KafkaRecordSerializationSchema,
    KafkaSink,
    KafkaSource,
)
from pyflink.datastream.functions import FlatMapFunction, KeyedProcessFunction, RuntimeContext, TimeDomain
from pyflink.datastream.state import StateTtlConfig, ValueState, ValueStateDescriptor
from pyflink.java_gateway import get_gateway

from extended_otel_semconv.graph.interaction import (
    InteractionEvent,
    InteractionState,
    apply_observation,
    expire_state,
)
from otel_servicegraph_diff.config import InteractionDiffConfig
from otel_servicegraph_diff.runner import (
    ParsedObservation,
    ParsedPayload,
    RejectedRecord,
    dlq_record,
    event_record,
    iter_parsed_payloads,
)

OUTPUT_ROW_TYPE = Types.ROW_NAMED(["key", "value"], [Types.STRING(), Types.STRING()])


class TimerService(Protocol):
    def current_processing_time(self) -> int: ...
    def current_watermark(self) -> int: ...
    def register_processing_time_timer(self, timestamp: int) -> None: ...
    def register_event_time_timer(self, timestamp: int) -> None: ...
    def delete_processing_time_timer(self, timestamp: int) -> None: ...
    def delete_event_time_timer(self, timestamp: int) -> None: ...


class ProcessContext(Protocol):
    def timer_service(self) -> TimerService: ...


class OnTimerProcessContext(ProcessContext, Protocol):
    def time_domain(self) -> TimeDomain: ...


def run_flink_job(config: InteractionDiffConfig) -> None:
    flink_config = Configuration()
    flink_config.set_string("restart-strategy.type", "fixed-delay")
    flink_config.set_integer("restart-strategy.fixed-delay.attempts", config.restart_attempts)
    flink_config.set_string(
        "restart-strategy.fixed-delay.delay",
        f"{config.restart_delay_seconds} s",
    )
    env = StreamExecutionEnvironment.get_execution_environment(flink_config)
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)
    env.enable_checkpointing(config.checkpoint_interval_ms)

    source = _kafka_source(config)
    event_sink = _kafka_sink(config, config.output_topic)
    dlq_sink = _kafka_sink(config, config.dlq_topic)

    payloads = (
        env.from_source(source, WatermarkStrategy.no_watermarks(), "servicegraph-otlp-json")
        .name("servicegraph-kafka-source")
        .uid("servicegraph-kafka-source")
    )
    parsed = payloads.flat_map(_PayloadParser()).name("parse-otlp-servicegraph").uid("parse-otlp-servicegraph")

    rejected = (
        parsed.filter(lambda item: isinstance(item, RejectedRecord))
        .name("filter-rejected-records")
        .uid("filter-rejected-records")
    )
    rejected_rows = (
        rejected.map(_rejected_row, output_type=OUTPUT_ROW_TYPE)
        .name("serialize-rejected-records")
        .uid("serialize-rejected-records")
    )
    rejected_rows.sink_to(dlq_sink).name("interaction-dlq").uid("interaction-dlq")

    observations = (
        parsed.filter(lambda item: isinstance(item, ParsedObservation))
        .name("filter-interaction-observations")
        .uid("filter-interaction-observations")
        .assign_timestamps_and_watermarks(
            WatermarkStrategy.for_bounded_out_of_orderness(
                Duration.of_seconds(config.allowed_lateness_seconds)
            )
            .with_idleness(Duration.of_seconds(max(config.allowed_lateness_seconds * 2, 1)))
            .with_timestamp_assigner(_ObservationTimestampAssigner())
        )
        .name("interaction-watermarks")
        .uid("interaction-watermarks")
    )
    events = (
        observations.key_by(_interaction_key, key_type=Types.STRING())
        .process(_InteractionDiffProcess(config.interaction_ttl_seconds, config.state_ttl_seconds))
        .name("interaction-keyed-diff")
        .uid("interaction-keyed-diff")
    )
    event_rows = (
        events.map(_event_row, output_type=OUTPUT_ROW_TYPE)
        .name("serialize-interaction-events")
        .uid("serialize-interaction-events")
    )
    event_rows.sink_to(event_sink).name("interaction-events").uid("interaction-events")

    env.execute("servicegraph-interaction-diff")


def _kafka_source(config: InteractionDiffConfig) -> KafkaSource:
    builder = (
        KafkaSource.builder()
        .set_bootstrap_servers(config.bootstrap_servers)
        .set_topics(config.input_topic)
        .set_group_id(config.group_id)
        .set_starting_offsets(
            KafkaOffsetsInitializer.committed_offsets(KafkaOffsetResetStrategy.EARLIEST)
        )
        .set_property("commit.offsets.on.checkpoint", "true")
        .set_property("allow.auto.create.topics", "false")
    )
    for key, value in config.kafka_client_properties.items():
        builder.set_property(key, value)
    return builder.set_value_only_deserializer(SimpleStringSchema()).build()


def _kafka_sink(config: InteractionDiffConfig, topic: str) -> KafkaSink:
    jvm = get_gateway().jvm
    # Py4J resolves checked-in Java classes dynamically and exposes no callable
    # type metadata. Keep that unsound boundary to these two constructor calls.
    key_serializer = SerializationSchema(
        jvm.io.extendedotel.flink.FirstColumnStringSerializationSchema()  # pyright: ignore[reportCallIssue, reportOptionalCall, reportAttributeAccessIssue, reportOptionalMemberAccess]
    )
    value_serializer = SerializationSchema(
        jvm.io.extendedotel.flink.SecondColumnStringSerializationSchema()  # pyright: ignore[reportCallIssue, reportOptionalCall, reportAttributeAccessIssue, reportOptionalMemberAccess]
    )
    serializer = (
        KafkaRecordSerializationSchema.builder()
        .set_topic(topic)
        .set_key_serialization_schema(key_serializer)
        .set_value_serialization_schema(value_serializer)
        .build()
    )
    builder = (
        KafkaSink.builder()
        .set_bootstrap_servers(config.bootstrap_servers)
        .set_record_serializer(serializer)
        .set_delivery_guarantee(DeliveryGuarantee.AT_LEAST_ONCE)
    )
    builder.set_property("allow.auto.create.topics", "false")
    for key, value in config.kafka_client_properties.items():
        builder.set_property(key, value)
    return builder.build()


class _PayloadParser(FlatMapFunction):
    def flat_map(self, value: str) -> Iterable[ParsedPayload]:
        yield from iter_parsed_payloads(value)


class _InteractionDiffProcess(KeyedProcessFunction):
    def __init__(self, ttl_seconds: int, state_ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._state_ttl_seconds = state_ttl_seconds
        self._state: ValueState[str] | None = None
        self._processing_timer: ValueState[int] | None = None

    def open(self, runtime_context: RuntimeContext) -> None:
        descriptor = ValueStateDescriptor("interaction-state-v1", Types.STRING())
        ttl_config = (
            StateTtlConfig.new_builder(Time.seconds(self._state_ttl_seconds))
            .update_ttl_on_create_and_write()
            .never_return_expired()
            .cleanup_full_snapshot()
            .build()
        )
        descriptor.enable_time_to_live(ttl_config)
        self._state = runtime_context.get_state(descriptor)
        processing_timer_descriptor = ValueStateDescriptor("interaction-processing-expiry-v1", Types.LONG())
        processing_timer_descriptor.enable_time_to_live(ttl_config)
        self._processing_timer = runtime_context.get_state(processing_timer_descriptor)

    def process_element(
        self,
        value: ParsedPayload,
        ctx: KeyedProcessFunction.Context,
    ) -> Iterable[InteractionEvent]:
        if not isinstance(value, ParsedObservation):
            return ()
        state_handle = self._require_state()
        previous_json = state_handle.value()
        previous = InteractionState.model_validate_json(previous_json) if previous_json else None
        timer_service = cast(ProcessContext, ctx).timer_service()
        watermark_nano = max(timer_service.current_watermark(), 0) * 1_000_000
        result = apply_observation(
            previous,
            value.observation,
            ttl_seconds=self._ttl_seconds,
            expiry_base_unix_nano=watermark_nano,
        )
        if previous == result.state:
            return ()
        processing_timer_state = self._require_processing_timer()
        if previous is not None:
            timer_service.delete_event_time_timer(_timer_millis(previous.expires_at_unix_nano))
            previous_processing_timer = cast(int | None, processing_timer_state.value())
            if previous_processing_timer is not None:
                timer_service.delete_processing_time_timer(previous_processing_timer)
        state_handle.update(result.state.model_dump_json())
        timer_service.register_event_time_timer(_timer_millis(result.state.expires_at_unix_nano))
        processing_expiry = timer_service.current_processing_time() + self._ttl_seconds * 1_000
        processing_timer_state.update(processing_expiry)
        timer_service.register_processing_time_timer(processing_expiry)
        return (result.event,) if result.event is not None else ()

    def on_timer(
        self,
        timestamp: int,
        ctx: KeyedProcessFunction.OnTimerContext,
    ) -> Iterable[InteractionEvent]:
        state_handle = self._require_state()
        state_json = state_handle.value()
        if not state_json:
            return ()
        state = InteractionState.model_validate_json(state_json)
        timer_service = cast(ProcessContext, ctx).timer_service()
        processing_timer_state = self._require_processing_timer()
        time_domain = cast(OnTimerProcessContext, ctx).time_domain()
        if time_domain is TimeDomain.PROCESSING_TIME:
            if processing_timer_state.value() != timestamp:
                return ()
            event = expire_state(state, state.expires_at_unix_nano)
            timer_service.delete_event_time_timer(_timer_millis(state.expires_at_unix_nano))
        else:
            event = expire_state(state, timestamp * 1_000_000)
        if event is None:
            return ()
        processing_timer = cast(int | None, processing_timer_state.value())
        if processing_timer is not None and time_domain is TimeDomain.EVENT_TIME:
            timer_service.delete_processing_time_timer(processing_timer)
        processing_timer_state.clear()
        state_handle.clear()
        return (event,)

    def _require_state(self) -> ValueState[str]:
        if self._state is None:
            raise RuntimeError("Flink state accessed before operator initialization")
        return self._state

    def _require_processing_timer(self) -> ValueState[int]:
        if self._processing_timer is None:
            raise RuntimeError("Flink processing timer state accessed before operator initialization")
        return self._processing_timer


class _ObservationTimestampAssigner(TimestampAssigner):
    def extract_timestamp(self, value: ParsedPayload, record_timestamp: int) -> int:
        del record_timestamp
        if not isinstance(value, ParsedObservation):
            raise TypeError("timestamp assigner received a rejected payload")
        return value.observation.observed_at_unix_nano // 1_000_000


def _interaction_key(item: ParsedPayload) -> str:
    if not isinstance(item, ParsedObservation):
        raise TypeError("key selector received a rejected payload")
    return item.observation.interaction_id


def _event_row(event: InteractionEvent) -> Row:
    record = event_record(event.model_dump_json(), event.interaction_id)
    return Row(record.key, record.value)


def _rejected_row(item: ParsedPayload) -> Row:
    if not isinstance(item, RejectedRecord):
        raise TypeError("DLQ mapper received an observation")
    record = dlq_record(item.rejection)
    return Row(record.key, record.value)


def _timer_millis(unix_nano: int) -> int:
    return (unix_nano + 999_999) // 1_000_000
