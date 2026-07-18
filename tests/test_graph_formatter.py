from __future__ import annotations

import pytest

from extended_otel_semconv.graph.metrics import parse_metrics_json_document
from extended_otel_semconv.services.graph_loader.loader import (
    observations_from_otlp_json_log_document,
    observations_from_otlp_json_metrics_document,
)


def test_otlp_json_datapoint_log_formats_graph_observations() -> None:
    observations = tuple(
        observation.model_dump(mode="json")
        for observation in observations_from_otlp_json_log_document(
            {
                "resourceLogs": [
                    {
                        "scopeLogs": [
                            {
                                "logRecords": [
                                    {
                                        "timeUnixNano": "1784215260000000000",
                                        "body": {
                                            "kvlistValue": {
                                                "values": [
                                                    {
                                                        "key": "metric.name",
                                                        "value": {"stringValue": "traces_service_graph_request_total"},
                                                    },
                                                    {"key": "value", "value": {"intValue": "2450"}},
                                                ]
                                            }
                                        },
                                        "attributes": [
                                            {"key": "client", "value": {"stringValue": "frontend"}},
                                            {"key": "server", "value": {"stringValue": "payment-service"}},
                                            {"key": "connection_type", "value": {"stringValue": "http"}},
                                            {"key": "server_service.namespace", "value": {"stringValue": "payments"}},
                                            {"key": "server_http.request.method", "value": {"stringValue": "POST"}},
                                            {"key": "server_http.route", "value": {"stringValue": "/pay"}},
                                        ],
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        )
    )

    assert any(observation["kind"] == "entity_observed" for observation in observations)
    assert any(
        observation["kind"] == "edge_observed"
        and observation["edge"]["source"] == "service:frontend"
        and observation["edge"]["target"] == "service:payment-service"
        and observation["edge"]["type"] == "calls"
        for observation in observations
    )


def test_formatter_ignores_non_metric_logs() -> None:
    assert tuple(
        observations_from_otlp_json_log_document(
            {"resourceLogs": [{"scopeLogs": [{"logRecords": [{"body": {"stringValue": "hello"}}]}]}]}
        )
    ) == ()


def test_otlp_json_metric_formats_graph_observations() -> None:
    observations = tuple(
        observation.model_dump(mode="json")
        for observation in observations_from_otlp_json_metrics_document(
            {
                "resourceMetrics": [
                    {
                        "scopeMetrics": [
                            {
                                "metrics": [
                                    {
                                        "name": "traces_service_graph_request_total",
                                        "sum": {
                                            "dataPoints": [
                                                {
                                                    "timeUnixNano": "1784215260000000000",
                                                    "asInt": "3",
                                                    "attributes": [
                                                        {"key": "client", "value": {"stringValue": "frontend"}},
                                                        {"key": "server", "value": {"stringValue": "payment-service"}},
                                                        {"key": "connection_type", "value": {"stringValue": "http"}},
                                                        {"key": "server_service.namespace", "value": {"stringValue": "payments"}},
                                                        {"key": "server_http.request.method", "value": {"stringValue": "POST"}},
                                                        {"key": "server_http.route", "value": {"stringValue": "/pay"}},
                                                    ],
                                                }
                                            ]
                                        },
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        )
    )

    assert any(observation["kind"] == "entity_observed" for observation in observations)
    assert any(
        observation["kind"] == "edge_observed"
        and observation["edge"]["source"] == "service:frontend"
        and observation["edge"]["target"] == "service:payment-service"
        and observation["edge"]["type"] == "calls"
        for observation in observations
    )


def test_malformed_otlp_json_metric_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_metrics_json_document({"resourceMetrics": "not-a-list"})
