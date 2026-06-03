# HANDOFF.md

Last updated: 2026-06-03

This is the current resume snapshot.

## Current State

Branch: `feature/simplification-refactor`

Current model:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Current assurance levels:

- `low`
- `medium`
- `high`

Active planning database:

- `meta`
- `plans`
- `tasks`
- `attempts`
- `evidence_bundles`
- `decisions`

Ignored local cleanup is complete. `.venv/` remains for local development.

Stage 2 is implemented in `src/codex_supervisor/policy.py`. Assurance policy is pure core code:
it uses explicit `low`, `medium`, or `high` task assurance, defines evidence requirements, and
evaluates task, attempt, and evidence records without importing CLI, MCP, plugin, worker, or SQLite
layers. Assurance is not inferred from prose.

Stage 3 is implemented in `src/codex_supervisor/attempts.py` and
`src/codex_supervisor/attempt_store.py`. Run attempts now have a pure status model, compact SQLite
helpers, evidence attachment, and planning integrity checks for attempt/evidence relationships.

Stage 4 is implemented in `src/codex_supervisor/small_interface.py`. The active CLI includes
`task-create` for durable task intent, `queue-next` for inspection, and `attempt-transition` for
supervisor/admin state transitions. `plan-init` exists to create the compact schema. `queue-next` has one meaning: the
next operational task in the active queue, with running work surfaced before ready work.
`attempt-transition` is the state-transition path for attempts, evidence, and acceptance when the
transition does not mutate product files. `plan-init`
supports `--json` so fresh workspace smoke tests can initialize the compact schema without parsing
human output.

Stage 5 is implemented in `src/codex_supervisor/process_attempt.py`. `attempt-run` is the generic
AFK process path: it writes a task assignment JSON for the worker, passes it as
`CODEX_SUPERVISOR_TASK_JSON`, runs one command in an explicit workspace, records stdout, stderr,
command metadata, assignment metadata, a tiny liveness JSON with `last_output_at`, exit code,
artifacts, checks, optional verifier output, risks, gaps, and acceptance results, then terminalizes
the attempt through the same acceptance policy path. Failed worker processes and failed verifier
commands cannot leave supplied passing acceptance results as passing evidence. If a worker times out,
`attempt-run` still runs the verifier when one is supplied; a passing verifier can accept the
original task instead of forcing a separate acceptance-only task. Process launch failures, verifier
failures, missing declared artifacts, and telemetry write failures become durable terminal evidence
instead of stranded running attempts. Work categories remain task intent and acceptance criteria, not
supervisor job types.
For full AFK or autonomous-worker product work, the supervisor may manage task intent, worker launch,
inspection, verifier setup, evidence, and acceptance, but it does not mutate product files directly.
Product cleanup, audit, warning, polish, or repair work is assigned through another `attempt-run`.
Verifier commands must prove behavior or structural contract: builds, tests, API calls, browser
flows, artifact existence, JSON fields, and endpoint responses are preferred. Verifiers must not
depend on local implementation names, variable names, or incidental source snippets unless the task
explicitly requires that exact text. Literal string checks are reserved for tasks where literal text
is itself required.

The happy path is now locked by scenario tests: a fresh workspace can initialize a workspace-local
ledger, create a task, run one worker process through `attempt-run`, record assignment/process
evidence, run a generic verifier when acceptance depends on machine-checkable facts, accept a single
criterion with `--acceptance-result pass`, and end with a clean planning database. Bare `pass` or
`fail` is intentionally valid only for single-criterion tasks; tasks with multiple criteria must name
criteria explicitly. When the last open task in an active plan becomes done, the plan becomes done
too. Liveness and timeout-recovery tests cover live `last_output_at` updates and verifier acceptance
on the original timed-out task. A second scenario test covers the current follow-up model: when
supervisor inspection discovers additional product work after a plan is done, the supervisor creates
a new plan/task and assigns that mutation through another worker attempt. Acceptance-only follow-up
tasks are disallowed by skill guidance; follow-up task intent is for new product work, repair,
cleanup, audit, or polish.

The planning database has been reconciled through `c8280ad Add timeout recovery liveness`.
`plan-ledger-currentness-20260531` reconstructs the missing records after
`attempt-factory-state-hardening-20260531` and adds the currentness guardrail. Source-of-truth docs
now require `HANDOFF.md` and `plans/planning.sqlite3` to move together, and
`tests/test_simplified_contract.py` fails when `HANDOFF.md` changes without a matching planning DB
change relative to `HEAD`. The liveness regression test also tolerates transient partial reads while
the worker liveness JSON is being rewritten. `plan-verifier-steering-20260601` records the
behavior-first verifier steering hardening after the Green Book mobile-header smoke test exposed an
overly literal local variable-name check.

