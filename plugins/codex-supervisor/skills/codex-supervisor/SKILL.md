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
  You **MUST pass the intended planning database path** or use a launcher configured with
  `CODEX_SUPERVISOR_PLANNING_PATH`; MCP must not guess the ledger.
- Use the repository CLI for mutation:
  - `codex-supervisor plan-init`
  - `codex-supervisor task-create`
  - `codex-supervisor attempt-transition`
  - `codex-supervisor attempt-run`
- Keep work categories in task intent and acceptance criteria. Do not invent supervisor job types.

## Desktop Invocation

When running from Codex Desktop, you **MUST use the plugin CLI launcher** instead of probing whether
`codex-supervisor` is on `PATH`. The launcher lives at `scripts/cli_launcher.py` in this plugin and
forwards to the source repository CLI.

If you omit `--path` for `plan-init`, `task-create`, `queue-next`, `attempt-transition`, or
`attempt-run`, the launcher **MUST default to the current workspace ledger** at
`.codex-supervisor/planning.sqlite3`. Use an explicit `--path` only when intentionally operating on a
specific ledger.

Use the launcher shape:

```sh
python -B scripts/cli_launcher.py <command> ...
```

On Windows or PowerShell, you **MUST** follow [WINDOWS.md](WINDOWS.md) for platform-aware worker
launch and verifier commands.

## Required Flow

When this skill is invoked for work that creates, edits, verifies, or reviews files, you **MUST**
use the durable supervisor flow. Do not treat simple work as exempt.

1. You **MUST create durable task intent** before mutating files.
2. You **MUST record a run attempt** for the work.
3. You **MUST attach evidence** that names checks and artifacts.
4. You **MUST finish with an acceptance decision** or a blocked state.

When terminalizing an attempt, if the task has exactly one acceptance criterion, you **MUST** use
`--acceptance-result pass` or `--acceptance-result fail`. You **MUST NOT** invent a result name.
Named acceptance results are only for multiple criteria, and each name **MUST** exactly match an
acceptance criterion.

When work already belongs to an existing task, acceptance **MUST** be recorded on that task. You
**MUST NOT** create acceptance-only follow-up tasks. Create follow-up task intent only for new
product work, repair, cleanup, audit, or polish.

In a fresh workspace, you **MUST run `plan-init --json` before any queue inspection** to create
`.codex-supervisor/planning.sqlite3`. You **MUST NOT run `queue-next` before `plan-init`** in an
empty folder.

For full AFK or worker-style execution, you **MUST use `attempt-run`**. The worker process receives
the task assignment through `CODEX_SUPERVISOR_TASK_JSON`, plus task, attempt, and workspace env vars.
For full AFK, autonomous worker, unattended worker, or worker-assigned file mutation, you **MUST
create the task with `--assurance high`** unless the user explicitly requests a lower assurance
level. Record declared artifacts, checks, acceptance results, and risk notes on the `attempt-run`
call. When acceptance depends on file contents or other machine-checkable facts, use
`--verify-command` so passing acceptance is backed by an independent verifier. Prefer a workspace
Python verifier at `.codex-supervisor/verify.py`.
Failed worker processes **MUST NOT** leave passing acceptance evidence.
Declared output artifacts **MUST exist** before supplied passing acceptance can remain passing.

For full AFK, autonomous worker, unattended worker, or worker-assigned file mutation, the supervisor
**MUST NOT mutate product files directly**. Product files are files outside `.codex-supervisor/`.
The supervisor may create or update supervisor-owned files under `.codex-supervisor/`, create task
intent, launch workers, inspect outputs, run verifiers or smoke tests, and record evidence. When the
supervisor discovers product cleanup, audit, warning, polish, or repair work, it **MUST** create
follow-up task intent and assign the product mutation through `attempt-run`.

Verifier checks **SHOULD** prove behavior or structural contract. Prefer builds, tests, API calls,
browser flows, artifact existence, JSON fields, and endpoint responses.
Literal string checks **SHOULD** only be used when the literal text is itself required by the task.

For manual edits, use `attempt-transition` to record running and terminal states around the edit. If
the launcher cannot locate the source repository, set `CODEX_SUPERVISOR_REPO_ROOT` to the source
repo and rerun the launcher.

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
