# Live Smoke Lessons

This file captures reusable lessons from the todo-list supervisor smoke investigation, the e2e
coverage follow-up, and the broader live Codex Exec smoke run on 2026-05-28. It is durable learning,
not live queue state. Current work still belongs in `plans/planning.sqlite3`.

## Claims

### Real Live Smokes Catch A Different Class Of Bugs

- `claim`: Deterministic e2e tests can prove the supervisor flow, but real Codex Exec smokes are
  still required for API, CLI, sandbox, and model-facing schema behavior.
- `confidence`: confirmed
- `evidence`: `plan-e2e-test-gap-closure-20260528`,
  `plan-broader-live-smoke-20260528`, `tests/test_story_loop_e2e.py`,
  `tests/test_mcp_stdio.py`, and the live worker runs `run-live-codex-smoke`,
  `run-live-codex-smoke-retry`, and `run-live-codex-smoke-danger` recorded in planning progress.
- `scope`: release-readiness, supervisor worker launch, Desktop plugin, and Story Loop validation.
- `supersedes`: relying on fake Codex workers as sufficient evidence for live execution.
- `next action`: Keep deterministic e2e tests in CI, then run narrow live smokes only for the
  behavior those tests cannot observe.

### Stage Smokes Before Spending On A Full App

- `claim`: A narrow ladder of smokes avoids wasting time and tokens on another full spawned app:
  installed plugin/profile smoke, mutating MCP or stdio smoke, fake-Codex Story Loop e2e, then a
  disposable real Codex worker smoke.
- `confidence`: confirmed
- `evidence`: user request to avoid a sixteenth todo app, `scripts/verify_codex_plugin_install.py`,
  `tests/test_mcp_stdio.py`, `tests/test_story_loop_e2e.py`, and
  `plan-broader-live-smoke-20260528`.
- `scope`: diagnosing supervisor/plugin readiness before a broader spawned-project run.
- `supersedes`: using a full todo-list app as the first signal after every supervisor change.
- `next action`: Treat a full spawned app as a final confidence check, not the first regression
  harness.

### Supervisor Monitoring Needs Raw Evidence

- `claim`: The supervisor can accurately monitor workers only when each launch preserves prompt,
  stdout, stderr, JSONL events, liveness, diff summary, raw Worker Result, normalized Worker Result,
  and an evidence manifest.
- `confidence`: confirmed
- `evidence`: `src/codex_supervisor/worker_backends.py`,
  `src/codex_supervisor/story_loop.py`, `tests/test_worker_backends.py`,
  `tests/test_story_loop_e2e.py`, and `run-live-codex-smoke-danger`.
- `scope`: Codex Exec workers, async Story Loop controllers, live review workers, and release
  evidence.
- `supersedes`: prose-only worker completion or lossy controller summaries.
- `next action`: Keep liveness and evidence-manifest checks in both fake and live smoke paths.

### Strict Output Schemas Must Match The Live API Dialect

- `claim`: Local JSON Schema validation is not enough for `codex exec --output-schema`; strict
  structured-output objects must list every property in `required`, with optional semantics modeled
  by nullable values.
- `confidence`: confirmed
- `evidence`: `plan-broader-live-smoke-20260528` failed with `invalid_json_schema` for
  `browser_smoke_results.items.required`, then `src/codex_supervisor/worker_backends.py` and
  `tests/test_worker_backends.py` were updated.
- `scope`: model-facing Worker Result and Review Result schemas.
- `supersedes`: schemas where optional object keys exist in `properties` but not in `required`.
- `next action`: Add strict-schema traversal assertions for every model-facing schema generator.

### Keep Semantic Validation Stricter Than The Model Schema

- `claim`: The model-facing schema should be API-compatible, while repo-side validators should keep
  the real contract semantics, such as nonblank strings, bounded browser-smoke commands, existing
  support artifacts, and required browser smoke when task scope demands it.
- `confidence`: confirmed
- `evidence`: `src/codex_supervisor/worker_results.py`,
  `src/codex_supervisor/worker_orchestration.py`, `tests/test_worker_results.py`, and
  `tests/test_worker_orchestration.py`.
- `scope`: Worker Result ingestion and promotion.
- `supersedes`: putting every semantic rule into the model schema.
- `next action`: Keep schema generation and ingestion validation tested separately.

### Worker Result Claims Need Event Evidence

- `claim`: A live Worker Result can claim commands, acceptance, or file state that the worker never
  actually observed; the controller should cross-check completed claims against JSONL tool events
  and worktree state before treating them as evidence.
- `confidence`: confirmed
- `evidence`: `plan-multiturn-live-smoke-20260528`, `run-live-multiturn-turn2`,
  `run-live-multiturn-turn2-retry`, and `run-live-multiturn-turn2-simple`. The compound retries
  self-blocked before tool use, while the simplified retry emitted a passing Worker Result without
  command-execution events and without the requested marker present in `smoke.txt`.
- `scope`: live Codex Exec workers, Story Loop polling, Worker Result ingestion, and multi-turn
  smoke tests.
- `supersedes`: treating the final structured Worker Result as sufficient proof that listed
  verification commands ran or that acceptance evidence was observed.
- `next action`: Add a live-evidence gate that reconciles `tests_run` and acceptance claims against
  JSONL command/file events and git worktree inspection, then cover the failure with e2e tests.

### Declared Support Artifacts Are Not Product Edits

- `claim`: Browser and worker support artifacts under `artifacts/` must be copied and preserved, but
  declared support artifacts should not count as product changed-path violations.
- `confidence`: confirmed
- `evidence`: `plan-e2e-test-gap-closure-20260528`,
  `src/codex_supervisor/worker_orchestration.py`, `tests/test_story_loop_e2e.py`, and
  `tests/test_worker_backends.py`.
