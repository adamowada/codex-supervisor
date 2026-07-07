# Architecture

`codex-supervisor` is organized around one state transition model and a narrow active surface.

## Core Flow

```text
TaskIntent
  -> RunAttempt
  -> EvidenceBundle
  -> AcceptanceDecision
```

The control plane preserves this flow across planning, execution, evidence, and acceptance.

## Layers

### Source Contracts

Source-of-truth documents define the product contract. They stay concise and current.

### Planning Store

`plans/planning.sqlite3` stores operational state using the schema in `PLANS.md`.
The store enforces one active plan, one non-terminal attempt per task, and atomic terminal attempt
evidence plus acceptance decision writes.

### Policy

Policy maps an explicit task assurance level to evidence requirements:

- `low`
- `medium`
- `high`

Assurance is stored task data. Policy does not infer assurance from prose.

### Execution Boundary

Execution is recorded as an attempt. Codex, manual work, shell checks, review, and future adapters
all run attempts when they produce evidence. The generic process runner is the AFK execution path:
it starts one worker process in a workspace, captures stdout, stderr, command metadata, exit code,
declared artifacts, git-discovered product paths, and optional verifier output, then writes terminal
evidence through the same acceptance path. Launch failures, timeouts, verifier failures, missing
artifacts, and telemetry write failures become durable evidence instead of leaving invisible running
work.

For full AFK or autonomous-worker product work, the supervisor manages task intent, worker launch,
inspection, verifier setup, evidence, and acceptance. Product files are changed by the worker
process inside `attempt-run`. Supervisor-owned setup and verifier files live under
`.codex-supervisor/`. Product follow-up work becomes new task intent assigned through `attempt-run`.

Work semantics live in task intent and worker behavior. The supervisor does not define job types for
features, bugs, reviews, project starts, or other engineering categories.

### Target Workspace Inspection

Target workspace inspection owns product provenance. It reads git workspace state, normalizes paths,
excludes `.gitignore` and `.codex-supervisor/**`, detects changed product paths, inspects linked
worktrees, and identifies product paths backed by succeeded `attempt-run` evidence. Git is the
concrete adapter at this seam.

### Evidence Boundary

Evidence bundles contain summaries, checks, and artifact references. SQLite indexes evidence and
points to supporting artifacts. Evidence is kept structured until the compact store encodes it into
the existing checks and artifacts JSON arrays.

Acceptance decisions are durable rows written for terminal attempts. They link the task, attempt,
and evidence bundle to the policy result and rationale. Task status is a projection of the latest
terminal decision, not the acceptance record itself.

### Interfaces

The active CLI surface is `plan-init`, `task-create`, `queue-next`, `attempt-transition`, and
`attempt-run`. `task-create` records durable intent. `queue-next` is inspection only and returns
running active work before ready work.
`attempt-transition` is the supervisor/admin state-transition path for attempts, evidence, blocked
states, review-only evidence, and terminal evidence that does not mutate product files.
`attempt-run` is the product-file mutation path for target-workspace AFK or autonomous-worker work,
and records execution through the same model.

The active MCP surface is one read-only dispatcher operation: `codex_supervisor.queue_next`. MCP
inspection requires an explicit planning path so it cannot silently inspect the source repository
ledger while the active work lives in a workspace ledger.
The active Codex plugin surface is a thin wrapper around that MCP stdio server. The plugin owns
discovery metadata and launch wiring only; it does not define separate task, worker, or acceptance
behavior.

CLI, MCP, plugin, automation, GitHub, and worker integrations are adapters over the core model.
Each adapter operation declares the task intent, attempt, evidence, and acceptance behavior it
supports before it becomes active.

## Build Rule

Add one generic operation at a time. Each operation declares:

- task intent it can create or inspect;
- attempts it can run;
- evidence it can emit;
- assurance levels it can satisfy;
- acceptance decision it can support.

Operations become part of the active surface after the core model and focused tests cover them.
New semantic work categories become task intents, not supervisor modes.
