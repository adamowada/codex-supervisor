# HANDOFF.md

Last updated: 2026-06-05

This is the current resume snapshot.

## Current State

Branch: `feature/simplification-refactor`

Current model:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Active surface:

- CLI: `plan-init`, `task-create`, `queue-next`, `attempt-transition`, `attempt-run`
- MCP: `codex_supervisor.queue_next`
- Plugin: thin Desktop wrapper around the same source CLI and MCP stdio server
- Repo-local skills: `codex-supervisor`, `improve-codebase-architecture`,
  `reduce-codebase-complexity`

Planning database:

- `meta`
- `plans`
- `tasks`
- `attempts`
- `evidence_bundles`
- `decisions`

`plans/planning.sqlite3` and `HANDOFF.md` must stay current together.

## Architecture Snapshot

The compact architecture is intact. Work semantics stay in task intent and acceptance criteria, not
supervisor job types. Assurance remains explicit policy data: `low`, `medium`, and `high`.

The latest architecture-deepening pass is implemented in code and docs:

- `src/codex_supervisor/target_workspace.py` owns target workspace product provenance: git changed
  product paths, `.codex-supervisor/**` exclusion, `.gitignore` exclusion, linked worktree product
  checks, path normalization, and worker-backed product evidence.
- `src/codex_supervisor/evidence.py` keeps evidence structured before it is encoded into the
  compact `checks_json` and `artifacts_json` fields.
- `src/codex_supervisor/terminal_transition.py` owns terminal attempt acceptance and persistence.
- `attempt-run` records declared artifacts plus git-discovered product paths through the same
  provenance rules ACP uses.
- Source-of-truth docs now name product provenance and structured evidence encoding directly.

Target-workspace supervisor operation still uses the bright-line filesystem boundary: the supervisor
owns `.codex-supervisor/**` and the narrow `.gitignore` bootstrap edit; product file mutation is
assigned through `attempt-run`; ACP stops when `.codex-supervisor/**` is tracked, not ignored, or
when changed product paths lack worker-backed evidence.

## Current Verification

Focused verification completed during the architecture-deepening pass:

```text
uv run --no-sync pytest tests/test_target_workspace.py tests/test_evidence_terminal_transition.py tests/test_acp_gate_e2e.py tests/test_process_attempt_e2e.py tests/test_small_interface.py
34 passed

uv run --no-sync ruff check src/codex_supervisor/target_workspace.py src/codex_supervisor/evidence.py src/codex_supervisor/terminal_transition.py src/codex_supervisor/process_attempt.py src/codex_supervisor/acp_gate.py src/codex_supervisor/workspace_hygiene.py src/codex_supervisor/small_interface.py tests/test_target_workspace.py tests/test_evidence_terminal_transition.py
All checks passed
```

Full verification completed after doc, source-lock, handoff, and planning ledger updates:

```text
uv run --no-sync ruff check src tests scripts
All checks passed

uv run --no-sync python -B scripts/verify.py
90 passed
```

Planning task `task-architecture-deepening-20260604` is accepted and done in
`plans/planning.sqlite3`.

The opt-in live Codex pytest and its letter-grade structure have been removed. Live smoke testing is
manual and out-of-band; source verification now stays fully deterministic with no always-skipped
live worker test.

## Recent Durable Decisions

- Product provenance is a target workspace contract.
- Evidence may be structured in code before compact JSON storage.
- Stale durable decisions from earlier stages are superseded by current source-of-truth docs,
  current planning records, and `DECISIONS.md`.

## Next Action

No next action.
