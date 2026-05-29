# AGENTS.md

## Repository Purpose

This repository builds `codex-supervisor`: a Python-first control plane for coordinating Codex work
through task intent, run attempts, evidence bundles, and acceptance decisions.

## Operating Principles

- Keep the state space small.
- Add a new axis only when it collapses more complexity than it creates.
- Keep durable state in `plans/planning.sqlite3`.
- Keep source-of-truth docs short, current, and direct.
- Keep skills as thin operating guidance.
- Keep CI focused on the active contract.
- Keep full-auto safety based on isolation, evidence, and acceptance.
- Prefer one transition path over mode-specific branches.

## Active Model

The durable work model is:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Assurance levels are `low`, `medium`, and `high`. They set evidence and acceptance requirements.
Work categories belong in task intent and acceptance criteria. Do not add supervisor job types for
semantic engineering categories.

## Source Of Truth

Protected source-of-truth files:

- `.gitignore`
- `.gitattributes`
- `README.md`
- `AGENTS.md`
- `PLANS.md`
- `ARCHITECTURE.md`
- `CONTRACTS.md`
- `ROADMAP.md`
- `SOP.md`
- `TESTING.md`
- `DECISIONS.md`
- `LICENSE`

`HANDOFF.md` is mutable and current-only.

After intentional protected-doc edits, refresh `scripts/check_protected_files.py` with current
hashes and rerun the lock check.

## Planning Database

Required tables:

- `meta`
- `plans`
- `tasks`
- `attempts`
- `evidence_bundles`
- `decisions`

The database records the current queue, attempts, evidence, and decisions. Keep additional detail in
JSON fields until a repeated access pattern earns a dedicated table.

## Common Commands

Use the verification gate:

```sh
uv run --no-sync python -B scripts/verify.py
```

Focused checks:

```sh
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B scripts/check_skill_inventory.py
uv run --no-sync python -B scripts/check_protected_files.py
```

Core CLI operations:

```sh
uv run --no-sync codex-supervisor task-create --help
uv run --no-sync codex-supervisor queue-next --help
uv run --no-sync codex-supervisor attempt-transition --help
uv run --no-sync codex-supervisor attempt-run --help
```

## Coding Rules

- Keep Python core code cross-platform.
- Use `pathlib.Path` for filesystem paths.
- Keep side effects at boundaries.
- Prefer structured data over prose-only state.
- Add abstractions where they simplify repeated behavior.

## Definition Of Done

- Source-of-truth docs match the active contract.
- Planning SQLite passes the schema check.
- Repo-local skill guidance matches the active model.
- Verification passes.
- `HANDOFF.md` names the current state and next action.
- Source locks match intentional protected-doc changes.
