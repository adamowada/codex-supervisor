# HANDOFF.md

Last updated: 2026-05-28

This file is a compact resume snapshot only. Canonical queue state, completion records, worker
evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Current queue state: empty. `story-loop-status --json` reports no current AFK, HITL, or running
  task after `plan-test18-orchestration-regressions-20260528` was completed.
- Latest completed checkpoint: `plan-test18-orchestration-regressions-20260528` added TDD
  regression coverage and fixes for the todo-list-test-18-low orchestration RCA: review-required
  tasks cannot silently drop review obligations after worker/review history exists, live review
  accepted findings now route repair instead of completing source work, planning integrity requires
  promotion/browser-smoke/worker-evidence/commit ledgers for controller promotions, Worker Result
  validation rejects stale blocker text in completed results, `task-upsert --scope-json-file` avoids
  PowerShell JSON loss, completed result ingestion auto-links repo-visible raw/normalized/manifest
  evidence while skipping legacy `worker-results/` source paths, and historical planning evidence
  was backfilled with explicit artifact links/review waivers where appropriate. Durable lessons were
  saved in `insights/live-smoke-lessons.md` and `insights/graph.md`. Full
  `uv run --no-sync python -B scripts/verify.py` passed locally.
- Previous completed checkpoint: `plan-test17-orchestration-regressions-20260528` added TDD
  regression coverage and fixes for the todo-list-test-17 orchestration RCA: Worker Result
  evidence matching now normalizes PowerShell path separator variants, planning integrity rejects
  completed Codex Exec runs that lost core raw evidence or hide a failed `controller.stdout.json`,
  product-surface tasks cannot acquire controller-worker privileges via `controller_mutation_kind`,
  `worker-run-upsert` accepts `--metadata-json-file` for PowerShell-safe metadata updates, spawned
  scaffold integrity copies include the new checks, and `insights/live-smoke-lessons.md` plus
  `insights/graph.md` record the durable lessons. Focused verification passed across
  `tests/test_worker_backends.py`, `tests/test_planning.py`, `tests/test_planning_integrity.py`,
  `tests/test_story_loop.py`, and `tests/test_spawned_projects.py`.
- Previous completed checkpoint: `plan-test16-orchestration-regressions-20260528` added regression
  coverage for the todo-list-test-16 orchestration failure mode: Codex Exec liveness now preserves
  last semantic file-change context across heartbeats, full-AFK runtime preflight blocks manual
  worker execution, Story Loop e2e polling covers a live file-change-plus-heartbeat worker, and
  planning integrity rejects nonterminal Codex Exec runs without Story Loop evidence metadata or
  stalled runs that already recorded file-change events. Durable lessons were added to
  `insights/live-smoke-lessons.md` and `insights/graph.md`.
- Previous completed checkpoint: `plan-live-evidence-gate-loop-20260528` adds a Codex Exec evidence
  gate that rejects completed worker-result claims whose `tests_run` commands were not observed in raw
  JSONL command-execution events. Regression coverage now includes backend unit coverage and a real
  CLI Story Loop e2e rejection path. A real Codex MCP Story Loop smoke,
  `run-evidence-gate-live-smoke`, passed with strict JSONL, `git_worktree` changed files, and
  matching `git status --short` command evidence. Full `scripts/verify.py` passed locally after the
  implementation.
- Previous completed checkpoint: `plan-multiturn-live-smoke-20260528` ran a broader multi-turn live
  Codex Exec Story Loop smoke against a disposable git/planning/worktree repo. Turn 1 completed and
  was promoted. The compound turn-2 retries self-blocked before tool use by treating the final
  structured-output schema as a tool-use constraint, and the simplified retry emitted a passing
  Worker Result without command-execution evidence or the requested marker in `smoke.txt`; the
  supervisor rejected that result because completed results cannot have empty `changed_files`.
  `src/codex_supervisor/worker_backends.py` now clarifies that the schema constrains only the final
  assistant message, with focused coverage in `tests/test_worker_backends.py`, but live evidence
  shows that prompt clarification alone is not enough. `insights/live-smoke-lessons.md` and
  `insights/graph.md` now record the need to reconcile Worker Result claims with JSONL/tool events
  and inspected worktree state.
- Previous completed checkpoint: `plan-live-smoke-insight-acp-20260528` added
  `insights/live-smoke-lessons.md`, linked it from the insight wiki and graph, and registered the
  file purpose for public justification. The insight captures the todo-list smoke analysis,
  deterministic e2e follow-up, broader live Codex Exec smoke results, strict schema fix,
  Windows `workspace-write` limitation, planning hygiene lesson, and ACP evidence loop.
