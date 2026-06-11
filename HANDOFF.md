# HANDOFF.md

Last updated: 2026-06-10

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
- `acceptance_decisions`
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
  Terminal attempts now write a durable `acceptance_decisions` row linked to the task, attempt, and
  evidence bundle; task status is the current-state projection.
- `attempt-run` records declared artifacts plus git-discovered product paths through the same
  provenance rules ACP uses.
- The packaged Desktop Codex worker launcher defaults workers to
  `model_reasoning_effort="xhigh"` and exposes `--reasoning-effort` only for explicit user-requested
  reasoning overrides.
- `AttemptStore.finalize_attempt()` is the only store terminalization path. Terminal attempts write
  evidence and acceptance decisions atomically instead of allowing a decision-free completion path.
- `AttemptStore.finalize_attempt()` rejects contradictory task status, attempt status, acceptance
  result, and evaluation combinations before writing durable state.
- `plan-init` refuses existing incompatible planning schemas instead of half-upgrading old ledgers.
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

uv run --no-sync python -B -m pytest
96 passed

uv run --no-sync python -B scripts/verify.py
96 passed
```

Planning task `task-durable-acceptance-decisions-20260605` is accepted and done in
`plans/planning.sqlite3`. The planning database schema is version 2 and includes durable
`acceptance_decisions` rows. Existing terminal attempts were reconstructed with one acceptance
decision per attempt during the schema upgrade.

Planning task `task-terminalization-single-path-20260605` is accepted and done in
`plans/planning.sqlite3`. The unused `complete_attempt()` bypass was removed so terminal store
state moves through `finalize_attempt()`.

Planning task `task-acceptance-decision-normalization-20260605` is accepted and done in
`plans/planning.sqlite3`. Acceptance decision actor and rationale values are normalized once before
both insertion and return.

Planning task `task-acceptance-hardening-review-fixes-20260605` is accepted and done in
`plans/planning.sqlite3`. The review fixes add fail-fast old-schema initialization, store-level
acceptance projection validation, clearer integrity diagnostics, and focused regression tests.

The opt-in live Codex pytest and its letter-grade structure have been removed. Live smoke testing is
manual and out-of-band; source verification now stays fully deterministic with no always-skipped
live worker test.

Planning task `task-default-xhigh-worker-reasoning-20260610` is accepted and done in
`plans/planning.sqlite3`. The packaged Codex worker launcher now passes
`model_reasoning_effort="xhigh"` by default, supports explicit `--reasoning-effort` overrides,
documents the policy in the packaged and source skills, and records the intentional
`CONTRACTS.md` source-lock update.

Verification completed for the xhigh worker default change:

```text
uv run --no-sync pytest tests/test_codex_plugin.py tests/test_simplified_contract.py -q
18 passed

uv run --no-sync python -B scripts/verify.py
97 passed
```

## Recent Durable Decisions

- Product provenance is a target workspace contract.
- Evidence may be structured in code before compact JSON storage.
- Stale durable decisions from earlier stages are superseded by current source-of-truth docs,
  current planning records, and `DECISIONS.md`.

## Next Action

No next action.
