# Handoff

## Current State

Repository: `codex-supervisor`

This file is a mutable fresh-thread snapshot. Treat `plans/planning.sqlite3` as canonical for active
plans, current task, task status, worker runs, progress, and execution order. Run these before using
this handoff:

```sh
git status --short --branch
git rev-parse --short HEAD
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B -m codex_supervisor.cli task-current --json
uv run --no-sync python -B -m codex_supervisor.cli plan-summary --current-queue
```

As of this snapshot, Stage 6 is complete and ACP'd, and Stage 7 is the active current-queue plan.
The expected queue state after Stage 7A completion is `completed`: no ready, running, blocked, or
HITL task remains in the current queue until the next Stage 7 slice is shaped. If the database
reports anything else, trust the database and call this handoff stale.

Recent completed ACP checkpoints:

- `3e6d1d3`: aligned fresh-thread planning bootstrap commands and handoff guidance.
- `200d027`: hardened exact task claiming, Story Loop queue snapshots, completed-plan criteria, and
  worker-result/attribution skill contracts.

The latest full local gate passed after the Stage 7A worktree-layout update with:

```sh
uv run --no-sync python -B scripts/verify.py
```

That run covered 273 tests, Ruff, format check, mypy, CLI smoke checks, file justification, public
hygiene, planning integrity, skill inventory, source inventory, protected locks, and
`uv lock --check`.

Stage 6 design changed:

- `ARCHITECTURE.md`: added the `WorkerBackend` boundary and `CodexExecBackend` responsibilities.
- `CONTRACTS.md`: added the Codex Exec Backend Contract, preflight metadata, argv command contract,
  and failure classes.
- `PLANS.md`: documented `worker_runs.metadata_json` for Codex Exec preflight/evidence.
- `ROADMAP.md`: added Stage 6A allowed paths, verification, and rollback behavior.
- `scripts/check_protected_files.py`: refreshed protected hashes for intentional doc edits.
- `plans/planning.sqlite3`: recorded Stage 6 design progress and the blocked Stage 6A successor
  task.

Stage 6A backend protocol changed:

- `src/codex_supervisor/worker_backends.py`: added launch/result models and a non-live fake backend
  that emits prompt, JSONL, stdout, stderr, final message, diff summary, and Worker Result JSON
  evidence.
- `src/codex_supervisor/worker_results.py`: added Worker Result Contract loading and validation.
- `src/codex_supervisor/planning.py`: added validated result ingestion, shared worker-run result
  membership checks, and result-status-based task/run updates.
- `src/codex_supervisor/cli.py`: routed `worker-run-status --status completed` and
  `worker-run-upsert --status completed` through Worker Result validation.
- `tests/test_worker_backends.py`, `tests/test_worker_results.py`, and `tests/test_planning.py`:
  cover fake backend evidence, result validation, CLI completion, failure/blocked/needs_review
  preservation, and shared worker-run membership.
- `insights/stage6a-backend-protocol-worker-result.json`: durable Stage 6A worker-result evidence.

Stage 6B Codex Exec preflight changed:

- `src/codex_supervisor/worker_backends.py`: added `CodexExecBackend.preflight`, executable
  resolution, `codex --version` evidence capture, WindowsApps access-denied classification, and
  shell-free `codex exec` argv construction.
- `tests/test_worker_backends.py`: covers successful preflight metadata, argv construction,
  launch-disabled no-live behavior, and inaccessible executable failure evidence.
- `insights/stage6b-codex-exec-preflight-worker-result.json`: durable Stage 6B worker-result
  evidence.

Stage 6C Codex Exec launch path changed:

- `src/codex_supervisor/worker_backends.py`: added the `launch_enabled` execution branch using an
  injected command runner. The backend now runs preflight first, avoids exec after preflight failure,
  returns `completed` only when a Worker Result JSON exists, returns `codex_exec_failed` or
  `worker_result_missing` for failure paths, and preserves prompt, stdout, stderr, JSONL,
  final-message, and diff-summary evidence.
- `tests/test_worker_backends.py`: covers launch success, nonzero exec failure, missing result
  artifact, preflight failure, launch-disabled behavior, and preservation of runner-produced JSONL
  and diff-summary files.
- `insights/stage6c-codex-exec-launch-worker-result.json`: durable Stage 6C worker-result evidence.

Stage 7A worktree and artifact layout changed:

- `src/codex_supervisor/worktree_artifacts.py`: added deterministic per-worker worktree/run/artifact
  path layout, ignored-runtime path detection, cleanup containment guards, and changed-file
  allowed-path validation that does not require files to exist.
- `tests/test_worktree_artifacts.py`: covers safe layout generation, unsafe traversal/drive/slash
  identifiers, cleanup containment, relative cleanup targets, and changed-file scope validation.
- `insights/stage7a-worktree-layout-worker-result.json`: durable Stage 7A worker-result evidence.

Important environment note: local `codex --version` and `codex exec --help` resolved to the
WindowsApps `codex.exe` path but failed with `Access is denied`. Treat live Codex Exec launch as
unavailable until the CLI path and intended `CODEX_HOME` are confirmed.

## Next Session Prompt

```text
Use the codex-supervisor skill. If it is not listed in the active Codex session, read
.agents/skills/codex-supervisor/SKILL.md directly and follow it as the repo-local fallback.

Read README.md, AGENTS.md, PLANS.md, and insights/README.md. Do not read mutable HANDOFF.md or
historical audit files before inspecting the live queue.

Inspect plans/planning.sqlite3 through typed helpers:

uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B -m codex_supervisor.cli task-current --json
uv run --no-sync python -B -m codex_supervisor.cli plan-summary --current-queue

Use story-loop-status as the queue state machine. Use task-current only as the executable AFK
selector. If queue_state is hitl or running, inspect current_task_id with task-show.

If queue_state is completed, shape the next vertical slice in planning SQLite before editing. The
likely next AFK slice is Stage 7B: connect `WorktreeRunLayout` to `WorkerLaunchRequest`
construction, worker-run metadata, and diff-summary capture through injected runners. Keep it
explicitly non-live while the local Codex CLI still fails preflight with `Access is denied`; do not
launch live `codex exec` until an accessible executable path and intended `CODEX_HOME` are
confirmed.
```

## Active Caveats

- Do not vendor ignored `sources/` clones.
- Keep the project cross-platform.
- Treat local `~/.codex` databases as read-only observational inputs.
- Treat native Codex Goals as execution contracts, not as the canonical queue. If `/goal` is not
  visible on a Goals-capable build, official Codex docs say to enable `[features] goals = true` in
  `${CODEX_HOME}/config.toml` or run `codex features enable goals`; do this only when Goal Mode setup
  and writes to that Codex home are in scope.
- Update protected source-of-truth hashes after intentional edits to locked files.
