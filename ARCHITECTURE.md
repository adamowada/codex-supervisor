# Architecture

`codex-supervisor` is the durable evidence substrate below Codex Goal Mode.

Goal Mode decides what should happen next. Supervisor records what was intended, what ran, what
evidence exists, and whether policy accepted it.

## Core Flow

```text
Goal Mode
  -> TaskIntent
  -> RunAttempt
  -> EvidenceBundle
  -> AcceptanceDecision
  -> compact recovery state for Goal Mode
```

The durable substrate preserves this flow across planning, worker launch, evidence capture,
acceptance, and recovery.

## Layers

### Goal Mode Boundary

Goal Mode owns long-lived objective, strategy, sequencing, launch packet content, recovery choices,
repair decisions, and final completion judgment.

Supervisor does not infer semantic job types. Starting a project, fixing a bug, reviewing work,
repairing a failed attempt, and proving a release are all task intent plus attempts, evidence, and
acceptance.

### Source Contracts

Source-of-truth documents define the substrate contract. `SUBSTRATE_PLAN.md` is the branch master
plan for `feature/substrate`. The protected docs stay concise, current, and aligned with that plan.

### Planning Store

`plans/planning.sqlite3` stores operational state using the schema in `PLANS.md`. The store enforces
one active plan, one non-terminal attempt per task, and atomic terminal attempt evidence plus
acceptance decision writes.

The active schema remains compact. Task lineage uses `tasks.lineage_json`. Launch packet details,
verifier intent, command metadata, and evidence digests should use existing structured JSON or
artifact records until a repeated access pattern earns a dedicated table.

### Policy

Policy maps an explicit task assurance level to evidence requirements:

- `low`
- `medium`
- `high`

Assurance is stored task data. Policy does not infer assurance from prose.

### Launch Packet Boundary

Goal Mode writes the free-form launch packet and verifier intent. Supervisor must copy, hash, and
reference them so a future reader can prove which context produced a worker attempt.

The packet is intentionally flexible. It can contain strategy, constraints, file context,
acceptance notes, verifier intent, and recovery instructions. Supervisor records packet identity; it
does not prescribe the packet's semantic schema until repeated access patterns justify one.

### Execution Boundary

Execution is recorded as an attempt. Codex, manual work, shell checks, review, and future adapters
all run attempts when they produce evidence. The generic process runner is the worker execution
path: it starts one worker process in a workspace, captures stdout, stderr, command metadata, exit
code, declared artifacts, git-discovered product paths, and optional verifier output, then writes
terminal evidence through the same acceptance path.

Launch failures, timeouts, verifier failures, missing artifacts, and telemetry write failures become
durable evidence instead of leaving invisible running work.

For Goal Mode product work, Supervisor manages task intent, worker launch, inspection, verifier
setup, evidence, and acceptance. Product files are changed by the worker process inside
`attempt-run`. Supervisor-owned setup and verifier files live under `.codex-supervisor/`. Product
follow-up work becomes new task intent assigned through `attempt-run`.

### Target Workspace Inspection

Target workspace inspection owns product provenance. It reads git workspace state, normalizes paths,
excludes `.gitignore` and `.codex-supervisor/**`, detects changed product paths, inspects linked
worktrees, and identifies product paths backed by succeeded `attempt-run` evidence. Git is the
concrete adapter here.

### Evidence Boundary

Evidence bundles contain summaries, checks, and artifact references. SQLite indexes evidence and
points to supporting artifacts. Evidence is kept structured until the compact store encodes it into
the existing checks and artifacts JSON arrays.

Terminal evidence records compact evidence digests over raw logs so Goal Mode can recover without
reading every artifact: verifier result, changed files, warnings, log sizes, important tails, risk
notes, gaps, next actions, and acceptance rationale.

Acceptance decisions are durable rows written for terminal attempts. They link the task, attempt,
and evidence bundle to the policy result and rationale. Task status is a projection of the latest
terminal decision, not the acceptance record itself.

### Recovery And Lineage

`queue-next` is the read path Goal Mode uses to recover. It exposes active task, active attempt,
liveness age when available, latest evidence, latest acceptance, packet hash, verifier hash,
lineage, git summary, and warning flags.

Retry, repair, review, and final-proof relationships should use one generic lineage mechanism, not
workflow-specific job types.

When rejected evidence blocks a plan, queue inspection can surface the blocked task and suggest a
linked repair task. Creating that task reactivates the plan through the same task-intent path.
When a task has `shipping_proof_of` lineage, recovery state names it as final proof for the linked
task.

### Interfaces

The active CLI surface is `plan-init`, `task-create`, `queue-next`, `attempt-transition`, and
`attempt-run`. `task-create` records durable intent. `queue-next` is inspection only and returns
running active work before ready work.

`attempt-transition` is the supervisor/admin state-transition path for attempts, evidence, blocked
states, review-only evidence, and terminal evidence that does not mutate product files.
`attempt-run` is the product-file mutation path for target-workspace Goal Mode or full AFK work, and
records execution through the same model.

The active MCP surface is one read-only dispatcher operation: `codex_supervisor.queue_next`. MCP
inspection requires an explicit planning path so it cannot silently inspect the source repository
ledger while the active work lives in a workspace ledger.

The active Codex plugin surface is a thin wrapper around that MCP stdio server. The plugin owns
discovery metadata and launch wiring only; it does not define separate task, worker, or acceptance
behavior.

CLI, MCP, plugin, automation, GitHub, and worker integrations are adapters over the substrate
model. Each adapter operation declares the task intent, attempt, evidence, and acceptance behavior
it supports before it becomes active.

## Build Rule

Add one generic operation at a time. Each operation declares:

- task intent it can create or inspect;
- attempts it can run;
- evidence it can emit;
- recovery state it exposes;
- assurance levels it can satisfy;
- acceptance decision it can support.

Operations become part of the active surface after the core model and focused tests cover them. New
semantic work categories become task intents and lineage, not supervisor modes.
