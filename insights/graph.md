# Knowledge Graph

Operational pointer: this graph is descriptive memory, not the live queue. For current work, run
`uv run codex-supervisor story-loop-status --json` and inspect `queue_state` plus
`current_task_id`. Do not store mutable live task IDs or queue snapshots in this graph.

## Nodes

- `CodexSupervisor`: Python-first orchestration control plane.
- `PlanningSQLite`: tracked operational planning state.
- `SourceLocks`: SHA-256 guard for stable source-of-truth docs.
- `InsightsWiki`: markdown durable learning memory.
- `CodexExecBackend`: planned fresh-context worker backend after ROADMAP Stage 6.
- `ProjectAdapter`: translator between project source-of-truth and supervisor contracts.
- `GoalContract`: thread- or worker-scoped execution contract derived from a supervisor task.
- `StoryLoop`: one vertical slice per fresh-context worker iteration.
- `RalphLoop`: OSS inspiration for fresh-context story execution with durable progress.
- `SkillLearningLoop`: process for turning repeated lessons into tested skills.
- `AgenticEngineeringFactory`: operating model for AFK/HITL task flow.

## Edges

| From | Relation | To | Source | Confidence | Last verified | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| `CodexSupervisor` | owns | `PlanningSQLite` | `PLANS.md`, `src/codex_supervisor/planning.py` | confirmed | 2026-05-24 | Keep SQLite as queue authority. |
| `CodexSupervisor` | checks | `SourceLocks` | `AGENTS.md`, `scripts/check_protected_files.py` | confirmed | 2026-05-24 | Rehash only after intentional protected-doc edits. |
| `CodexSupervisor` | updates | `InsightsWiki` | `insights/README.md`, `knowledge-graph-updater` skill | confirmed | 2026-05-24 | Add provenance/confidence to new insight edges. |
| `CodexSupervisor` | prepares before Stage 6 | `CodexExecBackend` | `ROADMAP.md`, `HANDOFF.md` | confirmed | 2026-05-24 | Implement backend only after HITL publication checkpoint. |
| `ProjectAdapter` | compiles docs into | `PlanningSQLite` | `ROADMAP.md`, `CONTRACTS.md` | planned | 2026-05-24 | Build adapter after planning/publication hardening. |
| `GoalContract` | derives from | `PlanningSQLite` | `CONTRACTS.md`, `src/codex_supervisor/goal_contracts.py` | confirmed | 2026-05-24 | Preserve prompt fallback when native Goals unavailable. |
| `StoryLoop` | executes | `GoalContract` | `src/codex_supervisor/story_loop.py`, `story-loop-runner` skill | confirmed | 2026-05-24 | Keep one executable AFK task per iteration. |
| `RalphLoop` | informs | `StoryLoop` | `insights/goal-mode-and-ralph-loop.md`, `sources/snarktank-ralph` | confirmed | 2026-05-24 | Use as pattern source, not operational state. |
| `SkillLearningLoop` | refines | `InsightsWiki` | `insights/skill-learning-loop.md`, `skill-golden-eval-loop` skill | planned | 2026-05-24 | Add golden evals for high-risk skills. |
| `AgenticEngineeringFactory` | implemented by | `CodexSupervisor` | `README.md`, `ROADMAP.md`, repo-local skills | confirmed | 2026-05-24 | Continue tightening bootstrap and ACP reproducibility. |
