# AGENTS.md

## Repository Purpose

This repository builds `codex-supervisor`: a Python-first control plane for coordinating
fresh-context Codex workers, worktrees, checks, reviews, handoffs, skills, and project source of
truth until production-quality code is produced. The current repo implements planning, Goal
Contracts, Story Loop state, verification gates, skills, and handoff doctrine; automatic Codex Exec
worker launch is still a planned backend.

The product is not a replacement for Codex. It is a durable orchestration layer around Codex.

## Operating Principles

- Treat source-of-truth files as contracts, not scratchpads.
- Prefer repo-owned state over chat memory.
- Prefer fresh-context worker runs over bloated long sessions.
- Prefer Goal Contracts over open-ended "keep going" prompts.
- Prefer one-story loops over broad unattended execution.
- Prefer structured outputs over prose-only completion.
- Prefer vertical-slice tasks over horizontal layer work.
- Prefer worktrees over direct edits for unattended implementation.
- Prefer deterministic checks before automated review.
- Prefer skill updates and knowledge-graph updates when a workflow lesson repeats.

## Dangerous Full-Auto Assumption

The intended production mode is trusted, local or controlled-runner full-auto operation. Do not design
around frequent human approval prompts. Design around isolation, auditability, checks, and review.

## Source Of Truth

Locked top-level documents and guard files:

- `.gitignore`
- `.gitattributes`
- `README.md`
- `AGENTS.md`
- `PLANS.md`
- `ARCHITECTURE.md`
- `CONTRACTS.md`
- `ROADMAP.md`
- `SOP.md`
- `TESTING.md`
- `DECISIONS.md`
- `LICENSE`
- `ATTRIBUTIONS.md`

Mutable handoff document:

- `HANDOFF.md`

Do not edit locked source-of-truth documents unless the user explicitly asks or a current-queue plan
says the edit is required. After an intentional edit, update `scripts/check_protected_files.py` with
new hashes.

Operational planning state belongs in `plans/planning.sqlite3`. Use typed helpers in
`codex_supervisor.planning`; do not scatter ad hoc SQL across the project.

Local Codex databases under `~/.codex` are read-only telemetry inputs. Do not write directly to
Codex internal SQLite databases. Reconcile observations into project-owned planning SQLite, and use
official Codex automation tooling for recurring jobs, reminders, monitors, and thread wakeups.

Native Codex Goals are execution contracts for a thread or worker. They do not replace planning
SQLite as the canonical project queue. Official guidance, indexed in `insights/source-index.md`,
says Goals require a Goals-capable Codex build and are managed through commands such as `/goal`,
`/goal pause`, `/goal resume`, and `/goal clear`. Before depending on `/goal`, run
`codex --version`, verify the worker uses the intended `CODEX_HOME`, and confirm Goals are visible
or enabled. If `/goal` is missing on a Goals-capable build, official OpenAI guidance says to enable
this feature gate in
`${CODEX_HOME}/config.toml`:

```toml
[features]
goals = true
```

or run `codex features enable goals`. Treat the config edit and CLI feature command as setup
mutations: use them only when Goal Mode setup is explicitly in scope and writes to the intended
Codex home are allowed. Restart or start a fresh Codex session only if the running process does not
pick up the config change. If Goals are not available, render the Goal Contract into the prompt
instead.

If `codex --version` fails from a Windows shell because the resolved executable is inaccessible,
treat native Goal Mode as unavailable for that worker and use the prompt-rendered Goal Contract
fallback until the CLI path and `CODEX_HOME` are confirmed.

When designing or launching Stage 6 noninteractive workers, record the Goal Mode preflight evidence
in worker metadata: resolved Codex executable, version output, intended `CODEX_HOME`, config path and
feature state, whether the backend has an official noninteractive native-goal path, and the
prompt-rendered fallback decision.

Synthesized durable learning belongs in `insights/`. Do not bury reusable workflow lessons only in
chat, logs, or worker summaries.

## Common Commands

Use `uv` for local development:

```sh
uv sync --dev
uv run python -B scripts/check_protected_files.py
uv run python -B scripts/verify.py
```

`uv sync --dev` writes dependency state; skip it during read-only orientation unless dependencies
are already present.

Planning:

```sh
uv run codex-supervisor story-loop-status --json
uv run codex-supervisor task-current --json
uv run codex-supervisor task-list --current-queue-plans-only
uv run codex-supervisor plan-summary --current-queue
uv run codex-supervisor plan-list
```

Use read-only planning inspection commands for orientation. `story-loop-status` is the queue state
machine for ready, running, HITL, blocked, completed, and empty states across active and blocked
current-queue plans by default; `--all` adds completed, abandoned, and superseded history.
`task-current` selects only executable AFK work. Inspect `story-loop-status --json` first, then use
`task-show <current_task_id> --json` whenever a current task ID is present. If
`task-current --json` returns `null`, do not conclude there is no task until the JSON status reports
`completed` or `empty`. Use `plan-init` only when intentionally creating or migrating the tracked
database.

Use `--active-only` and `--active-plans-only` only for deliberately narrow audits of currently active
plans. Fresh-thread orientation should prefer the current-queue flags so blocked successors remain
visible.

`uv run` can create or update local dependency/cache state when the environment is missing. In
strict read-only or review-only mode, use it only when dependencies are already present; otherwise
report that typed CLI orientation needs dependency setup, and fall back to existing command output,
Git state, or read-only SQLite inspection.

## Coding Rules

- Keep the supervisor core Python-first and cross-platform.
- Use `pathlib.Path` for filesystem paths.
- Keep side effects at boundaries; core planning, task, lock, and adapter logic should be testable
  without launching Codex.
- Prefer standard library until a dependency clearly earns its place.
- Add abstractions only at real seams: worker backends, project adapters, source adapters, queue
  stores, and result sinks.
- Never hardcode Windows-only path separators in core code.
- Use structured data models for task/result contracts.
- Preserve raw worker evidence: prompts, JSONL, stderr, stdout, diffs, checks, reviews, timing, and
  final structured result.

## Project Adapters

Initial adapter targets:

- `nlp-stock-prediction`: planning SQLite adapter.
- `observe-safety-monorepo`: markdown plan adapter and validation command adapter.
- `codex-subagent-testing`: harness/config/prompt adapter.
- `tech-resume`: insights knowledge graph adapter.
- generic repos: `AGENTS.md`, `PLANS.md`, `TASKS.json`, checks, and source docs.

## Definition Of Done

- The requested behavior is implemented or explicitly documented as staged future work.
- Focused tests cover changed behavior.
- Relevant checks pass.
- Source-of-truth docs are updated only when intentionally required.
- Planning SQLite records the plan, decisions, progress, and verification state.
- Handoff information is captured in `HANDOFF.md` or a plan progress record.
- No cloned `sources/` repositories, worker runs, worktrees, logs, or secrets are staged.
