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

### Liveness Heartbeats Must Preserve Semantic Worker Events

- `claim`: Heartbeat updates are only useful when they preserve the most recent semantic Codex Exec
  event; otherwise an active file-changing worker can look like a generic idle process.
- `confidence`: confirmed
- `evidence`: todo-list-test-16 audit, `src/codex_supervisor/worker_backends.py`,
  `tests/test_worker_backends.py`, `tests/test_story_loop_e2e.py`, and
  `scripts/check_planning_integrity.py`.
- `scope`: Codex Exec stream observation, async Story Loop polling, liveness probes, and stalled
  worker classification.
- `supersedes`: treating heartbeat-only liveness as sufficient evidence for a stall decision.
- `next action`: Keep file-change/todo/command semantic liveness fields across heartbeat writes and
  reject stalled failure records that conflict with file-change stream events.

### Full-AFK Must Not Escape Into Manual Worker Execution

- `claim`: In plugin or supervised full-AFK mode, direct/manual worker execution is a blocked state,
  not a recovery path; recovery must continue through Story Loop polling or record HITL/blocker
  evidence.
- `confidence`: confirmed
- `evidence`: todo-list-test-16 audit, `src/codex_supervisor/runtime_preflight.py`,
  `scripts/check_planning_integrity.py`, `tests/test_runtime_preflight.py`, and
  `tests/test_planning_integrity.py`.
- `scope`: Desktop plugin full-AFK, live Story Loop recovery, runtime preflight, and planning
  integrity.
- `supersedes`: launching ad hoc `codex exec` workers or implementing in the controller thread
  after a Story Loop worker appears stalled.
- `next action`: Treat `manual` and `current_thread` worker execution as preflight-blocked for
  full-AFK and require nonterminal Codex Exec runs to carry Story Loop evidence metadata.

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
- `next action`: Keep expanding the live-evidence gate beyond `tests_run` command reconciliation as
  new claim types prove risky; current regression coverage and a real Codex smoke now prove
  `tests_run` claims must be backed by matching JSONL command events.

### Evidence Matching Must Be Cross-Platform

- `claim`: Worker Result evidence matching must normalize shell wrappers and path separators before
  deciding a verification command is missing.
- `confidence`: confirmed
- `evidence`: todo-list-test-17 run `run-build-local-todo-app-20260528-0926` was rejected because
  the Worker Result reported `python -B scripts/verify.py` while PowerShell JSONL observed
  `python -B scripts\verify.py`; regression coverage now lives in
  `tests/test_worker_backends.py`.
- `scope`: Codex Exec Worker Result evidence gates, Windows shells, PowerShell command wrappers, and
  live-smoke verification command matching.
- `supersedes`: byte-for-byte command comparison between Worker Result `tests_run` entries and raw
  JSONL command text.
- `next action`: Keep adding normalization cases only when backed by observed JSONL evidence, and
  continue rejecting commands that are genuinely absent from the event stream.

### Failed Controllers Cannot Be Promoted In Place

- `claim`: A Story Loop controller result that records `status=failed` is terminal evidence for that
  worker run; later planning repair must create explicit recovery evidence, not overwrite the same
  run into completed state.
- `confidence`: confirmed
- `evidence`: todo-list-test-17 `controller.stdout.json` recorded
  `worker_result_evidence_mismatch` while the final planning row was later marked completed;
  regression coverage now lives in `tests/test_planning_integrity.py`.
- `scope`: Story Loop completion, worker-run status mutation, planning integrity, and live-smoke
  recovery.
- `supersedes`: treating post-run manual planning edits as equivalent to a successful controller
  result.
- `next action`: Keep planning integrity checking failed controller artifacts against completed
  worker-run rows, and require separate recovery tasks/results for deliberate repair.

### Product Surface Cancels Controller Worker Privileges

- `claim`: A task that declares a `product_surface` must be treated as product work even if its
  scope also contains `controller_mutation_kind`; controller-owned paths stay blocked.
