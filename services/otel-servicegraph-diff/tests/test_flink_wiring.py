# PyFlink erases generic stream types; these tests intentionally mock that boundary.
# pyright: reportPrivateUsage=false, reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import ANY, MagicMock, call

import pytest

pytest.importorskip("pyflink")

from pyflink.datastream import RuntimeExecutionMode
from pyflink.datastream.connectors.kafka import DeliveryGuarantee, KafkaOffsetResetStrategy

from extended_otel_servicegraph_engine.elements import GraphContributionUpsert, GraphNode, apply_contribution
from extended_otel_servicegraph_engine.metrics import SERVICE_GRAPH_REQUEST_TOTAL
from extended_otel_servicegraph_ingest.interaction import observation_from_servicegraph_datapoint
from otel_servicegraph_diff import flink_job
from otel_servicegraph_diff.config import InteractionDiffConfig
from otel_servicegraph_diff.runner import ParsedObservation


def test_main_loads_settings_and_runs_job(monkeypatch: pytest.MonkeyPatch) -> None:
    config = InteractionDiffConfig()
    load_config = MagicMock(return_value=config)
    run = MagicMock()
    monkeypatch.setattr(flink_job, "interaction_diff_config_from_env", load_config)
    monkeypatch.setattr(flink_job, "run_flink_job", run)

    assert flink_job.main() == 0
    load_config.assert_called_once_with()
    run.assert_called_once_with(config)


def test_run_flink_job_configures_runtime_and_executes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    config = InteractionDiffConfig(
        parallelism=2,
        checkpoint_interval_ms=5_000,
        restart_attempts=4,
        restart_delay_seconds=7,
    )
    flink_config = _FakeConfiguration()
    env = MagicMock()
    source = object()
    sink = object()
    configure_graph = MagicMock()
    environment_factory = MagicMock(return_value=env)

    monkeypatch.setattr(flink_job, "Configuration", lambda: flink_config)
    monkeypatch.setattr(
        flink_job,
        "StreamExecutionEnvironment",
        SimpleNamespace(get_execution_environment=environment_factory),
    )
    monkeypatch.setattr(flink_job, "_kafka_source", MagicMock(return_value=source))
    monkeypatch.setattr(flink_job, "_kafka_sink", MagicMock(return_value=sink))
    monkeypatch.setattr(flink_job, "_configure_job_graph", configure_graph)

    flink_job.run_flink_job(config)

    assert flink_config.values == {
        "restart-strategy.type": "fixed-delay",
        "restart-strategy.fixed-delay.attempts": 4,
        "restart-strategy.fixed-delay.delay": "7 s",
    }
    environment_factory.assert_called_once_with(flink_config)
    env.set_runtime_mode.assert_called_once_with(RuntimeExecutionMode.STREAMING)
    env.set_parallelism.assert_called_once_with(2)
    env.enable_checkpointing.assert_called_once_with(5_000)
    flink_job._kafka_source.assert_called_once_with(config)  # pyright: ignore[reportFunctionMemberAccess]
    flink_job._kafka_sink.assert_called_once_with(config, config.output_topic)  # pyright: ignore[reportFunctionMemberAccess]
    configure_graph.assert_called_once_with(env, config, source, sink)
    env.execute.assert_called_once_with("servicegraph-graph-element-engine")


