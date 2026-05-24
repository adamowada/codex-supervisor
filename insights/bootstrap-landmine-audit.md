# Bootstrap Landmine Audit

Confidence: confirmed.

## Evidence

- Six read-only explorer lanes audited repo shape, Python code and tests, skills, source-of-truth
  docs, planning SQLite, and the fresh-thread bootstrap path.
- Component checks passed after fixes. Earlier pre-ACP snapshots intentionally stopped at the
  protected-file/publication checkpoint until intended public files were tracked; current
  publication-ready status is summarized in `Recently Fixed And Verified`.
- Read-only SQLite drift checks passed for current-queue plans with pending criteria, missing
  artifact links, parent-plan timestamps, integrity, and foreign keys.

## Fixed Landmines

- `HANDOFF.md` now follows `plans/planning.sqlite3` for execution order instead of telling fresh
  threads to rerun a completed audit.
- `planning-sqlite-operator` now states that planning SQLite beats stale handoff prose.
- `task-current` no longer crashes in text mode when the queue has no current AFK task.
- `plan-init --seed-bootstrap-plan` no longer reactivates existing bootstrap work.
- The current Stage 1 task now names the remaining work: lifecycle mutation helpers and write-side
  planning CLI commands.
- Goal Contract and Story Loop pending criteria now have blocked task rows instead of living only as
  plan criteria.
- Child planning mutations now update parent `plans.updated_at`.
- Goal-mode preflight now includes `codex --version`, intended `CODEX_HOME`, `/goal` visibility, and
  feature enablement fallback.
- Rendered Goal Contracts now include the documented contract fields, source-authority metadata,
  native Goal Mode preflight, and prompt-only fallback.
- Story Loop status now distinguishes ready AFK, HITL, blocked, completed, and empty states.
- Story Loop progress and artifact links are recorded together through one typed planning helper.
- Completed task dependencies no longer block next-ready selection forever.
- The top-level `codex-supervisor` skill now has a fresh-thread bootstrap contract.
- Corrupted triage brief text and the diagnose HITL helper contradiction were corrected.
- Skill routing landmines were tightened: planning SQLite authority is now an authority matrix,
  PR/CI inspection is inspect-only by default, and worker-launch wording no longer implies the
  Stage 6 backend exists.
- Always-read bootstrap docs now spell out the native Goals recovery path:
  `[features] goals = true`, `codex features enable goals`, and a fresh/restarted Codex session
  only when the running process does not pick up the config change.
- Fresh-thread bootstrap now requires `story-loop-status --json` before interpreting
  `task-current --json`, and `hitl` state now leads to `task-show <current_task_id> --json`.
- Child skills now share the authority matrix: locked docs govern durable doctrine, while planning
  SQLite and `story-loop-status` govern active queue state and execution order.
- `scripts/verify.py --publication-ready` now runs the full default suite plus the stricter public
  index gate, so ACP guidance can invoke one command.
- Publication hygiene does not publish ignored `sources/<name>` clone artifacts. The tracked
  `sources/README.md` inventory documents how to recreate local clones, while publication-ready
  checks require linked planning artifacts to be tracked files unless they are external URLs.
- `scripts/check_planning_integrity.py` now makes SQLite drift checks part of the default local
  verification suite, including queue-state drift, invalid statuses, missing worker evidence, and
  missing progress artifact links.
- `scripts/check_file_justification.py` now makes every public candidate file and folder match an
  intentional bootstrap purpose category and rejects empty public text files.
- `story-loop-status --json` now exposes top-level `queue_state`, `current_task_id`,
  `current_hitl_task_id`, and `current_afk_task` so HITL queues are not mistaken for no work.
- AFK readiness now requires acceptance criteria, verification commands, allowed paths, active plan
  state for execution, ready task state, and resolved blockers through one shared predicate.
- Planning progress with a `linked_artifact_id` now creates an artifact link, and completed worker
  runs require a result path before the typed store accepts them.
