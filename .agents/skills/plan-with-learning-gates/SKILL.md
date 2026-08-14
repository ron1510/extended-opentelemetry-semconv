---
name: plan-with-learning-gates
description: Add deliberate-learning checkpoints to plans for nontrivial architecture, state, data-contract, deployment, or unfamiliar implementation work. Use when creating or reviewing an engineering plan in this repository so the user keeps implementation knowledge while Codex preserves delivery speed. Skip for mechanical edits and direct factual questions.
---

# Plan With Learning Gates

Preserve AI delivery speed while making the critical mechanism understandable and reviewable by the user.

## Classify The Change

- Treat architecture, stateful behavior, retries, identity, schemas, concurrency, security boundaries, and unfamiliar libraries as learning-bearing work.
- Treat formatting, generated output, straightforward renames, dependency bumps, and repetitive wiring as mechanical work.
- Apply the full workflow only to learning-bearing work.

## Build The Plan

Before proposing implementation, identify the changed product behavior, the invariant whose failure invalidates the design, one primary learning target, a small hands-on slice for the user, and the mechanical work Codex can own.

Include a short `Learning Gate` in every substantial plan with two to four tailored questions:

- What exact input enters this mechanism, and what output leaves it?
- Which component owns the state, and why is that the correct key or boundary?
- What happens on duplicate delivery, retry, replay, and restart?
- What starts, updates, expires, and deletes the lifecycle object?
- Which identity and compatibility contract must remain stable?
- What production failure is absent from the happy path?
- Which test or observation proves the important invariant?

Leave selected questions as review prompts when retrieval improves learning. Answer them when safety, ambiguity, or the user requires it.

## Preserve Momentum

- Skip the gate for trivial tasks and do not force the user to write boilerplate.
- Do not reopen an approved plan unless inspection reveals a missing or false invariant.
- Prefer one user-owned critical function, test, diagnosis, or teach-back over splitting all implementation.
- If Codex implements everything, finish with a focused review checkpoint.

## Close The Change

Report evidence and ask concise teach-back questions about the learning target. The user should be able to explain runtime flow, ownership, failure behavior, and proof without relying on Codex's summary.
