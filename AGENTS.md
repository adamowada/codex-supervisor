# AGENTS.md

## Repository Purpose

This repository builds `codex-supervisor`: a small Python-first control plane for coordinating Codex
work through explicit task intent, isolated attempts, evidence bundles, and acceptance decisions.

The project is pre-MVP. Legacy behavior, historical tests, old queue rows, and old public surfaces
have zero preservation weight.

## Operating Principles

- Prefer a smaller state space over a richer feature matrix.
- Treat every new axis as guilty until it proves it removes more complexity than it adds.
- Keep durable state in `plans/planning.sqlite3`.
- Keep source-of-truth docs short, current, and willing to change.
- Keep skills as thin operating guidance, not another orchestration layer.
- Keep CI focused on the contracts that matter now.
- Keep full-auto safety based on isolation, evidence, and acceptance, not approval prompts.
- Do not preserve compatibility for non-existent users.

## Active Model

The only durable work model is:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Assurance levels are `low`, `medium`, and `high`. They modify evidence and acceptance requirements.
They are not task types, worker backends, runtime modes, review modes, or database schemas.

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
- `ATTRIBUTIONS.md`

`HANDOFF.md` is mutable and current-only.

When protected docs intentionally change, update `scripts/check_protected_files.py` with fresh
hashes and rerun the lock check.

## Planning Database

The fresh planning database is intentionally small. Do not reintroduce historical planning tables
unless the current architecture explicitly needs them.

Required tables:

- `meta`
- `plans`
- `tasks`
- `attempts`
- `evidence_bundles`
- `decisions`

Do not recreate historical event-type vocabularies, artifact-link relationship vocabularies, or
worker-result compatibility tables.

## Common Commands

Use the small verification gate:

```sh
uv run --no-sync python -B scripts/verify.py
```

Run individual checks when useful:

```sh
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B scripts/check_skill_inventory.py
uv run --no-sync python -B scripts/check_protected_files.py
```

## Coding Rules

- Keep Python core code cross-platform.
- Use `pathlib.Path` for filesystem paths.
- Keep side effects at boundaries.
- Prefer structured data over prose-only state.
- Prefer one transition path over mode-specific branches.
- Add abstractions only when they collapse real duplication.

## Definition Of Done

- The fresh source-of-truth contract remains coherent.
- The planning database passes the fresh schema check.
- Minimal skills match the new operating model.
- Minimal CI passes.
- `HANDOFF.md` names the current state and next action.
- Source locks are refreshed for intentional protected-doc changes.
