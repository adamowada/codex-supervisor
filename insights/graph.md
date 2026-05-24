# Knowledge Graph

## Nodes

- `CodexSupervisor`: Python-first orchestration control plane.
- `PlanningSQLite`: tracked operational planning state.
- `SourceLocks`: SHA-256 guard for stable source-of-truth docs.
- `InsightsWiki`: markdown durable learning memory.
- `CodexExecBackend`: primary fresh-context worker backend.
- `ProjectAdapter`: translator between project source-of-truth and supervisor contracts.
- `GoalContract`: thread- or worker-scoped execution contract derived from a supervisor task.
- `StoryLoop`: one vertical slice per fresh-context worker iteration.
- `RalphLoop`: OSS inspiration for fresh-context story execution with durable progress.
- `SkillLearningLoop`: process for turning repeated lessons into tested skills.
- `AgenticEngineeringFactory`: operating model for AFK/HITL task flow.

## Edges

- `CodexSupervisor` owns `PlanningSQLite`.
- `CodexSupervisor` checks `SourceLocks`.
- `CodexSupervisor` updates `InsightsWiki`.
- `CodexSupervisor` launches `CodexExecBackend`.
- `ProjectAdapter` compiles source-of-truth docs into tasks.
- `GoalContract` is derived from `PlanningSQLite`.
- `StoryLoop` executes `GoalContract`.
- `RalphLoop` informs `StoryLoop`.
- `SkillLearningLoop` reads `InsightsWiki`.
- `AgenticEngineeringFactory` is implemented by `CodexSupervisor`.
