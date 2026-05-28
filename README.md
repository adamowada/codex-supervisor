# Codex Supervisor

`codex-supervisor` is a compact Python control plane for coordinating Codex work through explicit
tasks, isolated attempts, durable evidence, and acceptance decisions.

## Product Shape

The supervisor owns one durable work model:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Every interface, worker integration, check, and review path flows through that model.

## Assurance Levels

Assurance describes the evidence needed before a task can advance.

- `low`: exploration, diagnosis, sketches, and candidate work.
- `medium`: ordinary supervised engineering work with focused checks.
- `high`: full-auto, source-of-truth, controller, release, destructive, or trust-boundary work with
  strict evidence and explicit acceptance.

Assurance is policy. The core model stays the same across all three levels.

## State Authority

`plans/planning.sqlite3` is the operational queue and evidence database.

The active schema contains:

- `meta`
- `plans`
- `tasks`
- `attempts`
- `evidence_bundles`
- `decisions`

The branch history carries past implementation context. The database carries current operational
state.

## Active Surface

The active product surface is intentionally narrow:

1. Source-of-truth documents.
2. Planning SQLite.
3. One repo-local operating skill.
4. A focused verification gate.

New CLI, MCP, plugin, automation, and worker surfaces are added one operation at a time after the
core model proves the shape.

## Repository Map

- `README.md`: product overview.
- `AGENTS.md`: operating instructions for Codex in this repository.
- `PLANS.md`: planning database contract.
- `ARCHITECTURE.md`: layer boundaries and state model.
- `CONTRACTS.md`: task, attempt, evidence, acceptance, and assurance contracts.
- `ROADMAP.md`: build sequence.
- `SOP.md`: daily operating procedure.
- `TESTING.md`: verification posture.
- `DECISIONS.md`: durable decisions.
- `HANDOFF.md`: current resume snapshot.
- `insights/`: durable design lessons.
