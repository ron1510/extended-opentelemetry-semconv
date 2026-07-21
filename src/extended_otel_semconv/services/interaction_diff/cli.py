"""CLI entrypoint for the interaction diff service."""

from __future__ import annotations

from extended_otel_semconv.services.interaction_diff.config import interaction_diff_config_from_env
from extended_otel_semconv.services.interaction_diff.flink_job import run_flink_job


def main() -> int:
    run_flink_job(interaction_diff_config_from_env())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
