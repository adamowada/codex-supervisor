# Handoff

## Current State

Repository: `codex-supervisor`

Before starting work, run `git status --short --branch` and `git rev-parse --short HEAD` to confirm
the local checkout. This file is a mutable handoff, while `plans/planning.sqlite3` is the canonical
operational queue.

The repository is a Python-first control plane for an agentic coding factory around Codex. The
bootstrap source-of-truth documents, planning SQLite database, source lock guard, Python supervisor
package, ignored OSS study sources, insights graph, and repo-local skill pack are present.

Major additions now present:

- `.agents/skills/codex-supervisor`: thin top-level orchestrator skill.
- `.agents/skills/skill-router`: small dispatcher for choosing the right workflow skill.
- Matt Pocock-inspired engineering skills for architecture, grilling, triage, issue shaping, TDD,
  diagnosis, prototyping, and zoom-out review.
- Fresh-thread code review and review-finding fixer skills matching Adam's review workflow.
- Protected source-of-truth doctrine for treating local `~/.codex` SQLite databases as read-only
  telemetry, while keeping `plans/planning.sqlite3` as the canonical queue.
- Goal Contract and Story Loop doctrine inspired by Codex Goals and Ralph.
- `sources/snarktank-ralph` is present locally as an ignored MIT-licensed inspiration source.
- The queued six-lane knowledge graph audit is complete; its findings were reconciled into docs,
  skills, planning state, and insights.
- Completed explorer worker runs now point at structured JSON evidence:
  `insights/bootstrap-landmine-worker-result.json`; the markdown audit remains linked supporting
  context.
- Goal Contract and Story Loop implementation is present locally: `goal-contract-render`,
  `story-loop-status`, and `story-loop-record` are available through the CLI.
- Source inventory now tracks license posture and use posture for ignored `sources/` clones, including
  reference-only treatment for license-unclear sources.
- Fresh-thread current-work discovery has been hardened: `story-loop-status` is the canonical queue
  state machine, `task-current` is only the executable AFK selector, completed blockers can live on
  historical plans, worker-run IDs cannot be reassigned across tasks, and completed worker results
  now require nonempty evidence fields.
- `story-loop-status` now includes both active and blocked current-queue plans by default, so a
  successor such as Stage 6 remains visible as soon as the publication checkpoint resolves.
  Use `--all` only when historical completed, abandoned, or superseded plans are needed.
- Planning queue integrity now rejects terminal or ready task states while a nonterminal worker run
  is still attached, completed worker result paths are validated as repo-local JSON paths at write
  time, and the planning integrity gate catches the same drift if SQLite is edited out of band.
- Planning SQLite access now validates the expected schema and required indexes before CLI
  reads/writes, prevents more than one nonterminal worker run for a task, rejects nonterminal
  worker-run states on pending or terminal tasks, and rejects moving a task to another plan after
  worker history exists. `plans/planning.sqlite3` is now at planning schema version 3, including
  stronger SQLite-level status/review constraints and schema-fragment validation for critical DDL.
- Fresh-thread summary commands now expose current-queue views:
  `plan-summary --current-queue` and `task-list --current-queue-plans-only` include active and
  blocked plans, while the older active-only flags are reserved for deliberately narrow audits.
- Worker-run completion helpers auto-link completed `result_path` JSON artifacts with the
  `worker-result` relationship, so normal CLI completion no longer leaves result evidence
  half-linked.
- Planning lifecycle writes now also reject task upserts that would hide an active worker run and
  reject terminal plan states while child tasks, milestones, or acceptance criteria remain open.
- Latest bootstrap hardening also repairs stale seeded bootstrap task contracts, rejects unsafe
  ready-AFK allowed paths, surfaces task-current non-claimable reasons, permits intentional rework
  after completed worker evidence when the task is explicitly set back to `ready`, validates Story
  Loop task/run references, and gives mutating skills explicit read-only/review-only guards.
