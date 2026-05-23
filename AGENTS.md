# AGENTS.md

## Repository Purpose

This repository builds `codex-supervisor`: a Python-first control plane that lets Codex coordinate
fresh-context Codex workers, worktrees, checks, reviews, handoffs, skills, and project source of truth
until production-quality code is produced.

The product is not a replacement for Codex. It is a durable orchestration layer around Codex.

## Operating Principles

- Treat source-of-truth files as contracts, not scratchpads.
- Prefer repo-owned state over chat memory.
- Prefer fresh-context worker runs over bloated long sessions.
- Prefer structured outputs over prose-only completion.
- Prefer vertical-slice tasks over horizontal layer work.
- Prefer worktrees over direct edits for unattended implementation.
- Prefer deterministic checks before automated review.
- Prefer skill updates and knowledge-graph updates when a workflow lesson repeats.

## Dangerous Full-Auto Assumption

The intended production mode is trusted, local or controlled-runner full-auto operation. Do not design
around frequent human approval prompts. Design around isolation, auditability, checks, and review.

## Source Of Truth

Locked top-level documents:

- `README.md`
- `AGENTS.md`
- `PLANS.md`
- `ARCHITECTURE.md`
- `CONTRACTS.md`
- `ROADMAP.md`
- `SOP.md`
- `TESTING.md`
- `DECISIONS.md`

Do not edit locked source-of-truth documents unless the user explicitly asks or an active plan says
the edit is required. After an intentional edit, update `scripts/check_protected_files.py` with new
hashes.

Operational planning state belongs in `plans/planning.sqlite3`. Use typed helpers in
`codex_supervisor.planning`; do not scatter ad hoc SQL across the project.

Local Codex databases under `~/.codex` are read-only telemetry inputs. Do not write directly to
Codex internal SQLite databases. Reconcile observations into project-owned planning SQLite, and use
official Codex automation tooling for recurring jobs, reminders, monitors, and thread wakeups.

Synthesized durable learning belongs in `insights/`. Do not bury reusable workflow lessons only in
chat, logs, or worker summaries.

## Common Commands

Use `uv` for local development:

```sh
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python scripts/check_protected_files.py
```

Planning:

```sh
uv run codex-supervisor plan-init
uv run codex-supervisor plan-list
```

## Coding Rules

- Keep the supervisor core Python-first and cross-platform.
- Use `pathlib.Path` for filesystem paths.
- Keep side effects at boundaries; core planning, task, lock, and adapter logic should be testable
  without launching Codex.
- Prefer standard library until a dependency clearly earns its place.
- Add abstractions only at real seams: worker backends, project adapters, source adapters, queue
  stores, and result sinks.
- Never hardcode Windows-only path separators in core code.
- Use structured data models for task/result contracts.
- Preserve raw worker evidence: prompts, JSONL, stderr, stdout, diffs, checks, reviews, timing, and
  final structured result.

## Project Adapters

Initial adapter targets:

- `nlp-stock-prediction`: planning SQLite adapter.
- `observe-safety-monorepo`: markdown plan adapter and validation command adapter.
- `codex-subagent-testing`: harness/config/prompt adapter.
- `tech-resume`: insights knowledge graph adapter.
- generic repos: `AGENTS.md`, `PLANS.md`, `TASKS.json`, checks, and source docs.

## Definition Of Done

- The requested behavior is implemented or explicitly documented as staged future work.
- Focused tests cover changed behavior.
- Relevant checks pass.
- Source-of-truth docs are updated only when intentionally required.
- Planning SQLite records the plan, decisions, progress, and verification state.
- Handoff information is captured in `HANDOFF.md` or a plan progress record.
- No cloned `sources/` repositories, worker runs, worktrees, logs, or secrets are staged.
