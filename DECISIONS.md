# Decisions

## D-0001: Compact State Model

Decision: The durable model is `TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision`.

Rationale: A single transition model keeps the control plane small enough to reason about and test.

## D-0002: Planning Schema

Decision: Planning SQLite stores `meta`, `plans`, `tasks`, `attempts`, `evidence_bundles`, and
`decisions`.

Rationale: These tables answer the current operational questions directly.

## D-0003: Assurance Levels Are Policy

Decision: `low`, `medium`, and `high` are assurance levels.

Rationale: Assurance changes evidence and acceptance requirements while the core model stays stable.

## D-0004: Skills Are Guidance

Decision: The repo-local skill surface is one concise supervisor skill.

Rationale: Skills are most useful as operating reminders beside the source-of-truth contract.

## D-0005: Interfaces Follow The Core

Decision: CLI, MCP, plugin, automation, and GitHub surfaces are adapters over the core model.

Rationale: Interfaces should make the core easier to use while preserving the same task, attempt,
evidence, and acceptance semantics.

## D-0006: CI Guards The Active Contract

Decision: CI runs the focused verification gate.

Rationale: The gate should match the current architecture and grow with rebuilt behavior.

## D-0007: Insights Capture Design Lessons

Decision: Insights record durable lessons that guide future design.

Rationale: The insight set should help future work preserve the compact control-plane shape.
