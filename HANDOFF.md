# HANDOFF.md

Last updated: 2026-06-04

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

`plan-e2e-weak-spots-20260603` is complete. The remaining factory e2e weak spots are hardened with a
deterministic target-workspace ACP gate and tests: direct product edits are rejected, tracked
`.codex-supervisor/**` state is rejected, and worker-backed product changes are accepted. An opt-in
live Codex worker smoke test now exercises a real `codex exec` worker when
`CODEX_SUPERVISOR_RUN_LIVE_CODEX_E2E=1` is set. The normal verification gate stays deterministic and
skips that live test by default.

`plan-windows-worker-launcher-20260603` is complete. The packaged Desktop plugin now includes
`scripts/codex_worker_launcher.py`, a single stdin-safe Codex worker launch path for `attempt-run`.
The launcher resolves `codex` or `codex.ps1`, wraps Windows `codex.ps1` through PowerShell in one
tested place, and pipes the worker prompt through stdin instead of putting prompt text in argv.
The packaged skill and Windows guidance now require this launcher and forbid ad hoc PowerShell
worker launch scripts. Plugin tests lock the Windows command shape and prompt-stdin behavior.

`plan-live-smoke-a-plus-20260604` is complete. The opt-in live Codex worker smoke now runs a graded
three-scenario ladder through real `attempt-run` evidence, the packaged worker launcher, Python
verifiers, and target-workspace ACP gates. The ladder covers exact single-file creation, code repair
with pytest coverage creation, and data-summary work that preserves inputs while producing derived
JSON and notes. The initial live red exposed the stale direct `codex exec` path, prompt ambiguity,
and an ACP nested untracked file mismatch. ACP now asks git for all untracked files so worker-backed
nested product artifacts match file-level evidence instead of directory placeholders. The live ladder
scored A+ twice consecutively, and the default verification gate passed with 83 tests and one opt-in
live smoke skipped. `plan-live-smoke-polish-20260604` records the post-evidence touched-file Ruff
cleanup and final post-polish verification pass.

`plan-live-todo-smoke-20260604` is complete. The next exact-prompt live smoke used the worker prompt
`create a 3-tier todo list app`. The broad prompt generated unknown product files, which exposed that
`attempt-run` did not automatically record git-discovered product artifacts for ACP. `attempt-run`
now records changed product paths from `git status --porcelain=v1 -z --untracked-files=all` after
the worker/verifier run, excluding `.gitignore` and `.codex-supervisor/**`, so broad worker outputs
can be ACP-backed without predeclaring every file. A deterministic ACP regression covers this path.
The accepted live retry produced `app.js`, `index.html`, and `styles.css`, passed a structural
verifier for a reasonable three-tier todo hierarchy, and passed the target ACP gate with those
product paths worker-backed.

`plan-live-subagent-worktree-smoke-20260604` is complete. The next exact-prompt live smoke used the
worker prompt `create a 3-tier todo list app using 6 subagents working in git worktrees`. The worker
interpreted the prompt literally enough to create six linked git worktrees:
`agent-1-scaffold`, `agent-2-data`, `agent-3-service`, `agent-4-ui`, `agent-5-client`, and
`agent-6-qa`. The root worktree contained coordination and QA files, while the actual app pieces
remained unintegrated in linked worktrees outside the root target workspace. The old ACP gate
incorrectly passed the root when linked worktrees were dirty. ACP now inspects linked git worktrees
and rejects unintegrated product changes outside the target workspace, reporting the dirty linked
worktree path and product files. A deterministic ACP regression covers this. The live target is
intentionally not ACP-ready until those linked worktree changes are integrated, and the source
guardrail now reports that instead of silently passing root ACP.

`plan-live-subagent-a-plus-20260604` is complete. The same live-smoke target has now reached A+:
integration work was assigned through `attempt-run`, copied and reconciled the six subagent
worktree outputs into the root worktree, removed the linked worktrees, and verified the integrated
app. The A+ verifier proved required integrated files, `node --test test/http-contract.test.js`,
`node scripts/smoke-test.js`, and linked worktree count `0`. The final target ACP gate passed with
all changed product paths worker-backed and no failures.

`plan-live-parallel-worker-smoke-20260604` is complete. The exact-prompt live smoke used the worker
prompt `create a 3-tier todo list app. spawn workers in parallel.` The supervisor created four
separate target tasks and launched four `attempt-run` worker processes concurrently, without Codex
subagent framing. The red run proved real overlap and exposed concurrent mutation pressure: all four
live worker attempts terminalized failed or timed out while still producing a shared todo app and
repair artifacts. A final high-assurance target task then ran through `attempt-run`, normalized the
root app, and verified A+ evidence. The target A+ report proves prompt fidelity, worker count `4`,
all six overlap pairs, four terminal parallel worker attempts, `node --test` API/smoke success, and
linked worktree count `0`. Target ACP passed with `.codex-supervisor/planning.sqlite3` ignored, no
tracked `.codex-supervisor/**` paths, and every changed product path worker-backed. A browser smoke
on the generated UI also passed: add a todo to `Next`, move it to `Now`, complete/delete it, and
return the board to empty.

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
`done` in `plans/planning.sqlite3`. The e2e weak-spot hardening pass is complete with 80 default
tests passing and one explicit live Codex worker smoke test skipped unless enabled. The packaged
Windows Codex worker launcher is complete, with 82 default tests passing and one explicit live Codex
worker smoke test skipped unless enabled. The live smoke A+ hardening pass is complete: the opt-in
live ladder scored A+ twice consecutively, and the default verification gate now passes with 83
tests and one explicit live Codex worker smoke test skipped unless enabled. The post-polish
touched-file Ruff check and final verification pass are recorded in `plans/planning.sqlite3`. The
exact-prompt 3-tier todo smoke is also complete; the final verification gate now passes with 84
tests and one explicit live Codex worker smoke test skipped unless enabled. The exact-prompt
six-subagent worktree smoke is complete; ACP now rejects dirty linked worktrees, and the final
verification gate passes with 85 tests and one explicit live Codex worker smoke test skipped unless
enabled. The follow-on A+ integration pass for that same smoke is complete: the target app verifies,
linked worktrees are removed, and target ACP passes. The exact-prompt parallel supervisor worker
smoke is complete: four concurrent `attempt-run` workers were launched without subagents, the red
concurrency result was recorded, the final target app reached A+, browser smoke passed, and target
ACP passed. The final source verification gate passes with 85 tests and one explicit live Codex
worker smoke test skipped unless enabled.

Planning task:

- none