def test_configure_job_graph_builds_named_stable_operator_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    env = MagicMock()
    source = object()
    sink = object()
    watermark = MagicMock()
    watermark.with_idleness.return_value = watermark
    watermark.with_timestamp_assigner.return_value = watermark
    strategy = SimpleNamespace(
        no_watermarks=MagicMock(return_value="no-watermarks"),
        for_bounded_out_of_orderness=MagicMock(return_value=watermark),
    )
    duration = SimpleNamespace(of_seconds=MagicMock(side_effect=_duration))
    monkeypatch.setattr(flink_job, "WatermarkStrategy", strategy)
    monkeypatch.setattr(flink_job, "Duration", duration)
    monkeypatch.setattr(flink_job, "Types", SimpleNamespace(STRING=MagicMock(return_value="string")))

    config = InteractionDiffConfig(allowed_lateness_seconds=3, interaction_ttl_seconds=10, state_ttl_seconds=30)
    flink_job._configure_job_graph(
        cast(Any, env),
        config,
        cast(Any, source),
        cast(Any, sink),
    )

    source_operator = env.from_source.return_value
    source_named = source_operator.name.return_value
    payloads = source_named.uid.return_value
    parser_operator = payloads.flat_map.return_value
    parser_named = parser_operator.name.return_value
    parser_uid = parser_named.uid.return_value
    watermark_operator = parser_uid.assign_timestamps_and_watermarks.return_value
    watermark_named = watermark_operator.name.return_value
    observations = watermark_named.uid.return_value
    keyed = observations.key_by.return_value
    process_operator = keyed.process.return_value
    process_named = process_operator.name.return_value
    contributions = process_named.uid.return_value
    element_keyed = contributions.key_by.return_value
    aggregate_operator = element_keyed.process.return_value
    aggregate_named = aggregate_operator.name.return_value
    events = aggregate_named.uid.return_value
    map_operator = events.map.return_value
    map_named = map_operator.name.return_value
    event_rows = map_named.uid.return_value
    sink_operator = event_rows.sink_to.return_value
    sink_named = sink_operator.name.return_value

    env.from_source.assert_called_once_with(source, "no-watermarks", "servicegraph-otlp-json")
    source_operator.name.assert_called_once_with("servicegraph-kafka-source")
    source_named.uid.assert_called_once_with("graph-v2-kafka-source")
    payloads.flat_map.assert_called_once_with(ANY)
    parser_operator.name.assert_called_once_with("parse-otlp-servicegraph")
    parser_named.uid.assert_called_once_with("graph-v2-parse-otlp-servicegraph")
    strategy.for_bounded_out_of_orderness.assert_called_once_with("3s")
    watermark.with_idleness.assert_called_once_with("6s")
    watermark.with_timestamp_assigner.assert_called_once_with(ANY)
    parser_uid.assign_timestamps_and_watermarks.assert_called_once_with(watermark)
    watermark_operator.name.assert_called_once_with("graph-element-watermarks")
    watermark_named.uid.assert_called_once_with("graph-v2-watermarks")
    observations.key_by.assert_called_once_with(flink_job._interaction_key, key_type="string")
    keyed.process.assert_called_once_with(ANY)
    process_operator.name.assert_called_once_with("interaction-contributions")
    process_named.uid.assert_called_once_with("graph-v2-interaction-contributions")
    contributions.key_by.assert_called_once_with(flink_job._element_key, key_type="string")
    element_keyed.process.assert_called_once_with(ANY)
    aggregate_operator.name.assert_called_once_with("graph-element-aggregation")
    aggregate_named.uid.assert_called_once_with("graph-v2-element-aggregation")
    events.map.assert_called_once_with(flink_job._event_row, output_type=flink_job.OUTPUT_ROW_TYPE)
    map_operator.name.assert_called_once_with("serialize-graph-element-events")
    map_named.uid.assert_called_once_with("graph-v2-serialize-events")
    event_rows.sink_to.assert_called_once_with(sink)
    sink_operator.name.assert_called_once_with("graph-element-events")
    sink_named.uid.assert_called_once_with("graph-v2-events-sink")


