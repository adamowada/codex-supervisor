# Handoff

## Current State

Repository: `codex-supervisor`

Last clean pushed baseline before this planning update: `31da5a2`

The repository is a Python-first control plane for an agentic coding factory around Codex. The
bootstrap source-of-truth documents, planning SQLite database, source lock guard, initial Python
package skeleton, ignored OSS study sources, insights graph, and repo-local skill pack are present.

Major additions now present:

- `.agents/skills/codex-supervisor`: thin top-level orchestrator skill.
- `.agents/skills/skill-router`: small dispatcher for choosing the right workflow skill.
- Matt Pocock-inspired engineering skills for architecture, grilling, triage, issue shaping, TDD,
  diagnosis, prototyping, and zoom-out review.
- Fresh-thread code review and review-finding fixer skills matching Adam's review workflow.
- Protected source-of-truth doctrine for treating local `~/.codex` SQLite databases as read-only
  telemetry, while keeping `plans/planning.sqlite3` as the canonical queue.
- Goal Contract and Story Loop doctrine inspired by Codex Goals and Ralph.
- `sources/snarktank-ralph` is present locally as an ignored MIT-licensed inspiration source.

The repo was last verified with:

- `uv run pytest`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src`
- `uv lock --check`
- `python scripts/check_protected_files.py`

## Next Recommended Session Prompt

```text
Use the codex-supervisor skill.

Read README.md, AGENTS.md, PLANS.md, ARCHITECTURE.md, CONTRACTS.md, ROADMAP.md, SOP.md, TESTING.md,
DECISIONS.md, ATTRIBUTIONS.md, HANDOFF.md, and insights/codex-usage-skill-synthesis.md.

Inspect plans/planning.sqlite3 through the existing typed planning helpers and summarize active
plans, decisions, progress events, and next tasks.

First, use the knowledge-graph-updater skill on the queued immediate task: coordinate six read-only
explorer lanes, collect structured findings from sources/, .agents/skills/, and source-of-truth
documents, then synthesize useful findings into insights/ with provenance and confidence.

After that, begin implementation from ROADMAP.md, starting with Stage 1: Planning SQLite Core,
unless the current plan data or user instruction reprioritizes the work. Keep implementation scoped,
update plans/planning.sqlite3 through typed helpers, preserve protected source-of-truth locks, and
run the default verification suite before reporting completion.
```

## Recommended First Implementation Focus

Stage 1 should make the planning database comfortable enough for the supervisor to rely on it:

- complete typed CRUD helpers for plans, milestones, acceptance criteria, decisions, progress
  events, artifact links, commit links, supervisor tasks, and worker runs;
- add CLI commands beyond `plan-init` and `plan-list` for inspecting active plans and recording
  progress;
- add tests for idempotent initialization, serialization, status transitions, and source-lock
  interaction;
- keep the public docs synchronized only when stable contracts change.

Stage 8, the Codex local state adapter and automation bridge, is documented but should wait until the
planning core can accept reconciled observations cleanly.

Goal Contracts and Story Loop support are now documented before the Codex Exec backend. Keep that
middle layer in mind while implementing Stage 1 so task and worker-run records can carry goal/story
metadata cleanly.

## Important Constraints

- Do not vendor source clones from `sources/`.
- Keep the project cross-platform.
- Treat dangerous/full-auto operation as the intended production mode.
- Preserve the split between durable source of truth, operational SQLite state, local Codex
  telemetry, and generated run artifacts.
- Treat local `~/.codex` databases as read-only observational inputs.
- Use official Codex automation tooling for recurring jobs, reminders, monitors, and thread wakeups.
- Do not edit locked source-of-truth documents unless the active plan requires it; update
  `scripts/check_protected_files.py` after intentional protected-doc changes.
