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

Policy maps task intent to an assurance level:

- `low`
- `medium`
- `high`

Policy sets evidence and acceptance requirements.

### Execution Boundary

Execution is recorded as an attempt. Codex, manual work, shell checks, review, and future adapters
can all run attempts when they produce evidence.

### Evidence Boundary

Evidence bundles contain summaries, checks, and artifact references. SQLite indexes evidence and
points to supporting artifacts.

### Interfaces

CLI, MCP, plugin, automation, and GitHub integrations are adapters over the core model. Each adapter
operation declares the task intent, attempt, evidence, and acceptance behavior it supports.

## Build Rule

Add one operation at a time. Each operation declares:

- task intent it can create or inspect;
- attempts it can run;
- evidence it can emit;
- assurance levels it can satisfy;
- acceptance decision it can support.

Operations become part of the active surface after the core model and focused tests cover them.
