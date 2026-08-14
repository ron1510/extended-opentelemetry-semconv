---
name: validate-servicegraph-change
description: Select, run, and report proportionate validation for changes to the semantic SDK, code generator, Flink service, indexer, Gremlin runtime, Helm charts, and end-to-end pipeline. Use before claiming a change works, before commits, and when diagnosing Docker, Kind, Kafka, Flink, ArangoDB, or Gremlin behavior.
---

# Validate Servicegraph Change

Prove the changed contract at the narrowest reliable level, then broaden by blast radius. Never equate rendering, pod readiness, or mocked events with end-to-end success.

## Choose The Depth

- Run targeted tests while iterating, then all tests for the affected package or service.
- Run repository static checks for shared contracts, packaging, or cross-module changes.
- Run Helm lint and relevant renders for chart/value changes.
- Run focused container integration for ArangoDB, Gremlin, or projection behavior.
- Run complete Collector-to-Gremlin E2E only for cross-service runtime changes or explicit requests.
- Do not test trivial accessors or framework behavior; scale tests with state, replay, serialization, and deployment risk.

## Canonical Checks

```powershell
python -m tools.semconv_codegen --check
python -m ruff check .
python -m pyright
python -m pytest -m "not e2e"
python -m mkdocs build --strict
git diff --check
```

Lint changed charts with `helm lint deploy/helm/<chart>`. Render default and relevant restricted/private-network values when templates or values contracts change.

## Stateful Proof

For Flink lifecycle changes, explicitly verify deterministic identities, attribute merge/conflict behavior, duplicates and out-of-order observations, metric accumulation, partial and final expiry, event/processing timers, and Kafka serialization. Claim restart/checkpoint behavior only when exercised.

For indexer changes, verify deterministic keys, collection routing, replay idempotency, edge-delete fanout, partial-write replay, and commits only after complete success.

## Environment Discipline

- Inspect existing containers and Kind clusters before provisioning.
- Use unique task-specific names and track resources created by this run.
- Remove only resources created by the run; never clean unrelated user environments.
- Capture bounded state, events, hooks, and logs before failure cleanup.
- Preserve environments only when requested.

## Report Evidence

Separate unit/static, rendered deployment, focused integration, full E2E, and HA/restart confidence. State what did not run. Claim a pipeline stage worked only when that exact path was observed.
