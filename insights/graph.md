# Knowledge Graph

Operational pointer: this graph is descriptive memory, not the live queue. For current work, run
`uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json` and inspect
`queue_state` plus `current_task_id`. Do not store mutable live task IDs or queue snapshots in this
graph.

## Nodes

- `CodexSupervisor`: Python-first orchestration control plane.
- `PlanningSQLite`: tracked operational planning state.
- `SourceLocks`: SHA-256 guard for stable source-of-truth docs.
- `InsightsWiki`: markdown durable learning memory.
- `CodexExecBackend`: fresh-context worker backend for live Codex execution.
- `ProjectAdapter`: translator between project source-of-truth and supervisor contracts.
- `GoalContract`: thread- or worker-scoped execution contract derived from a supervisor task.
- `StoryLoop`: one vertical slice per fresh-context worker iteration.
- `RalphLoop`: OSS inspiration for fresh-context story execution with durable progress.
- `SkillLearningLoop`: process for turning repeated lessons into tested skills.
- `AgenticEngineeringFactory`: operating model for AFK/HITL task flow.
- `DesktopPluginRuntime`: installed Codex Desktop plugin cache, skill, and MCP startup surface.
- `PluginMcpLauncher`: cache-safe stdlib launcher that locates the supervisor source package or
  exposes a diagnostic MCP fallback.
- `ExecutionModeLedger`: visible preflight record of backend, planning, worker, goal, evidence, and
  infrastructure modes before supervised execution begins.
- `ToolSearchDiscovery`: relevance-ranked Codex tool discovery surface; useful for finding tools,
  but not authoritative MCP inventory.
- `WorkerBoundaryPolicy`: shared rule set separating product-worker paths from
  supervisor/controller-owned paths.
- `WorkerResultEvidenceGate`: controller validation that reconciles Worker Result claims with raw
  JSONL tool events and inspected worktree state.
- `CrossPlatformCI`: publication gate that proves Windows-local assumptions still hold under Linux
  CI type-checking, path semantics, shell behavior, and clean-checkout evidence.
- `LiveSmokeEvidence`: bounded real-environment validation using disposable repos, real Codex Exec,
  strict JSONL, Worker Result artifacts, liveness, and planning evidence.

## Edges