- `confidence`: confirmed
- `evidence`: todo-list-test-17 launched a product todo-app task with `controller_worker` privileges;
  regression coverage now lives in `tests/test_story_loop.py`.
- `scope`: task policy, Story Loop preclaim, spawned app implementation tasks, and worker prompt
  profile selection.
- `supersedes`: using `controller_mutation_kind=controller` as an escape hatch for ordinary product
  implementation.
- `next action`: Keep controller/planning/promotion/source-lock tasks explicit and separate from
  product implementation tasks.

### Review Gates Are Durable Obligations

- `claim`: Once a review-required worker task has worker or review history, ordinary task upserts
  must not be allowed to clear `review_required`; planning integrity should also reject completed
  Codex Exec tasks that have no review requirement, explicit waiver, or controller scope.
- `confidence`: confirmed
- `evidence`: todo-list-test-18-low completed `task-build-local-todo-product` after rewriting
  `review_required=false`; regression coverage now lives in `tests/test_planning.py`,
  `tests/test_review_persistence.py`, and `tests/test_planning_integrity.py`.
- `scope`: review-required AFK work, direct live reviews, Story Loop recovery, and planning SQLite
  mutation commands.
- `supersedes`: treating the current task row as the whole review contract after worker evidence
  already exists.
- `next action`: Keep review-gate checks both at mutation time and in broad planning integrity so
  legacy or manually repaired databases fail closed.

### Promotion Paths Must Replay Evidence Hooks

- `claim`: When a blocked worker result is later promoted by controller/manual repair, promotion
  must create durable `promotion_completed`, browser-smoke progress, worker evidence artifact links,
  and final commit links; it cannot rely only on a synthesized completed Worker Result.
- `confidence`: confirmed
- `evidence`: todo-list-test-18-low had passed browser smoke, review artifacts, and a final commit,
  but planning SQLite lacked `browser_smoke_passed`, `promotion_completed`, worker evidence artifact
  links, and commit links; regression coverage now lives in `tests/test_planning_integrity.py`.
- `scope`: controller promotion, manual/HITL promotion tasks, Worker Result ingestion, browser
  smoke evidence, and ACP publication readiness.
- `supersedes`: considering post-worker verification output sufficient without replaying the same
  planning ledger hooks used by a clean Story Loop completion.
- `next action`: Prefer a typed promotion helper for controller repairs so evidence links and
  progress events are created atomically.

### Artifact Links Are Not DB Source Paths

- `claim`: Planning artifact links are repo-visible evidence references, while DB-backed Worker
  Result `source_path` values can include legacy internal source locations such as
  `worker-results/`; integrity checks must not require or create forbidden public artifact links for
  those legacy source paths, and publication hygiene must allow ignored runtime evidence links under
  `artifacts/` and `runs/` without requiring those runtime files to be staged.
- `confidence`: confirmed
- `evidence`: The test18 broad verifier exposed historical Worker Result records whose
  `source_path` values lived under `worker-results/`; the new integrity gate now skips those paths
  while still requiring artifact links for `artifacts/**` raw, normalized, and manifest evidence.
  Publication-ready verification then exposed that runtime evidence links need a hygiene exception
  because AGENTS forbids staging worker runs and artifacts.
- `scope`: planning SQLite integrity, Worker Result ingestion, artifact links, and public repo
  hygiene.
- `supersedes`: treating every Worker Result source path as a plan artifact link candidate.
- `next action`: Keep DB source references and public artifact links as separate ledgers in future
  migrations and repair helpers.

### Completed Worker Results Cannot Carry Stale Blockers

- `claim`: A completed Worker Result must not retain blocker-language risks or follow-ups copied
  from a blocked result; stale blocker text should fail at ingestion and in planning integrity.
