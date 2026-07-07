# Codex Supervisor

`codex-supervisor` is the durable evidence substrate for Codex Goal Mode.

Goal Mode owns judgment: objective, strategy, sequencing, recovery, and final completion. Supervisor
owns durable proof: task intent, run attempts, evidence, acceptance decisions, product provenance,
worker launch records, and compact recovery state.

## Product Contract

The substrate keeps one durable work model:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Every interface, check, and worker integration flows through that model. Work semantics stay in
Goal Mode launch packets, task intent, and acceptance criteria. Supervisor records and verifies what
happened; it does not define semantic job types.

## Branch Master Plan

`SUBSTRATE_PLAN.md` is the master plan for `feature/substrate`. It names the pivot from
orchestration layer to durable Goal Mode substrate and defines the implementation sequence for:

- free-form launch packet capture and hashing;
- launch-time `command.json` metadata;
- generic task lineage for review, repair, retry, and final proof;
- more recovery data from `queue-next` and MCP;
- structured evidence digests;
- supervised shipping/final-proof records.

## Assurance Levels

Assurance describes the evidence needed before a task can advance.

- `low`: diagnosis, sketches, and candidate work.
- `medium`: ordinary supervised engineering work with focused checks.
- `high`: full-auto, source-of-truth, controller, release, destructive, or trust-boundary work with
  strict evidence and explicit acceptance.

Assurance is policy data. The durable substrate model stays the same across all three levels.

## State Authority

`plans/planning.sqlite3` is the operational queue and evidence ledger.

The active schema contains:

- `meta`
- `plans`
- `tasks`
- `attempts`
- `evidence_bundles`
- `acceptance_decisions`
- `decisions`

The branch history carries past implementation context. The database carries current operational
state. `HANDOFF.md` is the readable resume snapshot and must move with the ledger whenever current
state, completed work, next action, verification evidence, or source-of-truth status changes.

## Active Surface

The active product surface remains intentionally narrow and generic:

1. Source-of-truth documents, including the substrate branch master plan.
2. Planning SQLite.
3. Bounded repo-local operating and refactoring skills.
4. Five compact CLI commands: `plan-init`, `task-create`, `queue-next`, `attempt-transition`, and
   `attempt-run`.
5. One read-only MCP adapter operation: `codex_supervisor.queue_next`, with an explicit planning
   path.
6. One thin Codex plugin wrapper that starts the MCP stdio server and forwards Desktop CLI calls to
   the source CLI, defaulting omitted planning paths to the current workspace ledger.
7. A focused verification gate.

`task-create` records Goal Mode's next work unit as durable intent. `attempt-run` runs one process
in a workspace, writes the worker assignment to `CODEX_SUPERVISOR_TASK_JSON`, and records stdout,
stderr, command metadata, assignment metadata, artifacts, checks, risks, optional verifier results,
and acceptance through the same attempt/evidence path as manual transitions.

Terminal attempts write a durable acceptance decision linked to the task, attempt, and evidence
bundle. Task status is the current-state projection of that decision.

Product provenance is owned by the target workspace inspection layer. `attempt-run` records declared
artifacts and git-discovered changed product paths, excluding `.gitignore` and
`.codex-supervisor/**`. ACP uses the same provenance rules to decide whether changed product paths
are worker-backed.

`queue-next` inspects compact recovery state. Running work is surfaced before ready work so Goal
Mode can resume, finish, block, or repair an in-flight attempt instead of silently starting
something else.

The plugin is packaging, not a second workflow engine. New CLI, MCP, plugin, automation, and worker
surfaces are added one generic operation at a time after the substrate contract is proven.

## Repository Map

- `README.md`: product overview.
- `AGENTS.md`: operating instructions for Codex in this repository.
- `SUBSTRATE_PLAN.md`: master plan for the `feature/substrate` pivot.
- `PLANS.md`: planning database contract.
- `ARCHITECTURE.md`: layer boundaries and state model.
- `CONTRACTS.md`: task, attempt, evidence, acceptance, recovery, and assurance contracts.
- `ROADMAP.md`: substrate implementation sequence.
- `SOP.md`: daily operating procedure.
- `TESTING.md`: verification posture.
- `DECISIONS.md`: durable decisions.
- `HANDOFF.md`: current resume snapshot.
- `insights/`: design lessons.
