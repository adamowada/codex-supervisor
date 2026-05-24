---
name: goal-contract-drafter
description: Draft Codex Goal-style execution contracts from planning SQLite tasks, PRDs, issues, or source-of-truth plans. Use when preparing `/goal` objectives, long-running Codex work, fresh-context worker prompts, or any task that needs outcome, context, constraints, validation, stop conditions, blocked conditions, and budget/status boundaries.
---

# Goal Contract Drafter

Turn a plan or task into an evidence-based completion contract. A Goal Contract guides execution; it is not the canonical queue. The canonical queue remains planning SQLite.

## Contract Shape

Include:

- **Objective**: one durable outcome.
- **Context to read first**: source-of-truth docs, task rows, issues, files, or logs.
- **In scope**: allowed behavior and paths.
- **Out of scope**: explicit non-goals.
- **Verification surface**: commands, checks, artifacts, screenshots, review, or metrics that prove progress.
- **Stop condition**: evidence required to declare complete.
- **Blocked condition**: evidence that should pause and ask for HITL.
- **Iteration policy**: narrow loop, repair loop, or story-loop execution.
- **Budget/status hints**: token/time/run limits when available.
- **Record updates**: where progress, artifacts, decisions, and follow-ups must be written.

## Drafting Rules

- Prefer one goal per worker or active thread.
- Make the stop condition checkable by another Codex thread.
- Tie every acceptance criterion to a verification surface.
- Preserve source order: locked docs, planning SQLite, GitHub, handoffs, chat.
- Treat native Codex Goals as thread-scoped execution contracts, not project authority.
- Use official `/goal` or Codex goal tooling when available; do not write raw rows into Codex internal databases.

## Output Template

```text
Goal Contract

Objective:
- ...

Read first:
- ...

In scope:
- ...

Out of scope:
- ...

Verification:
- ...

Stop condition:
- ...

Blocked condition:
- ...

Iteration policy:
- ...

Record updates:
- ...
```

## When The Contract Is Not Ready

If the task lacks acceptance criteria, verification, source pointers, or a clear stop condition, route to `afk-issue-shaper`, `factory-task-decomposer`, or `grill-with-docs` before drafting the Goal Contract.
