---
name: codex-supervisor
description: Operate the codex-supervisor control plane from Codex Desktop through durable task intent, worker attempts, evidence, and acceptance.
---

# Codex Supervisor

Use this skill when the user asks for `codex-supervisor`, supervisor-managed Codex work, full AFK
work, autonomous worker assignment, queue inspection, durable evidence, or acceptance tracking.

## Core Contract

The durable work model is:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Codex decides the semantics of the work. The supervisor owns durable state, evidence, acceptance,
and auditability. Workers own product file mutation.

## Filesystem Firewall

The supervisor process **MUST** use this bright-line boundary:

- Supervisor-owned files are `.codex-supervisor/**`.
- Product files are every file outside `.codex-supervisor/**`, except the narrow
  `.gitignore` bootstrap rule below.
- The supervisor process **MUST NOT mutate product files directly**.
- Every product file creation, deletion, or mutation **MUST** be assigned through `attempt-run`.
- Generated artifacts, cleanup, repair, audit fixes, warning fixes, and polish changes outside
  `.codex-supervisor/**` are product file mutations.
- A worker is a process launched by `attempt-run`.
- Subagents are not workers. Subagents are useful for exploration or review, but subagents
  **MUST NOT** be treated as supervisor-assigned workers unless the product mutation is performed
  through `attempt-run`.
- `attempt-transition` **MUST NOT** be used as a substitute for product file mutation.

## Bootstrap Git Hygiene

`plan-init` owns the only allowed supervisor write outside `.codex-supervisor/**`.

- Before creating `.codex-supervisor/planning.sqlite3`, `plan-init` **MUST** ensure the workspace
  `.gitignore` ignores `.codex-supervisor/`.
- If `.gitignore` exists, `plan-init` **MUST** append `.codex-supervisor/` only when no equivalent
  rule exists.
- If `.gitignore` does not exist, `plan-init` **MUST** create it with `.codex-supervisor/`.
- The supervisor **MUST NOT** add unrelated ignore rules.
- If `.codex-supervisor/**` is already tracked by git, the supervisor **MUST** stop and report that
  the tracked supervisor files must be removed from the git index before ACP.

## Active Surface

The active mutation operations are:

- `plan-init`
- `task-create`
- `attempt-run`
- `attempt-transition`

These are operation names, not permission to run a bare executable. In Codex Desktop, you **MUST**
invoke mutation operations through the plugin CLI launcher. You **MUST NOT** run bare
`codex-supervisor ...` commands. You **MUST NOT** probe `PATH` to locate `codex-supervisor`.

Use the MCP tool `codex_supervisor.queue_next` only for read-only queue inspection. You **MUST**
pass the intended planning database path or use a launcher configured with
`CODEX_SUPERVISOR_PLANNING_PATH`; MCP **MUST NOT** guess the ledger.

Work categories **MUST** stay in task intent and acceptance criteria. You **MUST NOT** invent
supervisor job types for semantic engineering categories.

## Desktop Invocation

When running from Codex Desktop, you **MUST use the plugin CLI launcher** instead of probing whether
`codex-supervisor` is on `PATH`.

Use this shape:

```sh
python -B scripts/cli_launcher.py <command> ...
```

If you omit `--path` for `plan-init`, `task-create`, `queue-next`, `attempt-run`, or
`attempt-transition`, the launcher **MUST default to the current workspace ledger** at
`.codex-supervisor/planning.sqlite3`. Use an explicit `--path` only when intentionally operating on a
specific ledger.

On Windows or PowerShell, you **MUST** follow [WINDOWS.md](WINDOWS.md) for platform-aware worker
launch and verifier commands.

When a Windows `attempt-run` launches Codex as the worker, it **MUST** use the packaged worker
launcher at `<plugin-root>\scripts\codex_worker_launcher.py`. It **MUST NOT** create an ad hoc
PowerShell worker launcher.

The packaged worker launcher **MUST** default Codex workers to xhigh reasoning with
`model_reasoning_effort="xhigh"`. Pass `--reasoning-effort low`, `medium`, `high`, or `xhigh` only
when the user explicitly asks for different worker reasoning behavior.

## Required Flow

When this skill is invoked for work that creates, edits, verifies, reviews, or ships files, you
**MUST** use the durable supervisor flow. Do not treat small work as exempt.

1. You **MUST run `plan-init --json` before any queue inspection** in a fresh workspace.
   You **MUST NOT run `queue-next` before `plan-init`**.
2. You **MUST create durable task intent** with `task-create` before product mutation.
3. Product mutation tasks **MUST** use `--assurance high` unless the user explicitly requests a
   lower assurance level.
