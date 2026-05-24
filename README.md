# Codex Supervisor

`codex-supervisor` is a Python-first control plane for building an agentic coding factory around
Codex.

The goal is simple and ambitious: after I supply the required product, architecture,
acceptance, risk, and operating assumptions, Codex should be able to coordinate fresh-context Codex
workers until the plan is implemented, reviewed, tested, documented, and ready for a human decision.

This repository is the source of truth for that workflow. It combines patterns from my busiest
projects:

- `nlp-stock-prediction`: tracked SQLite planning state with typed access.
- `codex-subagent-testing`: locked top-level source-of-truth documents protected by SHA-256 hashes.
- `tech-resume`: an `insights/` markdown knowledge graph with provenance and confidence labels.
- `observe-safety-monorepo`: structured, test-enforced planning and production-grade gates.

It also includes shallow source clones under `sources/` for study and integration experiments. Those
clones are intentionally ignored by git.

## Dream Workflow

For any new project:

1. Run an extensive planning session to lock assumptions, contracts, non-goals, risks, and acceptance
   criteria.
2. Persist the plan into a tracked SQLite planning database.
3. Compile the plan into small vertical-slice tasks marked `AFK` or `HITL`.
4. Launch fresh-context Codex workers in isolated worktrees.
5. Give each worker a Goal Contract with objective, boundaries, verification, and stop conditions.
6. Execute one vertical slice per story-loop iteration.
7. Require every worker to return structured output.
8. Run automated checks and automated review before merge.
9. Record decisions, progress, artifacts, commits, failures, and follow-up tasks.
10. Update skills and the knowledge graph when repeated patterns or failures reveal something durable.

## Intended Operating Mode

This system is designed for trusted local or controlled-runner automation using dangerous/full-auto
Codex execution. The safety boundary is not permission prompts. The safety boundary is:

- disposable worktrees;
- explicit task scope;
- structured outputs;
- deterministic tests and checks;
- automated review;
- source-of-truth document locks;
- durable planning state;
- auditable logs and artifacts.

## Repository Map

```text
src/codex_supervisor/      Python supervisor package skeleton
tests/                     Focused tests for planning and document locks
scripts/                   Repo maintenance scripts
plans/planning.sqlite3     Tracked operational planning database
insights/                  Markdown knowledge graph and learning memory
.agents/skills/            Repo-specific Codex skills
sources/                   Ignored shallow clones of OSS inspiration sources
```

## Source-Of-Truth Documents

- `README.md`: human-facing purpose, goals, and operating vision.
- `AGENTS.md`: instructions for Codex and other coding agents in this repo.
- `PLANS.md`: planning database contract and required planning workflow.
- `ARCHITECTURE.md`: supervisor architecture and backend boundaries.
- `CONTRACTS.md`: durable runtime contracts for tasks, workers, adapters, and results.
- `ROADMAP.md`: staged implementation plan for future Codex sessions.
- `SOP.md`: standard operating procedure for projects spawned by the supervisor.
- `TESTING.md`: testing and verification strategy.
- `DECISIONS.md`: baseline decisions; ongoing decisions belong in SQLite first.
- `HANDOFF.md`: clean starting point for the next Codex session.
- `LICENSE`: MIT license for this repository.
- `ATTRIBUTIONS.md`: public OSS inspiration and integration attribution notes.

Stable top-level source-of-truth documents are locked by `scripts/check_protected_files.py`.

## First Commands

```sh
uv sync --dev
uv run pytest
uv run ruff check .
uv run mypy src
uv run python scripts/check_protected_files.py
```

Initialize or inspect the planning database:

```sh
uv run codex-supervisor plan-init
uv run codex-supervisor plan-list
```

## OSS Inspiration Sources

The ignored `sources/` directory contains shallow clones of:

- `openai/codex`
- `HarnessLab/claw-code-agent`
- `openclaw/openclaw`
- `mattpocock/skills`
- `mattpocock/sandcastle`
- `mattpocock/evalite`
- `mattpocock/agent-rules-books`
- `mattpocock/agent-browser`
- `mattpocock/node-DeepResearch`
- `snarktank/ralph`
