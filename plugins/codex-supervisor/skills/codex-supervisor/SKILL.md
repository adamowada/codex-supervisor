---
name: codex-supervisor
description: Operate the codex-supervisor control plane from Codex Desktop through durable task intent, attempts, evidence, and acceptance.
---

# Codex Supervisor

Use this skill when the user explicitly asks for `codex-supervisor`, supervisor-managed Codex work,
AFK supervisor work, queue inspection, or durable evidence/acceptance tracking.

## Model

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Codex decides the semantics of the work. The supervisor owns durable state, evidence, acceptance,
and auditability.

## Active Surface

- Use the MCP tool `codex_supervisor.queue_next` for read-only queue inspection when available.
- Use the repository CLI for mutation:
  - `codex-supervisor plan-init`
  - `codex-supervisor task-create`
  - `codex-supervisor attempt-transition`
  - `codex-supervisor attempt-run`
- Keep work categories in task intent and acceptance criteria. Do not invent supervisor job types.

## Required Flow

When this skill is invoked for work that creates, edits, verifies, or reviews files, you **MUST**
use the durable supervisor flow. Do not treat simple work as exempt.

1. You **MUST create durable task intent** before mutating files.
2. You **MUST record a run attempt** for the work.
3. You **MUST attach evidence** that names checks and artifacts.
4. You **MUST finish with an acceptance decision** or a blocked state.

In a fresh workspace, run `plan-init` first to create `.codex-supervisor/planning.sqlite3`.

For full AFK or worker-style execution, you **MUST use `attempt-run`**. The worker process receives
the task assignment through `CODEX_SUPERVISOR_TASK_JSON`, plus task, attempt, and workspace env vars.
Record declared artifacts, checks, acceptance results, and risk notes on the `attempt-run` call.

For manual edits, use `attempt-transition` to record running and terminal states around the edit. If
the CLI is not on `PATH`, find the source repository from `CODEX_SUPERVISOR_REPO_ROOT` or the
`codex-supervisor-local` marketplace entry in `~/.codex/config.toml`, then run the CLI from that
repository.

## Operating Rules

- Keep the state space small.
- Use assurance levels as policy: `low`, `medium`, `high`.
- Run AFK work through `attempt-run` so stdout, stderr, command metadata, exit code, checks,
  artifacts, risks, and acceptance results are recorded.
- Treat failures as durable evidence and terminalize attempts instead of silently retrying outside
  the ledger.
- Keep `HANDOFF.md` current when working in the source repository.

## Verification

In the source repository, run:

```sh
uv run --no-sync python -B scripts/verify.py
```