4. You **MUST record a run attempt** through `attempt-run` before product mutation.
5. You **MUST use `attempt-run`** for every product file mutation.
   - On Windows, Codex worker attempts **MUST** use
     `python -B <plugin-root>\scripts\codex_worker_launcher.py --workspace <workspace> --prompt-file <workspace>\.codex-supervisor\worker_prompt.txt`
     after the `attempt-run --` separator.
     Omit `--reasoning-effort` unless the user explicitly asks for a non-default reasoning level;
     the launcher defaults to xhigh reasoning.
6. You **MUST attach explicit evidence**:
   - `--check`: at least one check that ran or one concrete inspection result.
   - `--artifact`: every known expected product path and important generated artifact. `attempt-run`
     also records git-discovered changed product paths automatically. If no product artifact exists,
     record a `--check` that says no product artifact exists.
   - `--risk`: a real residual risk, or `No known residual risk.`
   - `--gap`: a real gap, or `No known gap.`
   - `--next-action`: the next action, or `No next action.`
   - `--review-evidence`: review evidence for high-assurance work, or a concrete reason review was
     not required.
7. You **MUST finish with an acceptance decision** or a blocked state on the same task.

The worker process receives the task assignment through `CODEX_SUPERVISOR_TASK_JSON`, plus task,
attempt, and workspace environment variables. Failed worker processes **MUST NOT** leave passing
acceptance evidence. Declared output artifacts **MUST** exist before supplied passing acceptance can
remain passing.

## Attempt Transition Limits

`attempt-transition` **MUST** be limited to supervisor/admin state:

- recording blocked states before a worker can run
- recording review-only or inspection-only evidence
- recording supervisor-owned setup under `.codex-supervisor/**`
- terminalizing state that does not mutate product files

`attempt-transition` **MUST NOT** be used to record direct supervisor edits to product files.

## Acceptance

When terminalizing an attempt, if the task has exactly one acceptance criterion, you **MUST** use
`--acceptance-result pass` or `--acceptance-result fail`. You **MUST NOT** invent a result name.

Named acceptance results are only for multiple criteria, and each name **MUST** exactly match an
acceptance criterion.

When work already belongs to an existing task, acceptance **MUST** be recorded on that task. You
**MUST NOT** create acceptance-only follow-up tasks. Create follow-up task intent only for new
product work, repair, cleanup, audit, warning, or polish.

## Verifiers

When acceptance depends on file contents, behavior, generated artifacts, API responses, or other
machine-checkable facts, you **MUST** use `attempt-run --verify-command`.

Verifier checks **MUST** prove behavior or structural contract. Prefer builds, tests, API calls,
browser flows, artifact existence, JSON fields, and endpoint responses.

Verifiers **MUST NOT** depend on local implementation names, variable names, or incidental source
snippets unless the task explicitly requires that exact text.

Literal string checks **MUST** only be used when the literal text is itself required by the task.

Prefer a workspace Python verifier at `.codex-supervisor/verify.py`. Do not put complex verifier
logic inline in shell or PowerShell command strings.

## ACP Gate

Before ACP, the supervisor **MUST** verify all of the following:

- `.codex-supervisor/` is ignored by git.
- `git ls-files .codex-supervisor` returns no tracked paths.
- Product file changes are backed by `attempt-run` worker evidence.
- The relevant verifier, smoke test, or acceptance check passed.
- The task has terminal evidence and an acceptance decision or blocked state.

If any ACP gate fails, the supervisor **MUST NOT** commit or push. It **MUST** record or report the
blocking condition instead.

From the target workspace, use these exact git checks before ACP:

```sh
git check-ignore -q -- .codex-supervisor/planning.sqlite3
git ls-files -- .codex-supervisor
git status --short
```

The first command **MUST** exit `0`. The second command **MUST** print nothing. The third command
**MUST** show no tracked `.codex-supervisor/**` paths, and every product-file path it shows **MUST**
be backed by `attempt-run` worker evidence.

## Operating Rules

- Keep the state space small.
- Use assurance levels as policy: `low`, `medium`, `high`.
- Run product mutation through `attempt-run` so stdout, stderr, command metadata, exit code, checks,
  artifacts, risks, gaps, and acceptance results are recorded.
- Treat failures as durable evidence and terminalize attempts instead of silently retrying outside
  the ledger.
- Keep `HANDOFF.md` current only when working in the `codex-supervisor` source repository.

## Verification

In the `codex-supervisor` source repository, run:

```sh
uv run --no-sync python -B scripts/verify.py
```
