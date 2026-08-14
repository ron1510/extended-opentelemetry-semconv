---
name: review-servicegraph-architecture
description: Review architecture, abstractions, ownership, typing, and simplification decisions in the Extended OpenTelemetry Semantic Conventions repository. Use for plans, code reviews, refactors, package boundaries, Flink lifecycle changes, semantic code generation, Kafka-to-ArangoDB projection, Gremlin access, or requests to make the repository leaner.
---

# Review Servicegraph Architecture

Review runtime behavior and product contracts before local style. Read affected code rather than relying on documentation or conversation memory.

## System Contract

Preserve unless explicitly changed:

- Collector service-graph delta metrics are the input.
- Flink extracts graph-element contributions and owns contributor-aware lifecycle state.
- Kafka schema `2.0` graph-element upsert/delete events are the public stream contract.
- Nodes and edges have equal lifecycles and deterministic IDs.
- The semantic registry owns entity identity, relationships, Collector dimensions, generated SDK models, and graph topology.
- The indexer projects idempotently into ArangoDB and commits offsets only after database success.
- Gremlin is read-only; the typed client reconstructs semantic models and rejects transformed results.
- Deployment uses Helm, non-root containers, existing platform services and secrets, no CRDs, and no cluster-admin assumption.
- Packaging uses pip and PEP 621, without uv-specific metadata.

## Trace Ownership

Trace only as far as the change can propagate:

1. OTLP JSON parsing and rejection.
2. Datapoint-to-contribution extraction.
3. Element-keyed contributor merge, metrics, and expiry.
4. Kafka lifecycle serialization and keying.
5. ArangoDB routing, replacement/deletion, and offset commit.
6. Gremlin traversal and typed reconstruction.

## Challenge Complexity

For every model, function, class, cache, transformation, and state object, ask whether it represents a product concept, preserves information used later, has one clear owner, and is independently reusable or testable. Prefer direct typed flow over wrappers and conversion maps. Remove speculative compatibility. Use established dependencies when they replace project machinery without weakening the contract.

Keep domain modules separate when responsibilities differ, even if they share one distribution.

## Review Python

- Prefer precise unions, literals, discriminated Pydantic models, and immutability where they encode contracts.
- Use pattern matching for closed variants; use `isinstance` when an open runtime hierarchy is clearer.
- Challenge `Any`, broad object maps, casts, string dispatch, stateless classes, pass-through wrappers, and duplicated parsing.
- Review generator inputs, schema, deterministic output, and collision checks instead of editing generated code.

## Findings

Report findings first by severity with file and line references. Separate correctness defects, simplification opportunities, and preferences. If no issue exists, say so and state residual test or operational risk.