- Previous completed checkpoint: `plan-broader-live-smoke-20260528` ran a broader live Codex Exec
  Story Loop smoke against disposable git/planning/worktree repos. The first live attempt exposed
  an OpenAI strict structured-output schema incompatibility in the Worker Result schema for
  `browser_smoke_results`; `src/codex_supervisor/worker_backends.py` now makes browser-smoke item
  properties strict-schema-compatible by requiring every key and allowing `null` for optional
  fields, with regression coverage in `tests/test_worker_backends.py`. The retry also showed
  Windows `codex exec --sandbox workspace-write` rejecting write commands as read-only, while the
  trusted isolated `danger-full-access` retry completed: real Codex edited `smoke.txt`, emitted
  strict JSONL and final Worker Result evidence, produced an evidence manifest, and completed the
  disposable queue. Focused worker/schema tests and planning integrity passed locally.
- Previous completed checkpoint: `plan-e2e-test-gap-closure-20260528` added deterministic e2e
  coverage for the live-smoke gap: `tests/test_story_loop_e2e.py` now launches the real
  `story-loop-run-once` and `story-loop-start`/`story-loop-poll` CLI paths against a real temporary
  git repo, real worktree, and fake Codex executable, while `tests/test_mcp_stdio.py` covers a
  mutating MCP stdio subprocess lifecycle. The new e2e test exposed support artifacts being treated
  as product code changes; `src/codex_supervisor/worker_orchestration.py` now ignores declared
  `artifacts/` support evidence for allowed-path validation while preserving raw worktree state.
  Focused tests and full `scripts/verify.py` passed locally.
- Previous completed checkpoint: `plan-supervisor-smoke-fixes-20260528` hardened the todo-list-test-15
  supervisor smoke-test flow: typed controller mutation contracts, prelaunch dirty-path policy,
  async controller orphan finalization, runtime preflight metadata, Worker Result artifact
  normalization, browser smoke progress events, handoff freshness checks, review-skip policy, and
  spawned-project loopback/process hygiene guidance. Focused tests, live CLI/Worker Result smokes,
  and full `scripts/verify.py` passed locally.
- Earlier completed checkpoint: `plan-cross-platform-ci-insight-20260528` added
  `insights/cross-platform-ci.md` to capture the repeated Windows-local vs Linux-CI assumption
  pattern and linked it from `insights/README.md` and `insights/graph.md`.
- Earlier completed checkpoint: `plan-ci-linux-mypy-windll-20260528` repaired GitHub Actions Verify
  run `26552849566`, where Linux mypy rejected direct `ctypes.windll` access in
  `src/codex_supervisor/story_loop.py`. Implementation commit:
  `9aed4a031b04634fdcb5711403cac24113176ca0`.
- Earlier completed checkpoint: `plan-supervisor-worker-boundary-cleanup-20260528` recorded the
  todo-list-test-14 RCA, implemented project-aware optional attribution context, shared
  product-worker/controller-owned path policy, planned-vs-actual evidence metadata, and
  product-worker prompt/runtime boundary guidance. Implementation commit:
  `7a11f9f6bde52f5e0c86764eb35e036e4987f766`.
- Small live Story Loop smoke used temporary real git/planning/worktree state with a deterministic
  tiny backend. It proved private product workers do not receive absent `ATTRIBUTIONS.md`, preclaim
  worker metadata uses `planned_evidence_paths` instead of actual raw evidence claims, and
  controller-owned product paths fail closed before worktree creation.
- Earlier completed checkpoint: `plan-worker-controller-boundary-hardening-20260527` implemented
  the worker/controller boundary hardening fixes requested after the earlier todo-list smoke tests.
- Durable changes now keep normal `codex_exec` workers read-only against planning/controller state,
  reject unsafe product-worker contracts pre-launch, preserve rejected Worker Result JSON as
  evidence, enforce review-promotion gates, require browser smoke evidence when task scope demands
  it, normalize worker backend names, and require explicit strict evidence mode for full-AFK
  preflight.
- Earlier completed checkpoint: `plan-subagent-spawn-insight-20260527` recorded the durable lesson
  that full-history subagent forks cannot also override role; use explicit explorer agents with
  self-contained prompts instead. The insight lives in
  `insights/workflow-patterns.md#full-history-subagent-forks-cannot-override-role`.

## Next Action

No active local queue task.
