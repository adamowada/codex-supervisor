---
name: codex-supervisor
description: Operate the compact codex-supervisor control plane through task intent, attempts, evidence, acceptance, and assurance policy.
---

# Codex Supervisor Source Skill

Use this skill when working in the `codex-supervisor` source repository or when validating the
packaged Codex Desktop supervisor behavior.

## Core Contract

The active model **MUST** stay:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

- Codex **MUST** decide the semantics of work from task intent and acceptance criteria.
- The supervisor **MUST** own durable state, worker assignment, evidence, acceptance, and auditability.
- The source repository **MUST** keep the state space small.
- New axes, modes, commands, tables, and adapters **MUST** collapse more complexity than they add.
- Work categories **MUST** stay in task intent and acceptance criteria. They **MUST NOT** become
  supervisor job types.

## Source Repository Rules

- Source edits in this repository are normal repository maintenance. The target-workspace filesystem
  firewall below **MUST NOT** be applied to ordinary edits in this source tree.
- `plans/planning.sqlite3` and `HANDOFF.md` **MUST** be current together.
- Any change to current state, completed work, next action, verification evidence, source-of-truth
  status, or planning evidence **MUST** update both `plans/planning.sqlite3` and `HANDOFF.md` in the
  same work unit.
- Protected source-of-truth edits **MUST** refresh `scripts/check_protected_files.py`.
- The packaged Desktop skill at `plugins/codex-supervisor/skills/codex-supervisor/SKILL.md`
  **MUST** remain the authoritative target-workspace operating contract.
- Source tests **MUST** cover the active contract rather than legacy compatibility paths.

## Target Workspace Firewall

Use these rules when validating or operating the packaged Desktop supervisor in another workspace.

- Supervisor-owned files are `.codex-supervisor/**`.
- The supervisor may create or edit `.gitignore` only to ensure `.codex-supervisor/` is ignored.
- Product files are every workspace file outside `.codex-supervisor/**`, except that bootstrap
  `.gitignore` edit.
- Product file creation, deletion, or mutation **MUST** happen through `attempt-run`.
- The supervisor **MUST NOT** mutate product files directly.
- `attempt-transition` **MUST NOT** substitute for a worker-run product mutation.
- Windows target-workspace Codex worker attempts **MUST** use the packaged Desktop worker launcher at
  `plugins/codex-supervisor/scripts/codex_worker_launcher.py`; do not create ad hoc PowerShell
  worker launch scripts.
- Packaged Codex worker launches **MUST** default to xhigh reasoning through
  `model_reasoning_effort="xhigh"` unless the user explicitly requests different worker reasoning
  behavior.
- `plan-init` **MUST** ensure `.codex-supervisor/` is ignored before the workspace can be ACP'd.
- ACP **MUST NOT** proceed if `.codex-supervisor/**` is tracked or if `.codex-supervisor/` is not
  ignored.
- Before target-workspace ACP, run:

```sh
git check-ignore -q -- .codex-supervisor/planning.sqlite3
git ls-files -- .codex-supervisor
git status --short
```

The first command **MUST** exit `0`. The second command **MUST** print nothing. Product-file paths in
`git status --short` **MUST** be backed by `attempt-run` worker evidence.

## Required Flow

- Create durable task intent before product mutation.
- Record a run attempt before product mutation.
- Assign product mutation through `attempt-run`.
- Record stdout, stderr, command metadata, assignment metadata, checks, artifacts, risks, gaps,
  next actions, verifier output, and acceptance through the attempt evidence path. Use explicit
  values such as `No known residual risk.`, `No known gap.`, and `No next action.` when there is
  nothing else to report.
- Treat worker failures and verifier failures as durable evidence.
- Retry the same task when intent is unchanged. Create a new task only for new product work, repair,
  cleanup, audit, or polish.
- For full AFK, autonomous worker, unattended worker, or worker-assigned product mutation, create the
  task with `--assurance high` unless the user explicitly requests a lower assurance level.

## Acceptance

- Assurance levels are `low`, `medium`, and `high`.
- Assurance levels **MUST** be explicit policy data.
- Acceptance **MUST** be recorded on the task that owns the work.
- Acceptance-only follow-up tasks **MUST NOT** be created.
- When terminalizing an attempt with exactly one acceptance criterion, use
  `--acceptance-result pass` or `--acceptance-result fail`.
- Named acceptance results are only for multiple criteria, and each name **MUST** exactly match an
  acceptance criterion.

## Verifiers

- Machine-checkable acceptance **MUST** use `attempt-run --verify-command`.
- Prefer workspace Python verifiers at `.codex-supervisor/verify.py`.
- Verifiers **MUST** prove behavior or structural contract.
- Verifiers **MUST NOT** depend on local implementation names, variable names, or incidental source
  snippets unless the task explicitly requires that exact text.
- Literal string checks **MUST** only be used when the literal text is itself required.

## Verification

Run:

```sh
uv run --no-sync python -B scripts/verify.py
```

The verification gate covers the active planning schema, skill inventory, source locks, plugin
packaging, and focused contract tests.
