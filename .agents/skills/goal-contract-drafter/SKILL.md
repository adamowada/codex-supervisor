---
name: goal-contract-drafter
description: Draft Codex Goal-style execution contracts from planning SQLite tasks, PRDs, issues, or source-of-truth plans. Use when preparing `/goal` objectives, long-running Codex work, fresh-context worker prompts, or AFK/HITL tasks whose acceptance, validation, stop, and blocked conditions must be explicit before execution.
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

- In `codex-supervisor`, prefer the typed renderer first:
  `uv run codex-supervisor goal-contract-render --task-id <task-id>`. Use the manual template only
  when the task is outside planning SQLite or the renderer is unavailable. Run this only when the
  repo environment is already synced or setup is explicitly in scope; otherwise inspect the task
  read-only and report the renderer preflight gap.
- Prefer one goal per worker or active thread.
- Make the stop condition checkable by another Codex thread.
- Tie every acceptance criterion to a verification surface.
- Use the repo authority matrix: locked docs govern durable doctrine; planning SQLite governs active
  plans, current task, task status, worker runs, and execution order.
- Treat native Codex Goals as thread-scoped execution contracts, not project authority.
- Use official `/goal` or Codex goal tooling when available; do not write raw rows into Codex internal databases.
- Before relying on `/goal`, verify `codex --version`, intended `CODEX_HOME`, `/goal` visibility,
  and whether `${CODEX_HOME}/config.toml` has `[features] goals = true`.
- In read-only mode, do not edit Codex config and do not run `codex features enable goals`; use the
  prompt-rendered Goal Contract fallback and report the missing preflight.
- Enable Goals in the target Codex home only when the user explicitly approves Goal Mode setup for
  that Codex home and writes are in scope. Then edit the feature gate or run
  `codex features enable goals`. A worker-launch workflow may require Goals, but it does not itself
  authorize config mutation; without explicit approval, use the prompt-rendered fallback. Restart or
  start a fresh Codex session only if the running process does not pick up an allowed config change.
- If Goals are unavailable, paste the rendered Goal Contract into the worker prompt.
- If `codex --version` fails because the shell cannot execute the resolved Codex binary, especially
  through Windows `WindowsApps`, treat native Goal Mode as unavailable for that worker and use the
  prompt-rendered fallback until the CLI path and `CODEX_HOME` are confirmed.

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