- `confidence`: confirmed
- `evidence`: todo-list-test-18-low synthesized a completed result from a blocked raw result while
  keeping follow-ups such as required review-task creation and risks saying verification remained
  blocked; regression coverage now lives in `tests/test_worker_results.py` and
  `tests/test_planning_integrity.py`.
- `scope`: Worker Result ingestion, controller-completed result synthesis, and broad verification.
- `supersedes`: shallow-editing a blocked Worker Result into a completed Worker Result.
- `next action`: Construct promotion results from explicit completion evidence, or clear/relocate
  historical blocked notes before ingestion.

### JSON-Heavy CLI Mutations Need File Inputs

- `claim`: JSON-heavy planning mutations should offer file-based inputs so workers do not have to
  inline nested JSON through PowerShell quoting.
- `confidence`: confirmed
- `evidence`: todo-list-test-17 repeatedly failed `worker-run-upsert --metadata-json` due shell
  quote loss, and todo-list-test-18-low lost task scope after inline JSON friction;
  `worker-run-upsert --metadata-json-file` and `task-upsert --scope-json-file` now have regression
  coverage in `tests/test_planning.py`.
- `scope`: Windows CLI ergonomics, planning SQLite mutation commands, worker evidence metadata, and
  recovery flows.
- `supersedes`: relying on inline JSON as the only CLI surface for complex metadata.
- `next action`: Add file or stdin variants for other JSON-heavy mutation flags when live runs show
  recurring quoting failures.

### Display Model Names Must Resolve To CLI Slugs

- `claim`: Worker launch code must normalize Codex model display names to CLI slugs before probing
  or launching `codex exec`; otherwise a valid model such as `GPT-5.3-Codex-Spark` can be rejected
  even though its slug is available locally.
- `confidence`: confirmed
- `evidence`: todo-list-test-20-low-spark RCA found the display-name launch failed while
  `gpt-5.3-codex-spark` succeeded; regression coverage now lives in
  `tests/test_worker_backends.py`.
- `scope`: Codex Exec model selection, Desktop plugin launches, live smoke tests, and worker
  capability metadata.
- `supersedes`: passing human-facing model labels directly to the CLI.
- `next action`: Keep launch metadata recording both requested and resolved capabilities so future
  RCA can tell whether the supervisor used the intended model.

### Required Worker Capabilities Fail Closed

- `claim`: Task-scoped required worker capabilities, especially model and reasoning effort, are a
  contract: launch defaults must not override them, and CLI rejection must block the run instead of
  silently falling back.
- `confidence`: confirmed
- `evidence`: todo-list-test-20-low-spark RCA, `src/codex_supervisor/worker_launches.py`,
  `src/codex_supervisor/worker_backends.py`, `tests/test_worker_launches.py`, and
  `tests/test_worker_backends.py`.
- `scope`: Story Loop worker launch preparation, Codex Exec capability probes, live smoke
  reproducibility, and model-constrained worker fleets.
- `supersedes`: best-effort fallback when the task said a specific worker model or reasoning level
  was required.
- `next action`: Add required capability fields deliberately in task scope and treat probe failures
  as useful blocked evidence, not as permission to downgrade the worker.

### Seeded Target Projects Must Pass Integrity Before Launch

- `claim`: Fresh spawned-project seeding should be transactional for empty targets and a Story Loop
  worker must not launch until the target project's own planning integrity gate passes.
- `confidence`: confirmed
- `evidence`: todo-list-test-20-low-spark produced an invalid target queue shape before worker
  orchestration; regression coverage now lives in `tests/test_spawned_projects.py` and
  `tests/test_story_loop.py`.
- `scope`: spawned-project scaffold apply, product-slice seeding, Story Loop preclaim checks, and
  live todo-list smoke tests.
- `supersedes`: writing partial scaffold/planning state directly into a fresh target and letting
  the first worker discover structural queue defects.
- `next action`: Keep project-local `scripts/check_planning_integrity.py` as a launch preflight for
  supervisor-managed targets and publish fresh scaffolds only after local verification succeeds.

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