- Fresh-thread docs and skills now treat any hardcoded HITL task ID as a mutable handoff snapshot,
  make the setup-agent-docs skill lightweight-only, route orphaned safety/provenance/eval skills,
  and require the full publication gate for ACP.
- `scripts/check_skill_inventory.py` now guards repo-local skills against missing frontmatter,
  folder/name drift, route-map orphaning, and prohibited tool-family references.
- Goal Mode docs now treat `[features] goals = true` and `codex features enable goals` as official
  Codex guidance, while preserving prompt-rendered Goal Contracts as fallback.
- Story Loop status now uses the same AFK execution predicate for plan-scoped and global queue
  selection, excludes tasks that already have a non-terminal or completed worker run, and reports a
  clear error for inactive or missing `--plan-id` filters.
- Worker runs can now be completed with `worker-run-status --result-path` without destructive
  full-record upsert.
- Source inventory, skill inventory, and planning integrity checks now catch row-level source
  mismatches, prohibited skill support-file drift, malformed planning JSON, incomplete current-queue
  plans, incomplete criteria on completed plans, weak ready-AFK contracts, and unlinked completed
  worker-run results.
- Protected source-of-truth checks now require protected files to be tracked by git, not merely
  present with the expected hash in the working tree.
- `task-upsert` and `worker-run-upsert` now preserve omitted optional contract/evidence fields by
  default, with `--replace` reserved for intentional full replacement.
- Completed worker runs now require their `result_path` to exist on disk, and JSON result files are
  checked against the Worker Result Contract field set and status vocabulary.
- Completed worker runs now require repo-local JSON result paths, not URLs, absolute paths, escaped
  paths, or markdown reports masquerading as structured worker evidence.
- Worker-run evidence is exposed through read-only CLI commands and `plan-summary --json`.
- Planning helper and CLI status validation now reject unknown milestone, criterion, and worker-run
  statuses.
- Worker-run status changes now sync the owning supervisor task and parent plan timestamps, so
  completed review-required work surfaces as HITL review instead of staying `running`.
- `story-loop-status` now reports HITL and running tasks in `current_task`, treats review states as
  HITL rather than running, and resolves blockers across plan boundaries.
- `story-loop-status` now includes active and blocked current-queue plans by default. This keeps
  blocked successors, such as the Stage 6 Codex Exec backend plan, visible after the active HITL
  checkpoint closes instead of making a fresh thread think the queue is empty.
- Task contract arrays now reject non-string or blank values at typed-helper boundaries, while the
  integrity checker reports corrupt historical rows without requiring ad hoc SQL.
- Source inventory checks now verify license posture, use posture, unexpected source directories,
  non-git source directories, dirty local clones, documented remotes, and pinned commits.
- Repo-local skill inventory checks now reject prohibited references case-insensitively.
- Planning structure can now be created through typed CLI commands for plans, milestones, and
  criteria, and commands that cannot infer the planning database path fail with a clean recovery
  message instead of a stack trace.
- The HITL publication checkpoint was encoded as read/report-only until the user approved ACP, then
  completed through the published checkpoint flow.
- A follow-up six-lane audit found the tracked database was missing the newer
  `idx_worker_runs_one_nonterminal_per_task` partial unique index even though fresh schema SQL
  created it. Schema validation now verifies required indexes, schema version was bumped to 2, and
  `plans/planning.sqlite3` records both migrations. A later schema version 3 migration tightened
  status/review constraints and validates critical DDL fragments directly.
- The planning store now rejects nonterminal worker-run states for tasks that are pending or
  terminal. Reruns must explicitly reopen the task before clearing terminal run evidence.
- `scripts/check_file_justification.py` had a Python 2-style `except` clause after the UTF-8 gate
  addition; the syntax is corrected and covered by the focused and broad test suites.
- Completed worker-result `acceptance_results` can no longer use bare `true`; each task criterion
  needs an object with passing status and nonblank evidence.
- Protected docs and skills now avoid stale bootstrap claims: worker-result examples use timeless
  summaries, `SOP.md` says automatic fresh-worker launch waits for Stage 6, Goal Mode setup requires
  an explicit in-scope action, and read-only/audit guards were tightened in key skills.