def test_kafka_source_maps_all_contract_properties(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = _fluent_builder(
        "set_bootstrap_servers",
        "set_topics",
        "set_group_id",
        "set_starting_offsets",
        "set_property",
        "set_value_only_deserializer",
    )
    source = object()
    builder.build.return_value = source
    monkeypatch.setattr(flink_job, "KafkaSource", SimpleNamespace(builder=MagicMock(return_value=builder)))
    monkeypatch.setattr(
        flink_job,
        "KafkaOffsetsInitializer",
        SimpleNamespace(committed_offsets=MagicMock(return_value="committed-earliest")),
    )
    deserializer = object()
    monkeypatch.setattr(flink_job, "SimpleStringSchema", MagicMock(return_value=deserializer))
    config = InteractionDiffConfig(kafka_bootstrap_servers="one:9092,two:9092")

    assert flink_job._kafka_source(config) is source
    builder.set_bootstrap_servers.assert_called_once_with("one:9092,two:9092")
    builder.set_topics.assert_called_once_with(config.input_topic)
    builder.set_group_id.assert_called_once_with(config.group_id)
    flink_job.KafkaOffsetsInitializer.committed_offsets.assert_called_once_with(  # pyright: ignore[reportFunctionMemberAccess]
        KafkaOffsetResetStrategy.EARLIEST
    )
    builder.set_starting_offsets.assert_called_once_with("committed-earliest")
    builder.set_property.assert_has_calls(
        [
            call("commit.offsets.on.checkpoint", "true"),
            call("allow.auto.create.topics", "false"),
            call("security.protocol", "PLAINTEXT"),
        ]
    )
    builder.set_value_only_deserializer.assert_called_once_with(deserializer)
    builder.build.assert_called_once_with()


def test_kafka_sink_maps_serializers_delivery_and_properties(monkeypatch: pytest.MonkeyPatch) -> None:
    key_java = object()
    value_java = object()
    jvm = SimpleNamespace(
        io=SimpleNamespace(
            extendedotel=SimpleNamespace(
                flink=SimpleNamespace(
                    FirstColumnStringSerializationSchema=MagicMock(return_value=key_java),
                    SecondColumnStringSerializationSchema=MagicMock(return_value=value_java),
                )
            )
        )
    )
    monkeypatch.setattr(flink_job, "get_gateway", MagicMock(return_value=SimpleNamespace(jvm=jvm)))
    serialization_schema = MagicMock(side_effect=_schema)
    monkeypatch.setattr(flink_job, "SerializationSchema", serialization_schema)

    record_builder = _fluent_builder("set_topic", "set_key_serialization_schema", "set_value_serialization_schema")
    record_serializer = object()
    record_builder.build.return_value = record_serializer
    monkeypatch.setattr(
        flink_job,
        "KafkaRecordSerializationSchema",
        SimpleNamespace(builder=MagicMock(return_value=record_builder)),
    )
    sink_builder = _fluent_builder(
        "set_bootstrap_servers",
        "set_record_serializer",
        "set_delivery_guarantee",
        "set_property",
    )
    sink = object()
    sink_builder.build.return_value = sink
    monkeypatch.setattr(flink_job, "KafkaSink", SimpleNamespace(builder=MagicMock(return_value=sink_builder)))
    config = InteractionDiffConfig(kafka_bootstrap_servers="broker:9092")

    assert flink_job._kafka_sink(config, "events") is sink
    serialization_schema.assert_has_calls([call(key_java), call(value_java)])
    record_builder.set_topic.assert_called_once_with("events")
    record_builder.set_key_serialization_schema.assert_called_once_with(("schema", key_java))
    record_builder.set_value_serialization_schema.assert_called_once_with(("schema", value_java))
    sink_builder.set_bootstrap_servers.assert_called_once_with("broker:9092")
    sink_builder.set_record_serializer.assert_called_once_with(record_serializer)
    sink_builder.set_delivery_guarantee.assert_called_once_with(DeliveryGuarantee.AT_LEAST_ONCE)
    sink_builder.set_property.assert_has_calls(
        [call("allow.auto.create.topics", "false"), call("security.protocol", "PLAINTEXT")]
    )
    sink_builder.build.assert_called_once_with()


def test_payload_parser_initializes_metric_and_yields_valid_observation() -> None:
    counter = MagicMock()
    metrics = MagicMock()
    metrics.counter.return_value = counter
    runtime = MagicMock()
    runtime.get_metrics_group.return_value = metrics
    parser = flink_job._PayloadParser()

    with pytest.raises(RuntimeError, match="before operator initialization"):
        parser._require_rejected_records()

    parser.open(runtime)
    observations = tuple(parser.flat_map(_valid_metrics_payload()))

    metrics.counter.assert_called_once_with("rejected_records")
    assert len(observations) == 1
    counter.inc.assert_not_called()


def test_payload_parser_yields_multiple_points_and_ignores_unknown_metrics() -> None:
    payload = json.loads(_valid_metrics_payload())
    metrics = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    second_point = dict(metrics[0]["sum"]["dataPoints"][0])
    second_point.update({"asInt": "2", "timeUnixNano": "2234567890"})
    metrics[0]["sum"]["dataPoints"].append(second_point)
    metrics.append({"name": "traces_service_graph_request_duration_seconds"})

    counter = MagicMock()
    runtime = MagicMock()
    runtime.get_metrics_group.return_value.counter.return_value = counter
    parser = flink_job._PayloadParser()
    parser.open(runtime)

    observations = tuple(parser.flat_map(json.dumps(payload)))

    assert [item.observation.metric.value for item in observations] == [1, 2]
    counter.inc.assert_not_called()


def test_process_open_registers_versioned_ttl_state(monkeypatch: pytest.MonkeyPatch) -> None:
    ttl = object()
    ttl_builder = _fluent_builder(
        "update_ttl_on_create_and_write",
        "never_return_expired",
        "cleanup_full_snapshot",
    )
    ttl_builder.build.return_value = ttl
    new_builder = MagicMock(return_value=ttl_builder)
    monkeypatch.setattr(flink_job, "StateTtlConfig", SimpleNamespace(new_builder=new_builder))
    monkeypatch.setattr(flink_job, "Time", SimpleNamespace(seconds=MagicMock(return_value="60s")))
    monkeypatch.setattr(
        flink_job,
        "Types",
        SimpleNamespace(STRING=MagicMock(return_value="string"), LONG=MagicMock(return_value="long")),
    )
    descriptors: list[_FakeDescriptor] = []

    def descriptor(name: str, value_type: object) -> _FakeDescriptor:
        result = _FakeDescriptor(name, value_type)
        descriptors.append(result)
        return result

    monkeypatch.setattr(flink_job, "ValueStateDescriptor", descriptor)
    states = [object(), object()]
    runtime = MagicMock()
    runtime.get_state.side_effect = states
    operator = flink_job._InteractionContributionProcess(ttl_seconds=5, state_ttl_seconds=60)

    operator.open(runtime)

    new_builder.assert_called_once_with("60s")
    assert [(item.name, item.value_type, item.ttl) for item in descriptors] == [
        ("interaction-state-v2", "string", ttl),
        ("interaction-processing-expiry-v2", "long", ttl),
    ]
    assert operator._state is states[0]  # pyright: ignore[reportPrivateUsage]
    assert operator._processing_timer is states[1]  # pyright: ignore[reportPrivateUsage]


def test_small_stream_adapters_preserve_identity_and_time() -> None:
    parsed = _parsed_observation()
    assigner = flink_job._ObservationTimestampAssigner()
    assert assigner.extract_timestamp(parsed, record_timestamp=999) == 1_234
    assert flink_job._interaction_key(parsed) == parsed.observation.interaction_id
    assert flink_job._timer_millis(1_000_000_000) == 1_000
    assert flink_job._timer_millis(1_000_000_001) == 1_001

    contribution = GraphContributionUpsert(
        element_id="service:frontend",
        contributor_id="interaction-a",
        observed_at_unix_nano=1_234_567_890,
        element=GraphNode(id="service:frontend", type="service"),
    )
    result = apply_contribution(None, contribution, emitted_at_unix_ms=10)
    assert result.event is not None
    assert flink_job._element_key(contribution) == contribution.element_id
    row = flink_job._event_row(result.event)
    assert row[0] == result.event.element_id
    assert '"operation":"upsert"' in row[1]


class _FakeConfiguration:
    def __init__(self) -> None:
        self.values: dict[str, str | int] = {}

    def set_string(self, key: str, value: str) -> None:
        self.values[key] = value

    def set_integer(self, key: str, value: int) -> None:
        self.values[key] = value


class _FakeDescriptor:
    def __init__(self, name: str, value_type: object) -> None:
        self.name = name
        self.value_type = value_type
        self.ttl: object | None = None

    def enable_time_to_live(self, ttl: object) -> None:
        self.ttl = ttl


def _fluent_builder(*method_names: str) -> MagicMock:
    builder = MagicMock()
    for method_name in method_names:
        getattr(builder, method_name).return_value = builder
    return builder


def _duration(seconds: int) -> str:
    return f"{seconds}s"


def _schema(value: object) -> tuple[str, object]:
    return "schema", value


def _parsed_observation() -> ParsedObservation:
    observation = observation_from_servicegraph_datapoint(
        SERVICE_GRAPH_REQUEST_TOTAL,
        {"client": "frontend", "server": "checkout-api"},
        1,
        1_234_567_890,
        start_time_unix_nano=1,
    )
    assert observation is not None
    return ParsedObservation(observation=observation)


def _valid_metrics_payload() -> str:
    return """{
      "resourceMetrics": [{
        "scopeMetrics": [{
          "metrics": [{
            "name": "traces_service_graph_request_total",
            "sum": {
              "aggregationTemporality": 2,
              "dataPoints": [{
                "asInt": "1",
                "startTimeUnixNano": "1",
                "timeUnixNano": "1234567890",
                "attributes": [
                  {"key": "client", "value": {"stringValue": "frontend"}},
                  {"key": "server", "value": {"stringValue": "checkout-api"}}
                ]
              }]
            }
          }]
        }]
      }]
    }"""
