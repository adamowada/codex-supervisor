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

As of this snapshot, Stage 10A Codex local-state inventory work is complete in planning SQLite. The
expected queue state is `completed` for active plan
`plan-stage10-codex-state-automation-bridge`, with no current AFK task until the next Stage 10 slice
is shaped. Stage 9 is marked completed in planning SQLite. If the database reports anything else,
trust the database and call this handoff stale.

Recent completed ACP checkpoints:

- `e565921`: shaped the Stage 10 Codex state inventory plan and Stage 10A task.
- `04931a8`: added Stage 9D skill promotion proposal and golden-eval evidence contracts.
- `34df19e`: shaped the Stage 9D skill promotion golden-eval contract task and handoff.
- `bf9386f`: shaped the Stage 9C guarded insight update workflow task and handoff.
- `0d7570d`: added the Stage 9B insight validation CLI and completed the Stage 9B worker-result
  checkpoint.
- `3e6d1d3`: aligned fresh-thread planning bootstrap commands and handoff guidance.
- `200d027`: hardened exact task claiming, Story Loop queue snapshots, completed-plan criteria, and
  worker-result/attribution skill contracts.

The latest full local gate passed after the Stage 10A Codex local-state inventory implementation
with:

```sh
uv run --no-sync python -B scripts/verify.py
```

That run covered 358 tests, Ruff, format check, mypy, CLI smoke checks, file justification, public
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

Stage 7B worker launch preparation changed:

- `src/codex_supervisor/worker_launches.py`: added `prepare_worker_launch_request`, which bridges
  planning task rows and Stage 7A layout into a `WorkerLaunchRequest` plus worker-run metadata
  without creating worktrees or launching Codex.
- `tests/test_worker_launches.py`: covers successful request preparation, metadata field exposure,
  no filesystem side effects, and unsafe worker-run ID rejection.
- `insights/stage7b-worker-launch-preparation-worker-result.json`: durable Stage 7B worker-result
  evidence.

Stage 7C worker orchestration changed:

- `src/codex_supervisor/worker_orchestration.py`: added `orchestrate_worker_launch`, which calls
  `prepare_worker_launch_request`, invokes a supplied backend once with the prepared request, parses
  the diff-summary evidence, validates changed files against task `allowed_paths`, and rewrites
  completed out-of-scope results to `failed` with `changed_paths_out_of_scope`.
- `tests/test_worker_orchestration.py`: covers successful injected `CodexExecBackend` execution,
  out-of-scope diff rejection, backend failure preservation with changed-path violation metadata,
  and unsafe worker-run ID rejection.
- `insights/stage7c-worker-orchestration-worker-result.json`: durable Stage 7C worker-result
  evidence.

Stage 7D worktree state snapshots changed:

- `src/codex_supervisor/worktree_state.py`: added read-only `inspect_worktree_state`, which uses
  an injected command runner and shell-free git argv to capture branch, base commit, head commit,
  dirty status paths, diff-summary paths, raw command evidence, and changed-path violations.
- `tests/test_worktree_state.py`: covers clean snapshots, dirty out-of-scope path reporting,
  `worktree_state_failed` command failure classification, and outside-workspace rejection before any
  runner invocation.
- `insights/stage7d-worktree-state-worker-result.json`: durable Stage 7D worker-result evidence.

Stage 7E cleanup and orphan planning changed:

- `src/codex_supervisor/worktree_cleanup.py`: added non-destructive `plan_cleanup_targets`, which
  validates candidate paths with `validate_cleanup_target`, classifies ignored runtime roots,
  preserves active worker-run IDs, and returns structured selected/skipped cleanup entries.
- `tests/test_worktree_cleanup.py`: covers safe orphan candidates, root/outside rejection,
  active-run preservation, unsupported runtime path skipping, and missing worker-run ID skipping.
- `insights/stage7e-cleanup-orphan-planning-worker-result.json`: durable Stage 7E worker-result
  evidence.

Stage 7F cleanup-plan dry-run CLI changed:

- `src/codex_supervisor/cli.py`: added `cleanup-plan`, a non-destructive dry-run command that
  accepts workspace root, cleanup candidates, active worker-run IDs, reason, and JSON output.
- `src/codex_supervisor/worktree_cleanup.py`: remains the single cleanup planning implementation
  used by the CLI.
- `tests/test_worktree_cleanup.py`: now covers CLI JSON output, human output, active-run skipping,
  invalid path failure, and proof that candidate directories remain on disk.
- `insights/stage7f-cleanup-plan-cli-worker-result.json`: durable Stage 7F worker-result evidence.

Stage 8A review contracts changed:

- `src/codex_supervisor/review_loop.py`: added explicit review modes, finding severities/statuses,
  `ReviewLocation`, `ReviewFinding`, waiver-rationale validation, and accepted-finding
  `RepairTaskDraft` generation.
- `tests/test_review_loop.py`: covers valid findings, invalid mode/severity/status, missing
  location, waived finding rationale enforcement, accepted repair draft generation, and non-accepted
  finding rejection.
- `insights/stage8a-review-contracts-worker-result.json`: durable Stage 8A worker-result evidence.