- `planning-sqlite-operator` now says fallback SQL rows on completed, abandoned, superseded, or
  otherwise historical plans are historical/drift evidence, not the current task. Fresh threads
  should start with `story-loop-status --json`, then use current-queue task helpers before reading
  all history.
- Verification-command evidence is now cache-safe and non-mutating: cacheful pytest, Ruff, and mypy
  commands are rejected, `uv run` evidence must use `uv run --no-sync`, and the only permitted
  Python CLI module smoke is `python -B -m codex_supervisor.cli --help`.
- File-purpose checks now restrict `manual review` to `HANDOFF.md` and fail stale manifest entries
  for missing files.
- Source inventory checks now compare exact canonical upstream URLs, including SSH/HTTPS GitHub
  normalization. The pinned `mattpocock-node-DeepResearch` row no longer includes secondary-upstream
  prose in the URL column.
- Task upsert and plan status writes now enforce lifecycle visibility: a task cannot be upserted to
  hide an active worker run, and a plan cannot enter a terminal state while child tasks, milestones,
  or acceptance criteria remain open.
- Completed worker-result evidence now rejects cache-writing `tests_run` commands and unsafe task
  verification commands, so historical or synthesized worker proof must meet the same cache-safe
  command posture as ready AFK tasks.
- `source-lock-operator` and `ambient-suggestion-triager` now put read-only/no-mutation guards before
  commands or queue actions.
- Source clone metadata is no longer duplicated between `ATTRIBUTIONS.md` and `sources/README.md`.
  `sources/README.md` is the validated clone/license/use inventory; `ATTRIBUTIONS.md` points to it
  and focuses on reuse rules plus copied/adapted material. The source inventory gate rejects a
  duplicate source table in `ATTRIBUTIONS.md`.
- Child-skill routing is now single-source: `skill-router` is the only validated route map, and the
  top-level `codex-supervisor` skill only explains when to delegate to it.
- The placeholder `docs/README.md` was removed instead of carrying an empty public docs surface.
  Extended docs should appear only when there is real implementation material to justify them.
- The file-purpose and public-hygiene gates now filter deleted tracked files before normal public
  candidate checks, so intentional removals are checked by Git status/publication readiness instead
  of stale folder or missing-worktree failures.
- Completed AFK tasks now require completed worker evidence in planning integrity, including
  historical plans, so a status update cannot silently remove work from the queue without a result
  artifact.
- Rendered Goal Contracts now distinguish Goal Mode setup from read-only execution: config edits and
  `codex features enable goals` are allowed only when that setup is in scope; otherwise workers use
  the prompt-rendered fallback.
- Verification hardening now avoids the `uv run` sync surface for console-script smoke checks,
  disables pytest cache in `pyproject.toml`, requires adjacent `-p no:cacheprovider` tokens, and
  compiles verification scripts to catch syntax regressions early.
- Source inventory parsing now skips only structural Markdown separator rows, not legitimate rows
  whose prose contains `---`.
- Planning path discovery no longer falls back to any nearest `.git` directory. Default planning
  paths must come from a recognized supervised root, or callers must pass `--path` explicitly.
- Plan listing now orders active plans before historical high-priority plans, reducing the chance
  that a raw `plan-list` misleads a fresh thread.
- Schema validation now checks the exact partial-index predicate for the one-nonterminal-worker-run
  invariant instead of validating only the index name, columns, uniqueness, and partial flag.
- Skill inventory routing now parses only the `## Route By Intent` section with a stricter route
  grammar, so incidental prose bullets do not satisfy routing coverage.
- Spawned-project architecture review and setup-docs skills now agree on fallback documentation:
  lightweight `docs/agents` files are optional, and the full spawned scaffold can be read from
  top-level source-of-truth documents.
- Plan commit links now require full 40-character lowercase hexadecimal SHAs, and the tracked
  planning database has been normalized away from historical short SHA evidence. This keeps commit
  links durable enough for future automation and avoids ambiguous handoff provenance.