Stage 6 is implemented in `src/codex_supervisor/adapter_contracts.py` and the read-only MCP
`codex_supervisor.queue_next` operation. Adapter growth is declaration-first: an operation must name
task intent, attempt behavior, evidence behavior, assurance levels, acceptance behavior, state flow,
and operator value before activation. `plugins/codex-supervisor` is the thin Codex plugin wrapper:
it contains discovery metadata, MCP config, a Desktop skill entrypoint, and a cache-safe launcher
for the same compact MCP stdio server.

The live surface now matches the compact contract. `src/codex_supervisor/cli.py` exposes five
commands: `plan-init`, `task-create`, `queue-next`, `attempt-transition`, and `attempt-run`.
`src/codex_supervisor/mcp_server.py` exposes one in-process tool: `codex_supervisor.queue_next`, and
`src/codex_supervisor/mcp_stdio.py` provides the minimal stdio JSON-RPC transport for live MCP
clients. `plugins/codex-supervisor` makes that transport discoverable as a Codex plugin without
adding a second control plane. The plugin also provides `scripts/cli_launcher.py`, a packaging-only
forwarder to the source CLI so Desktop runs do not probe PATH before starting supervisor work. Its
packaged skill requires durable task intent, attempt, evidence, and acceptance whenever the
supervisor is invoked for work, and it forbids `queue-next` before `plan-init` in fresh folders. It
also links Windows-specific launch guidance and prefers workspace Python verifiers at
`.codex-supervisor/verify.py` over inline shell or PowerShell verifier logic. The launcher defaults
omitted planning paths to the current workspace ledger, not the source repository. The old operation
registry, broad planning inspection commands, and fake worker scaffold have been removed.

`plan-supervisor-firewall-skill-20260603` is complete. The packaged Desktop skill has been rewritten
as a deterministic supervisor/worker filesystem contract: the supervisor owns `.codex-supervisor/**`
and the narrow `.gitignore` bootstrap edit, product files must be mutated through `attempt-run`, and
ACP must stop if `.codex-supervisor/**` is tracked or not ignored. The repo-local source skill now
separates source-repository maintenance from target-workspace supervisor operation. `plan-init`
enforces the workspace `.gitignore` guard and rejects tracked supervisor state. Focused CLI/plugin
tests passed with 20 tests, and the full verification gate passed with 75 tests.

`plan-skill-determinism-20260603` is complete. The remaining skill ambiguity has been removed:
Desktop mutation operations are logical operation names and must be invoked through the plugin CLI
launcher, ACP has literal git checks, evidence fields require explicit values instead of optional
gaps, and source docs now say `attempt-transition` is a supervisor/admin state transition rather
than product-file mutation.

The package has been cut down to the compact implementation modules. Attempt transitions validate
task ownership, planning integrity checks open work per active plan, and the attempt store prevents
multiple non-terminal attempts for a task. The attempt store enforces one active plan, reactivates
blocked work through the same retry path, and atomically writes terminal attempt evidence before task
status changes. Surviving queue read SQL lives in `AttemptStore`.

Repo-local skills now include:

- `codex-supervisor`
- `improve-codebase-architecture`
- `reduce-codebase-complexity`

`reduce-codebase-complexity` includes a front-door ruthlessness calibration step. It asks for
deletion tolerance, mutation scope, and sacred constraints only when those are unclear, then treats
the answer as run posture rather than another persistent mode axis.

## Roadmap

1. Stage 1, Foundation Contract: align docs, planning SQLite, skill guidance, CI, insights, handoff,
   and protected hashes around the compact model.
2. Stage 2, Policy Core: implement assurance and acceptance policy in code.
3. Stage 3, Execution Attempts: represent manual, shell, review, and future Codex work as one
   attempt shape.
4. Stage 4, Small Interface: add one inspection command and one mutation command.
5. Stage 5, Generic AFK Process Boundary: run worker processes inside the attempt/evidence model.
6. Stage 6, Interface Growth: add larger adapters one operation at a time.

## Next Action

All roadmap stages, compact contract repair, live-surface simplification, generic AFK process
execution, plugin workspace-default repair, generic verifier evidence, Windows launch steering,
Python-verifier happy-path coverage, factory-state hardening, timeout-recovery liveness, ledger
reconstruction, currentness guardrails, liveness test race repair, and repo-local
complexity-reduction skill work, including calibration, are complete. Verifier steering now uses
MUST language to reject implementation-name and incidental-snippet checks unless exact text is part
of the task. The supervisor filesystem firewall skill hardening and `plan-init` git hygiene guard
are complete. The follow-up determinism cleanup for Desktop launcher wording, ACP git checks,
explicit evidence fields, and state-transition language is complete. The related plans are marked
`done` in `plans/planning.sqlite3`.

Planning task:

- none
