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

### Policy

Policy maps an explicit task assurance level to evidence requirements:

- `low`
- `medium`
- `high`

Assurance is stored task data. Policy does not infer assurance from prose.

### Execution Boundary

Execution is recorded as an attempt. Codex, manual work, shell checks, review, and future adapters
can all run attempts when they produce evidence.

### Evidence Boundary

Evidence bundles contain summaries, checks, and artifact references. SQLite indexes evidence and
points to supporting artifacts.

### Interfaces

The active CLI surface is `plan-init`, `queue-next`, and `attempt-transition`. `queue-next` is
inspection only. `attempt-transition` is the write path for attempts, evidence, and acceptance.

The active MCP surface is one read-only dispatcher operation: `codex_supervisor.queue_next`.

CLI, MCP, plugin, automation, GitHub, and worker integrations are adapters over the core model.
Each adapter operation declares the task intent, attempt, evidence, and acceptance behavior it
supports before it becomes active.

## Build Rule

Add one operation at a time. Each operation declares:

- task intent it can create or inspect;
- attempts it can run;
- evidence it can emit;
- assurance levels it can satisfy;
- acceptance decision it can support.

Operations become part of the active surface after the core model and focused tests cover them.