- Completed worker JSON evidence now has to identify the worker run it proves. Single-run results
  use `worker_run_id`; intentionally shared synthesized results use `worker_run_ids`, and the
  planning integrity gate verifies that each listed run is completed and points at the same
  `result_path`.
- Completed worker `result_path` artifacts now have to be linked with the explicit
  `worker-result` relationship, not merely any `plan_artifact_links` row. Supporting reports can
  still use their own relationships without satisfying result evidence accidentally.
- Open AFK tasks on active or blocked plans now have their execution contracts checked before they
  enter any open execution state. The Stage 6 Codex Exec backend task was normalized from cacheful
  `uv run pytest` to the cache-safe `uv run --no-sync python -B -m pytest -q -p no:cacheprovider`
  form.
- Completed worker-result JSON now has to list its own `result_path` in `artifacts`, making the
  evidence artifact self-describing even when read outside the planning row that points to it.
  `changed_files` stays limited to implementation or durable-documentation paths covered by the task
  `allowed_paths`.
- Completed worker-result `tests_run` summaries now have to be nonblank and avoid stale pass
  phrasing. The six-lane audit result no longer preserves pre-ACP lock failures as current passing
  evidence.
- The active Stage 6 design task now has documentation-only `allowed_paths`; implementation paths
  stay out of the executable contract until the backend design is reviewed and authorized.
- Recent handoff checkpoint commits are linked in `plans/planning.sqlite3`, so mutable handoff prose
  and durable plan evidence no longer diverge on checkpoint provenance.
- Verification-command safety now bounds read-only `codex_supervisor.cli` invocations to approved
  flags and plain identifiers; `--path` and path-like task or plan arguments are rejected.
- Pending AFK tasks on current-queue plans are allowed to remain underspecified, while ready,
  running, blocked, and reviewing AFK states still require executable contracts.
- Skill guardrails now sharpen golden-eval fixtures, preserve test coverage during architecture
  deepening, classify `HANDOFF.md` as mutable snapshot rather than doctrine, and make
  `.out-of-scope/` an opt-in triage pattern.
- `plan-summary` now reads its plan, task, worker-run, decision, progress, and link inputs through a
  single typed summary snapshot instead of assembling a report across multiple SQLite reads.
- Git-based tests that create commits now disable inherited GPG signing in their temporary repo
  config, keeping local verification independent of developer machine settings.

## Remaining Watch Items

- The Stage 6 Codex Exec backend is not implemented; `worker_backend=codex_exec` is a planned
  backend label until then.
- Public hygiene checks are useful but intentionally lightweight; consider a stronger secret scanner
  before publishing broadly.
- Several imported skills remain useful but broad. Keep tightening triggers as real bootstraps reveal
  routing noise.
- `plans/planning.sqlite3` is intentionally tracked live operational state. If future churn becomes
  noisy, consider splitting schema/seed fixtures from local runtime state, but do not do that until
  the bootstrap value of a tracked queue is replaced.

## Recently Fixed And Verified

- The bootstrap publication checkpoint was ACP'd to `origin/main`, `.gitattributes` and the new
  public bootstrap files are tracked, and the default plus publication-ready verification gates pass.
- Planning schema version 4 includes constrained-table validation, critical SQLite DDL fragments,
  status enums, `review_required` boolean constraints, and strict full-SHA commit-link constraints.
- Fresh-thread orientation now has current-queue CLI flags so blocked successor plans stay visible:
  `plan-summary --current-queue` and `task-list --current-queue-plans-only`.
- Worker-run completion helpers now auto-link completed JSON `result_path` artifacts with the
  `worker-result` relationship.
- Terminal acceptance criteria semantics now treat only `pending` and `blocked` criteria as open, so
  intentional `failed` or `cancelled` criteria do not keep a terminal plan incomplete.
- Ready AFK task selection rejects unsafe verification commands before a worker can claim the task.
- `insights/graph.md` no longer stores live queue snapshots; it points readers back to
  `story-loop-status --json` for mutable task state.