- `scope`: allowed-path validation for Codex Exec and Story Loop worker results.
- `supersedes`: treating all worktree `artifacts/` writes as product code changes.
- `next action`: Continue recording ignored support artifacts in validation metadata so reviewers can
  audit the distinction.

### Windows Workspace-Write Needs A Live Probe

- `claim`: On the observed Windows Codex CLI path, `codex exec --sandbox workspace-write` accepted
  the flag but rejected write commands as read-only; `danger-full-access` could write in the same
  disposable worktree.
- `confidence`: confirmed
- `evidence`: direct `codex exec` probes and supervised runs recorded under
  `plan-broader-live-smoke-20260528`.
- `scope`: Windows live Codex Exec launches through `codex.cmd`.
- `supersedes`: assuming `workspace-write` is writable because the CLI accepts the argument.
- `next action`: Add a bounded write-capability preflight before supervised `workspace-write` worker
  launches on Windows, or explicitly select isolated `danger-full-access` for trusted local
  full-auto smokes.

### Full-Auto Safety Comes From Isolation And Auditability

- `claim`: For trusted local full-auto, the safer production posture is disposable repos, worktrees,
  allowed paths, strict evidence, and review, rather than frequent approval prompts.
- `confidence`: confirmed
- `evidence`: `AGENTS.md`, `TESTING.md`, `plan-broader-live-smoke-20260528`, and the successful
  `danger-full-access` live worker smoke.
- `scope`: Codex-supervisor live worker execution and spawned-project smoke tests.
- `supersedes`: treating human approval prompts as the main safety boundary for supervised workers.
- `next action`: Keep dangerous modes isolated to disposable or scoped worktrees with recorded
  evidence and publication checks.

### Planning Evidence Must Be Public-Hygiene Safe

- `claim`: Planning progress can become tracked public evidence, so it must not include local
  absolute paths, user home paths, credentials, or private transcript excerpts.
- `confidence`: confirmed
- `evidence`: `scripts/check_public_repo_hygiene.py` rejected absolute temp paths in
  `plans/planning.sqlite3`; the evidence was rewritten to redacted disposable-workspace wording.
- `scope`: planning SQLite progress, handoffs, insights, release evidence, and ACP.
- `supersedes`: treating planning SQLite as private chat scratch space.
- `next action`: Use repo-relative artifact IDs, worker run IDs, commit SHAs, and redacted
  descriptions in durable records.

### Close Smoke Plans Before Publication Checks

- `claim`: A smoke-tracking plan left active without executable tasks, milestones, or criteria will
  fail planning integrity even if the external smoke succeeded.
- `confidence`: confirmed
- `evidence`: `scripts/check_planning_integrity.py` flagged
  `plan-broader-live-smoke-20260528` until the plan was completed after evidence recording.
- `scope`: ad hoc validation plans, live-smoke plans, and ACP preparation.
- `supersedes`: leaving temporary tracking plans active after the smoke completes.
- `next action`: Record completion or blocker state in planning SQLite before running
  publication-ready verification.

### Controller And Worker Roles Must Stay Separate

- `claim`: Product workers should edit product-scoped allowed paths and return Worker Result JSON;
  the controller owns planning SQLite, review task creation, promotion, source locks, and final
  completion records.
- `confidence`: confirmed
- `evidence`: todo-list smoke RCA plans, `src/codex_supervisor/story_loop.py`,
  `src/codex_supervisor/worker_orchestration.py`, and Worker Result prompt text in
  `src/codex_supervisor/worker_backends.py`.
- `scope`: Story Loop execution, spawned projects, and review/promotion flows.
- `supersedes`: letting product workers repair supervisor scaffolding or planning state while doing
  product work.
- `next action`: Keep controller-owned paths blocked unless the task role explicitly authorizes
  controller/planning/promotion/source-lock work.

### Fresh-Context Workers Need Complete But Bounded Context

- `claim`: Workers need enough task and source context to avoid false blockers, but not broad chat
  history; missing optional root docs in disposable smokes should be either supplied deliberately or
  framed as nonessential.
- `confidence`: inferred
- `evidence`: `run-live-codex-smoke-danger` completed while noting absent root context docs in its
  Worker Result risk list.
- `scope`: disposable live smokes and spawned-project bootstrap tests.
- `supersedes`: assuming every smoke repo must include the full source-of-truth document set.
- `next action`: For minimal live smokes, make the prompt explicit that absent root docs are expected
  unless the task depends on them.

### Handoff Is A Snapshot, Not A Ledger

- `claim`: `HANDOFF.md` should name the latest useful checkpoint and current risks, while detailed
  history and worker evidence remain in planning SQLite and artifacts.
- `confidence`: confirmed
- `evidence`: `AGENTS.md`, `HANDOFF.md`, `plans/planning.sqlite3`, and repeated planning integrity
  checks during this conversation.
- `scope`: thread resumption, ACP, and long-running supervisor work.
- `supersedes`: copying operational history into protected docs or handoff prose.
- `next action`: Keep handoff compact after each plan, and use planning SQLite for detailed
  evidence.

### ACP Is Part Of The Evidence Loop

- `claim`: ACP for this repo is not just `git add && git commit && git push`; it includes scoped
  staging, staged-diff inspection, public hygiene, planning integrity, publication-ready
  verification, and commit-link evidence when applicable.
- `confidence`: confirmed
- `evidence`: `acp-publisher` skill, `plan-e2e-test-gap-closure-20260528`, prior ACP commits, and
  `scripts/verify.py --publication-ready`.
- `scope`: public checkpoints for code, planning evidence, handoff, and insight updates.
- `supersedes`: publishing without checking staged files or public evidence posture.
- `next action`: Continue running publication-ready verification after staging and before commit.