Stage 8B review result payload validation changed:

- `src/codex_supervisor/review_loop.py`: added `ReviewVerificationEvidence`, `ReviewResult`, and
  `validate_review_result_payload`, plus accepted/waived finding views and repair draft extraction.
- `tests/test_review_loop.py`: covers valid review result payloads, invalid payload shapes,
  verification evidence validation, invalid finding payloads, and repair draft extraction.
- `insights/stage8b-review-result-payloads-worker-result.json`: durable Stage 8B worker-result
  evidence.

Stage 8C review result persistence has been shaped:

- `plans/planning.sqlite3`: adds `task-stage8c-review-result-persistence` as a ready AFK slice,
  `milestone-stage8c-review-result-persistence`, and
  `criterion-stage8c-review-result-persistence`.
- Scope: persist validated `ReviewResult` records into planning progress and artifact links without
  launching live review workers or creating repair tasks.
- Expected focused check:
  `uv run --no-sync python -B -m pytest tests/test_review_persistence.py tests/test_review_loop.py -q -p no:cacheprovider`.

Stage 8C review result persistence changed:

- `src/codex_supervisor/review_persistence.py`: added `record_review_result`, which atomically
  stores validated `ReviewResult` evidence as a `review_result_recorded` planning progress event and
  links `review-result` plus `review-artifact` artifacts.
- `tests/test_review_persistence.py`: covers successful persistence, artifact relationships,
  invalid artifact rollback, and proof that no repair tasks are created.
- `scripts/check_file_justification.py`: records the new module, tests, and worker-result artifact.
- `insights/stage8c-review-result-persistence-worker-result.json`: durable Stage 8C worker-result
  evidence.

Stage 8D accepted finding repair routing has been shaped:

- `plans/planning.sqlite3`: adds `task-stage8d-review-repair-routing` as a ready AFK slice,
  `milestone-stage8d-review-repair-routing`, and `criterion-stage8d-review-repair-routing`.
- Scope: create deterministic focused supervisor repair tasks from accepted `ReviewResult` findings
  while preserving waived and needs-HITL findings as review evidence only.
- Expected focused check:
  `uv run --no-sync python -B -m pytest tests/test_review_repairs.py tests/test_review_loop.py -q -p no:cacheprovider`.

Stage 8D accepted finding repair routing changed:

- `src/codex_supervisor/review_repairs.py`: added `create_repair_tasks_from_review_result`, which
  creates deterministic ready AFK repair tasks from accepted `ReviewResult` findings, skips waived
  and needs-HITL findings, and rejects accepted findings without allowed paths.
- `tests/test_review_repairs.py`: covers accepted task creation, waived/HITL skipping, idempotent
  reruns, deterministic task IDs, and path/contract preservation.
- `scripts/check_file_justification.py`: records the new module, tests, and worker-result artifact.
- `insights/stage8d-review-repair-routing-worker-result.json`: durable Stage 8D worker-result
  evidence.

Stage 8E review result CLI ingestion changed:

- `src/codex_supervisor/cli.py`: added `review-result-ingest`, which loads review result JSON,
  validates it through Stage 8B contracts, records Stage 8C review progress/artifact links, and
  optionally routes accepted findings through Stage 8D repair task creation.
- `tests/test_review_cli.py`: covers persistence-only ingestion, repair routing, invalid payload
  failure, idempotent repair-task reruns, and proof that no live worker runs are launched.
- `scripts/check_file_justification.py`: records the new test and worker-result artifact.
- `insights/stage8e-review-result-cli-ingestion-worker-result.json`: durable Stage 8E
  worker-result evidence.
- Verification passed:
  `uv run --no-sync python -B -m pytest tests/test_review_cli.py tests/test_review_persistence.py tests/test_review_repairs.py -q -p no:cacheprovider`;
  `uv run --no-sync python -B scripts/verify.py`.

Stage 9A reusable insight contract validation changed:

- `src/codex_supervisor/insights.py`: added pure `InsightRecord` and
  `validate_insight_record_payload` contracts for reusable insight records with required claim,
  confidence, evidence, scope, optional supersedes, and next-action fields.
- `tests/test_insights.py`: covers valid records, markdown `next action` compatibility, invalid
  confidence labels, missing required fields, and blank string/list values.
- `scripts/check_file_justification.py`: records the new module, tests, and worker-result artifact.
- `insights/stage9a-insight-contracts-worker-result.json`: durable Stage 9A worker-result evidence.
- Verification passed:
  `uv run --no-sync python -B -m pytest tests/test_insights.py -q -p no:cacheprovider`;
  `uv run --no-sync python -B scripts/verify.py`.

Stage 9B insight validation CLI changed:

- `src/codex_supervisor/cli.py`: added `insight-validate`, which loads reusable insight JSON,
  validates it through Stage 9A `InsightRecord` contracts, and prints normalized JSON or
  human-readable output without opening planning SQLite or writing insight files.
- `tests/test_insight_cli.py`: covers normalized JSON output, markdown `next action` compatibility,
  invalid payload failure, no planning/insight file mutation, and human output.
