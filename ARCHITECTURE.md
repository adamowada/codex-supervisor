# Architecture

`codex-supervisor` is being rebuilt around one state transition model and a deliberately small
surface.

## Core Flow

```text
TaskIntent
  -> RunAttempt
  -> EvidenceBundle
  -> AcceptanceDecision
```

The control plane is responsible for preserving that flow. Interfaces are allowed only when they
delegate to it cleanly.

## Layers

### Source Contracts

Source-of-truth documents define the current contract. They are not sacred history. When the product
direction changes, rewrite them and refresh hashes.

### Planning Store

`plans/planning.sqlite3` stores active operational state in the fresh schema from `PLANS.md`.

The planning store should remain boring. If a feature needs many tables before it can ship, the
feature is probably too large.

### Policy

Policy maps task intent to an assurance level:

- `low`
- `medium`
- `high`

Policy decides evidence and acceptance requirements. It must not fork the domain model.

### Execution Boundary

Execution is an attempt, not an identity. Codex, manual work, shell checks, review, or future MCP
calls can all be represented as attempts if they produce evidence.

### Evidence Boundary

Evidence bundles contain summaries, checks, and artifact references. The database indexes evidence;
it does not become a blob store.

### Interfaces

CLI, MCP, plugin, automation, and GitHub integrations are optional adapters. They are rebuilt only
after the core model is small and proven.

## Current Architectural Cuts

- The packaged Desktop plugin was removed from the active surface.
- The old repo-local skill mesh was removed.
- The historical planning schema was replaced.
- Old tests were removed as acceptance criteria.
- CI now checks the smaller contract rather than the old factory.

## Rebuild Rule

Add back one public operation at a time. Each operation must declare:

- task intent it can create or inspect;
- attempts it can run;
- evidence it can emit;
- assurance levels it can satisfy;
- acceptance decision it can support.

If that cannot be stated simply, the operation is not ready.