- Open AFK tasks on active or blocked plans must already have executable contracts. This prevents a
  blocked future task from carrying cacheful or unsafe verification commands until the moment it is
  unblocked.
- Worker result evidence is now stricter: completed runs must record structured zero-exit
  `tests_run`, exact acceptance-criterion evidence, changed files within task `allowed_paths`, and
  verification commands that pass the safe-command parser. Completed worker JSON evidence now also
  rejects cache-writing `tests_run` commands and unsafe task verification commands. Worker JSON
  evidence must identify the covered run with `worker_run_id` or, for intentionally shared
  synthesized evidence, `worker_run_ids`; each shared entry must be a completed worker run pointing
  at the same `result_path`. The `result_path` artifact link must use relationship `worker-result`,
  and its own `result_path` must appear in the JSON `changed_files` and `artifacts` lists.
  `tests_run` summaries must be nonblank and avoid stale pass phrasing.
- `scripts/check_file_justification.py` syntax was repaired after the UTF-8 gate addition, and
  completed worker-result acceptance evidence can no longer be a bare boolean.
- Verification-command parsing now rejects cacheful pytest, Ruff, and mypy commands in worker-result
  evidence, permits only read-only `codex_supervisor.cli` module commands, and requires cache-free
  forms such as `python -B -m pytest -p no:cacheprovider`, `ruff ... --no-cache`, and
  `mypy --no-incremental`.
- File-purpose justification now treats `manual review` as a narrow `HANDOFF.md` verifier only and
  fails stale manifest entries for files that no longer exist.
- Source inventory checks now compare exact canonical upstream URLs, including normalized HTTPS and
  SSH GitHub remotes, so prose such as secondary upstream notes cannot masquerade as the pinned
  source URL.
- Public/file gates now reject invalid UTF-8 public text candidates and staged text blobs instead of
  silently skipping them.
- Plan commit links now require full 40-character lowercase hexadecimal SHAs; historical short SHA
  rows in `plans/planning.sqlite3` have been normalized so commit evidence remains unambiguous to
  fresh threads and automation.
- Repo-local skills now clarify strict read-only/review-only behavior, distinguish current Stage 5
  Story Loop support from the future Stage 6 Codex Exec backend, and route full spawned-project
  scaffolds to `spawned-project-bootstrap`.
- The verification runner disables pytest, Ruff, mypy, and Python bytecode caches so routine checks
  do not leave hidden cache artifacts.
- `scripts/verify.py` now includes CLI import and no-sync console-script smoke checks:
  `uv run python -B -m codex_supervisor.cli --help` and
  `uv run --no-sync codex-supervisor --help`.
- The Stage 6 Codex Exec backend successor is recorded durably as
  `plan-stage6-codex-exec-backend`. After ACP commit `e422e16` and queue reconciliation commit
  `a024555`, its design task is now the next ready AFK task.
- Latest six-lane follow-up hardening tightened skill mutation guards, made Codex Exec decision
  wording explicit about Stage 6, added the Matt Pocock MIT skill reuse decision, made worker-result
  snapshot evidence date-bound, and linked remaining checkpoint artifacts in planning SQLite.
- Verification-command safety now rejects direct pytest forms that can still write Python bytecode;
  use `python -B -m pytest ...` or `uv run python -B -m pytest ...` for AFK task contracts and
  worker-result evidence.
- `check_protected_files.py` now reports untracked protected files and hash mismatches together, so
  ACP can see all lock work in one run.

Implementation checks last passed in a clean worktree on 2026-05-24 at HEAD `a024555` with:

- `uv run python -B scripts/verify.py`
- `uv run python -B scripts/verify.py --publication-ready`

Both commands passed after ACP and planning queue reconciliation. They cover 217 tests, Ruff, format
check, mypy, CLI smoke checks, file justification, public hygiene, planning integrity, skill
inventory, source inventory, protected locks, and `uv lock --check`.

