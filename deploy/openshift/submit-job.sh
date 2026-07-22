#!/usr/bin/env bash
set -euo pipefail

readonly rest_endpoint="http://servicegraph-flink-jobmanager:8081"
readonly job_name="servicegraph-interaction-diff"

until overview="$(curl --fail --silent --show-error "${rest_endpoint}/overview")"; do
  echo "Waiting for the Flink JobManager REST API"
  sleep 5
done

if curl --fail --silent --show-error "${rest_endpoint}/jobs/overview" |
  python -c '
import json
import sys

active_states = {"CREATED", "INITIALIZING", "RUNNING", "RESTARTING", "RECONCILING"}
jobs = json.load(sys.stdin).get("jobs", [])
raise SystemExit(0 if any(job.get("name") == "servicegraph-interaction-diff" and job.get("state") in active_states for job in jobs) else 1)
'; then
  echo "Flink job ${job_name} is already active"
  exit 0
fi

exec flink run \
  -d \
  -m servicegraph-flink-jobmanager:8081 \
  -p 3 \
  -py /workspace/apps/otel-servicegraph-diff/src/otel_servicegraph_diff/cli.py