- `scripts/check_file_justification.py`: records the new test and worker-result artifact.
- `insights/stage9b-insight-cli-validation-worker-result.json`: durable Stage 9B worker-result
  evidence.
- Verification passed:
  `uv run --no-sync python -B -m pytest tests/test_insight_cli.py tests/test_insights.py -q -p no:cacheprovider`.
  `uv run --no-sync python -B scripts/verify.py`.

Stage 9C guarded insight update workflow changed:

- `src/codex_supervisor/insight_updates.py`: added deterministic insight markdown rendering and
  stable-anchor idempotent apply behavior for validated `InsightRecord` payloads, including
  evidence, supersedes, next action, promotion criteria, and provenance sections.
- `src/codex_supervisor/cli.py`: added `insight-update`, which validates an insight JSON payload
  before rendering or applying a guarded markdown update. It prints JSON output for future updater
  tooling and does not open planning SQLite or Codex internal state.
- `tests/test_insight_updates.py`: covers deterministic render fields, idempotent temp-file apply,
  invalid-payload no-write behavior for planning/insight sentinels, and CLI JSON output.
- `scripts/check_file_justification.py`: records the new module, tests, and worker-result artifact.
- `plans/planning.sqlite3`: records Stage 9C completion through
  `worker-run-stage9c-insight-update-workflow-20260525`,
  `progress-stage9c-review-completed-20260525`, completed task, completed milestone, and completed
  criterion.
- `insights/stage9c-insight-update-workflow-worker-result.json`: durable Stage 9C worker-result
  evidence.
- Verification passed:
  `uv run --no-sync python -B -m pytest tests/test_insight_updates.py tests/test_insight_cli.py tests/test_insights.py -q -p no:cacheprovider`;
  `uv run --no-sync python -B scripts/verify.py`.

Stage 9D skill promotion golden-eval contract work changed:

- `src/codex_supervisor/skill_promotion.py`: added typed `SkillPromotionProposal` and
  `GoldenEvalEvidence` validation for skill name, motivation, provenance, rollback plan,
  changed-path scope, baseline/candidate summaries, pass/fail eval status, and reviewer or
  automated verdict rationale.
- `src/codex_supervisor/cli.py`: added `skill-promotion-validate`, a read-only CLI that validates a
  proposal JSON file and prints normalized JSON or human-readable output without writing planning,
  insight, skill, or Codex internal state.
- `tests/test_skill_promotion.py`: covers valid proposal normalization, automated verdict evidence,
  invalid provenance/rollback/path/eval payloads, CLI JSON output, human output, and invalid-payload
  no-mutation behavior against planning, skill, and insight sentinels.
- `scripts/check_file_justification.py`: records the new module, tests, and worker-result artifact.
- `plans/planning.sqlite3`: records Stage 9D completion through
  `worker-run-stage9d-skill-promotion-eval-contracts-20260525`,
  `progress-stage9d-review-completed-20260525`, completed task, completed milestone, and completed
  criterion.
- `insights/stage9d-skill-promotion-eval-contracts-worker-result.json`: durable Stage 9D
  worker-result evidence.
- Verification:
  `uv run --no-sync python -B -m pytest tests/test_skill_promotion.py -q -p no:cacheprovider`;
  `uv run --no-sync python -B scripts/verify.py`.

Stage 10A Codex local-state inventory changed:

- `src/codex_supervisor/codex_state.py`: added `inventory_codex_state`, documented local Codex
  database specs, read-only SQLite `mode=ro` opening, table-name/row-count inventories, source
  database/table provenance, source-kind inference, and nonfatal missing/unreadable database
  statuses.
- `src/codex_supervisor/cli.py`: added `codex-state-inventory --codex-home <path> --json` for
  normalized metadata output without opening planning SQLite or writing Codex internal state.
- `tests/test_codex_state.py`: covers temp Codex home inventory, table row counts, missing and
  corrupt databases, no-mutation behavior, and CLI JSON that omits private row payload values.
- `scripts/check_file_justification.py`: records the new module, tests, and worker-result artifact.
- `plans/planning.sqlite3`: records Stage 10A completion through
  `worker-run-stage10a-codex-state-inventory-20260525`,
  `progress-stage10a-review-completed-20260525`, completed task, completed milestone, and completed
  criterion.
- `insights/stage10a-codex-state-inventory-worker-result.json`: durable Stage 10A worker-result
  evidence.
- Verification:
  `uv run --no-sync python -B -m pytest tests/test_codex_state.py -q -p no:cacheprovider`;
  `uv run --no-sync python -B scripts/verify.py`.

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

If queue_state is `ready`, run `task-current --json` and execute the current AFK slice with
story-loop discipline.

If queue_state is `completed`, shape the next AFK vertical slice from `ROADMAP.md`. The likely next
slice after Stage 10A is Stage 10B: safe local-state summarization/reconciliation findings or an
official automation-bridge dry-run surface.
Keep live Codex Exec launch disabled while the local Codex CLI still fails preflight with
`Access is denied`; do not launch live `codex exec` until an accessible executable path and intended
`CODEX_HOME` are confirmed.
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
