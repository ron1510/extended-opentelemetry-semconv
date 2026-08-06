from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("servicegraph-e2e")
    group.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="Provision and run the disposable Kind end-to-end environment.",
    )
    group.addoption(
        "--keep-e2e-cluster",
        action="store_true",
        default=False,
        help="Keep the disposable Kind cluster and images after the test for debugging.",
    )
    elasticsearch = parser.getgroup("servicegraph-elasticsearch")
    elasticsearch.addoption(
        "--run-elasticsearch",
        action="store_true",
        default=False,
        help="Run the disposable Elasticsearch 8.15 integration test.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "e2e" in item.keywords and not config.getoption("--run-e2e"):
            item.add_marker(pytest.mark.skip(reason="pass --run-e2e to provision the disposable Kind environment"))
        if "elasticsearch" in item.keywords and not config.getoption("--run-elasticsearch"):
            item.add_marker(
                pytest.mark.skip(reason="pass --run-elasticsearch to start disposable Elasticsearch 8.15")
            )
