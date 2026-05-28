# Codex Supervisor

`codex-supervisor` is being reset to a small pre-MVP control plane for coordinating Codex work.
The goal is not to preserve the accumulated factory. The goal is to rebuild a smaller system that
can grow without multiplying modes, surfaces, and test obligations.

## Current Product Shape

The product is a Python-first supervisor with one durable state store, one worker-attempt model, and
one acceptance policy model.

The core flow is:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Everything else is secondary. CLI, MCP, plugin, automation, review, spawned-project, and CI surfaces
exist only when they can be expressed through that flow without adding a new axis of behavior.

## Non-Negotiables

- No compatibility layer for pre-MVP behavior.
- No preservation of historical tests as acceptance criteria.
- No legacy queue migration beyond new seed records.
- No broad public surface until the core contract is small and stable.
- No plugin or MCP authority until the Python core can explain and test the same operation.
- No hidden downgrade from supervised or full-auto work into current-thread implementation.

## Assurance Levels

Strictness is modeled as assurance, not as another execution mode.

- `low`: exploratory or candidate work. It may produce useful output, but it cannot close durable
  production work by itself.
- `medium`: ordinary supervised engineering work. It needs structured evidence and focused checks.
- `high`: full-auto, controller, source-of-truth, release, or destructive work. It needs strict
  evidence, explicit acceptance, and review when risk warrants it.

Assurance levels adjust evidence and acceptance. They do not create separate task types, worker
families, schema variants, CLI branches, or plugin paths.

## State Authority

`plans/planning.sqlite3` is the only operational queue and evidence database.

The fresh schema is intentionally small:

- `meta`
- `plans`
- `tasks`
- `attempts`
- `evidence_bundles`
- `decisions`

Historical tables and event vocabularies were deleted. The branch is the archive.

## Repository Map

- `README.md`: product shape.
- `AGENTS.md`: operating instructions for Codex in this repository.
- `PLANS.md`: fresh planning database contract.
- `ARCHITECTURE.md`: layer boundaries and state model.
- `CONTRACTS.md`: task, attempt, evidence, acceptance, and assurance contracts.
- `ROADMAP.md`: ruthless simplification sequence.
- `SOP.md`: daily operating procedure.
- `TESTING.md`: current verification posture.
- `DECISIONS.md`: current durable decisions.
- `HANDOFF.md`: current resume snapshot only.
- `insights/`: durable lessons that should affect future design.

## Active Surface Policy

The active pre-MVP surface is deliberately narrow:

1. Source-of-truth documents.
2. Fresh planning SQLite.
3. Minimal repo-local skill guidance.
4. Minimal verification.

The old broad CLI/MCP/plugin surface is not product doctrine. It can be rebuilt later from the
smaller core, operation by operation.
