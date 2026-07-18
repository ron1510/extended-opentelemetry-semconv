"""Verify a stress telemetry run persisted expected graph rows."""

from __future__ import annotations

import argparse
import os

from sqlalchemy import create_engine, text


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify stress telemetry rows in Postgres.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--postgres-url",
        default=os.getenv("GRAPH_POSTGRES_URL", "postgresql+psycopg://entity_graph:entity_graph@localhost:5432/entity_graph"),
    )
    args = parser.parse_args()

    engine = create_engine(args.postgres_url, pool_pre_ping=True)
    with engine.begin() as connection:
        service_count = connection.execute(
            text("select count(*) from service_entities where entity_id like :pattern"),
            {"pattern": f"service:stress-{args.run_id}-%"},
        ).scalar_one()
        edge_count = connection.execute(
            text(
                "select count(*) from graph_edges "
                "where source_entity_id like :pattern or target_entity_id like :pattern"
            ),
            {"pattern": f"%stress-{args.run_id}%"},
        ).scalar_one()
        calls_count = connection.execute(
            text(
                "select count(*) from graph_edges "
                "where edge_type = 'calls' "
                "and source_entity_id like :pattern "
                "and target_entity_id like :pattern"
            ),
            {"pattern": f"%stress-{args.run_id}%"},
        ).scalar_one()
        same_service_calls = connection.execute(
            text(
                "select count(*) from graph_edges "
                "where edge_type = 'calls' "
                "and source_entity_id = target_entity_id "
                "and source_entity_id like :pattern"
            ),
            {"pattern": f"%stress-{args.run_id}%"},
        ).scalar_one()
        error_rows = connection.execute(text("select count(*) from graph_observation_errors")).scalar_one()

    print(
        " ".join(
            (
                f"run_id={args.run_id}",
                f"services={service_count}",
                f"edges={edge_count}",
                f"calls={calls_count}",
                f"same_service_calls={same_service_calls}",
                f"errors={error_rows}",
            )
        )
    )

    if service_count < 5:
        raise SystemExit("expected at least 5 stress services")
    if edge_count < 10:
        raise SystemExit("expected at least 10 stress edges")
    if calls_count < 3:
        raise SystemExit("expected at least 3 stress dependency edges")
    if same_service_calls != 0:
        raise SystemExit("same-service dependency edge should not be created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