| From | Relation | To | Source | Confidence | Last verified | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| `CodexSupervisor` | owns | `PlanningSQLite` | `PLANS.md`, `src/codex_supervisor/planning.py` | confirmed | 2026-05-24 | Keep SQLite as queue authority. |
| `CodexSupervisor` | checks | `SourceLocks` | `AGENTS.md`, `scripts/check_protected_files.py` | confirmed | 2026-05-24 | Rehash only after intentional protected-doc edits. |
| `CodexSupervisor` | updates | `InsightsWiki` | `insights/README.md`, `knowledge-graph-updater` skill | confirmed | 2026-05-24 | Add provenance/confidence to new insight edges. |
| `CodexSupervisor` | launches through | `CodexExecBackend` | `DECISIONS.md`, `insights/v1-hardening-clarifications.md`, `plans/planning.sqlite3` plan `plan-v1-hardening-clarifications` | confirmed | 2026-05-25 | Verify live Codex/API smoke tests for promised live behavior. |
| `ProjectAdapter` | compiles docs into | `PlanningSQLite` | `ROADMAP.md`, `CONTRACTS.md`, `insights/v1-hardening-clarifications.md` | confirmed | 2026-05-25 | Use ignored local config or runtime inputs for local roots; keep tracked state path-safe. |
| `GoalContract` | derives from | `PlanningSQLite` | `CONTRACTS.md`, `src/codex_supervisor/goal_contracts.py` | confirmed | 2026-05-24 | Preserve prompt fallback when native Goals unavailable. |
| `StoryLoop` | executes | `GoalContract` | `src/codex_supervisor/story_loop.py`, `story-loop-runner` skill | confirmed | 2026-05-24 | Keep one executable AFK task per iteration. |
| `RalphLoop` | informs | `StoryLoop` | `insights/goal-mode-and-ralph-loop.md`, `sources/README.md` pinned `snarktank/ralph` commit `6c53cb0b831ebe8739c6a003e22af14902d8b0b5` | confirmed | 2026-05-24 | Use as pattern source, not operational state. |
| `SkillLearningLoop` | refines | `InsightsWiki` | `insights/skill-learning-loop.md`, `insights/v1-hardening-clarifications.md`, `skill-golden-eval-loop` skill | confirmed | 2026-05-25 | Require source-linked insight, skill edit, golden eval or focused test, and passing verification before ACP. |
| `AgenticEngineeringFactory` | implemented by | `CodexSupervisor` | `README.md`, `ROADMAP.md`, repo-local skills | confirmed | 2026-05-24 | Continue tightening bootstrap and ACP reproducibility. |
| `DesktopPluginRuntime` | attaches | `CodexSupervisor` | `plugins/codex-supervisor/.mcp.json`, `plugins/codex-supervisor/skills/codex-supervisor/SKILL.md`, `insights/workflow-patterns.md` | confirmed | 2026-05-26 | Verify installed-cache MCP startup, not only source plugin shape. |
| `CodexSupervisor` | fails closed without | `DesktopPluginRuntime` | `insights/workflow-patterns.md` 2026-05-26 Desktop smoke RCA | confirmed | 2026-05-26 | Stop or record blocker when skill loads but MCP and CLI fallback are unavailable. |
| `ExecutionModeLedger` | guards | `StoryLoop` | `insights/workflow-patterns.md` 2026-05-26 mode-switch RCA | confirmed | 2026-05-26 | Make full-AFK preflight expose unavailable, current-thread, fallback database, and degraded evidence modes. |
| `PluginMcpLauncher` | guards | `DesktopPluginRuntime` | `insights/workflow-patterns.md` 2026-05-26 second Desktop smoke RCA | confirmed | 2026-05-26 | Delegate from cache to source repo or expose a blocked `runtime_preflight` diagnostic. |
| `DesktopPluginRuntime` | requires refresh evidence for | `CodexSupervisor` | `insights/workflow-patterns.md` 2026-05-26 stale cache smoke | confirmed | 2026-05-26 | Version-bump or refresh cache before treating source skill changes as live. |
| `DesktopPluginRuntime` | authorizes full-AFK through | `ExecutionModeLedger` | `insights/workflow-patterns.md` 2026-05-26 todo-list-test-3 false canary RCA | confirmed | 2026-05-26 | Treat CLI/package preflight as diagnostics-only after live MCP failure, never as plugin full-AFK authority. |
| `ToolSearchDiscovery` | is not inventory for | `DesktopPluginRuntime` | `insights/workflow-patterns.md` 2026-05-26 todo-list-test-4 false canary RCA | confirmed | 2026-05-26 | Let live MCP preflight self-inventory `list_mcp_tools`; use `canary`/semantic queries only to find callable tools. |
| `WorkerBoundaryPolicy` | guards | `StoryLoop` | `insights/workflow-patterns.md` 2026-05-28 todo-list-test-14 RCA | confirmed | 2026-05-28 | Keep optional docs project-aware and block product workers from controller-owned paths unless the task role is controller/planning/promotion/source-lock. |
| `CrossPlatformCI` | catches drift from | `CodexSupervisor` | `insights/cross-platform-ci.md`, GitHub Actions run `26552849566`, repair commit `9aed4a031b04634fdcb5711403cac24113176ca0` | confirmed | 2026-05-28 | Guard platform-specific APIs with typed adapter boundaries, feature probes, or cross-platform regression tests before publication. |
| `LiveSmokeEvidence` | complements | `StoryLoop` | `insights/live-smoke-lessons.md`, `plan-broader-live-smoke-20260528`, `tests/test_story_loop_e2e.py` | confirmed | 2026-05-28 | Keep fake-Codex e2e tests in CI, then run narrow real Codex Exec smokes for API/schema/sandbox behavior. |
| `LiveSmokeEvidence` | constrains | `CodexExecBackend` | `insights/live-smoke-lessons.md`, `src/codex_supervisor/worker_backends.py`, `tests/test_worker_backends.py` | confirmed | 2026-05-28 | Make model-facing output schemas strict-API compatible while preserving stronger repo-side validation. |
| `WorkerResultEvidenceGate` | verifies claims from | `CodexExecBackend` | `insights/live-smoke-lessons.md`, `plan-multiturn-live-smoke-20260528`, `plan-live-evidence-gate-loop-20260528`, live runs `run-live-multiturn-turn2`, `run-live-multiturn-turn2-retry`, `run-live-multiturn-turn2-simple`, and `run-evidence-gate-live-smoke` | confirmed | 2026-05-28 | Keep matching `tests_run` commands against JSONL command events, and expand claim reconciliation when new unsupported claim types appear. |
