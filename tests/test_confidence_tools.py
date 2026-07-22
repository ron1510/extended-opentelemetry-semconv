from __future__ import annotations

from pathlib import Path

from extended_otel_semconv.graph.metrics import SERVICE_GRAPH_REQUEST_TOTAL
from extended_otel_semconv_devtools.confidence.otlp_metrics import MetricSample, metrics_json
from extended_otel_semconv_devtools.confidence.scale import (
    ScaleConfig,
    _partition_from_metric_id,
    _percentile,
    build_trace_batch,
)
from otel_servicegraph_diff.runner import observations_from_otlp_json_metrics_payload


def test_metric_fixture_builder_round_trips_through_production_parser() -> None:
    payload = metrics_json(
        (
            MetricSample(
                name=SERVICE_GRAPH_REQUEST_TOTAL,
                attributes={"client": "frontend", "server": "checkout"},
                value=3,
                observed_at_unix_nano=10,
                start_time_unix_nano=1,
            ),
        )
    )

    observations = observations_from_otlp_json_metrics_payload(payload)

    assert len(observations) == 1
    assert observations[0].metric_value == 3


def test_load_batches_have_bounded_deterministic_interaction_names() -> None:
    config = ScaleConfig(
        run_id="test-run",
        endpoint="http://collector/v1/traces",
        bootstrap="kafka:9092",
        flink_url="http://flink:8081",
        collector_metrics_url="http://collector:8888/metrics",
        paired_traces_per_second=100,
        duration_seconds=1,
        batch_size=10,
        interaction_cardinality=3,
        concurrency=2,
        error_ratio=0.1,
        drain_timeout_seconds=10,
    )

    request, servers = build_trace_batch(config, 0, 10)

    assert len(servers) == 3
    assert len(request.resource_spans) == 6
    assert sum(len(item.scope_spans[0].spans) for item in request.resource_spans) == 20


def test_percentile_uses_nearest_rank() -> None:
    assert _percentile((1.0, 2.0, 3.0, 4.0), 0.50) == 2.0
    assert _percentile((1.0, 2.0, 3.0, 4.0), 0.95) == 4.0
    assert _percentile((), 0.95) is None


def test_collector_servicegraph_metrics_are_batched_for_kafka_efficiency() -> None:
    config = (Path(__file__).resolve().parents[1] / "deploy" / "local" / "otelcol-backend.yaml").read_text(
        encoding="utf-8"
    )

    assert "send_batch_size: 256" in config
    assert "send_batch_max_size: 512" in config
    assert "metrics_flush_interval: 5s" in config


def test_flink_source_partition_is_parsed_from_current_offset_metric() -> None:
    metric = (
        "Source__servicegraph-kafka-source.KafkaSourceReader.topic."
        "otel_servicegraph_metrics.partition.2.currentOffset"
    )

    assert _partition_from_metric_id(metric) == 2
    assert _partition_from_metric_id(metric.replace("currentOffset", "committedOffset")) is None


def test_confidence_campaign_has_cardinality_and_soak_fallbacks() -> None:
    script = (Path(__file__).resolve().parents[1] / "scripts" / "run_confidence.ps1").read_text(
        encoding="utf-8"
    )

    assert "foreach ($baseline in $CardinalityBaselines)" in script
    assert 'Invoke-IsolatedScaleStage "cardinality" $baselineRate $baselineDuration $baseline' in script
    assert "$passingRates | Sort-Object -Descending" in script
    assert 'Invoke-IsolatedScaleStage "soak" $soakRate $SoakDurationSeconds 100' in script