## Next Recommended Session Prompt

````text
Use the codex-supervisor skill. If that skill is not listed in the active Codex session, read
`.agents/skills/codex-supervisor/SKILL.md` directly and follow it as the repo-local fallback.

Read the minimum stable orientation set first: README.md, AGENTS.md, PLANS.md, and
insights/README.md. Do not read mutable HANDOFF.md or bulk-read historical audits before inspecting
the live queue.

Inspect plans/planning.sqlite3 through the existing typed planning helpers and summarize active
plans, decisions, progress events, and next tasks. Use:

```sh
uv run codex-supervisor story-loop-status --json
uv run codex-supervisor task-current --json
uv run codex-supervisor task-list --current-queue-plans-only
uv run codex-supervisor plan-summary --current-queue
```

Use `story-loop-status --json` as the queue state machine. `task-current --json` is only the AFK
execution selector; if it returns `null` while `story-loop-status` says `hitl`, use the
`current_task_id` from `story-loop-status` and inspect it with `task-show <current_task_id> --json`.

After the live task is known, read only the source-of-truth docs and insight files relevant to that
task. Use `insights/README.md` as the index. Historical audit files such as
`insights/bootstrap-landmine-audit.md` are evidence, not mandatory orientation.

If fallback read-only SQLite inspection reveals `ready` tasks attached to completed, abandoned,
superseded, or otherwise historical plans, treat those rows as historical or drift evidence. Blocked
plans remain current-queue plans, but their ready AFK tasks are not executable until the plan or task
blocker is resolved. Do not report historical rows as the current task unless the user explicitly
asks for historical backlog rows or reopens the plan.

Snapshot only:

As of this handoff snapshot, the expected state is `queue_state: "ready"` with current task
`task-stage6-codex-exec-backend-design` under active plan `plan-stage6-codex-exec-backend`. The
bootstrap publication checkpoint is completed and linked to ACP commit `e422e16`; queue
reconciliation is commit `a024555`. If the database reports a different state, trust the database and
call out this handoff as stale.

ROADMAP Stage 5 is implemented locally. Begin from the current database state rather than from stale
handoff prose.

Until ROADMAP Stage 6 is implemented, `worker_backend=codex_exec` is a planned backend label rather
than an automatic launcher. Execute ready AFK tasks in the supervised thread, in an explicitly
created worktree, or through a hand-authored fresh-context worker prompt.
````

## Current Implementation Focus

The next implementation focus should come from `story-loop-status` and `task-current`, not handoff
prose. At this snapshot, the next action is the Stage 6 Codex Exec backend design/contract task.
Stage 5 Goal Contract and Story Loop support is implemented locally; preserve or extend it only when
the active database task requires that.

Stage 1 is historical context: the planning database can be inspected and mutated through typed
helpers and CLI commands, including plan, milestone, and criterion creation; lifecycle/status
transitions; decisions; progress events; artifact links; commit links; supervisor tasks; and worker
runs.

Stage 9, the Codex local state adapter and automation bridge, is documented but should wait until the
planning core can accept reconciled observations cleanly.

Goal Contracts and Story Loop support are the completed bridge before the Codex Exec backend. Keep
task and worker-run records as the operational bridge between planning SQLite and native Codex Goals
or prompt-only Goal Contracts.

## Important Constraints

- Do not vendor source clones from `sources/`.
- Keep the project cross-platform.
- Treat dangerous/full-auto operation as the intended production mode.
- Preserve the split between durable source of truth, operational SQLite state, local Codex
  telemetry, and generated run artifacts.
- Treat local `~/.codex` databases as read-only observational inputs.
- Use official Codex automation tooling for recurring jobs, reminders, monitors, and thread wakeups.
- Do not edit locked source-of-truth documents unless the current-queue plan requires it; update
  `scripts/check_protected_files.py` after intentional protected-doc changes.
