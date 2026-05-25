# HANDOFF.md

Last updated: 2026-05-25 05:24 PDT

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Active Goal posture: dangerous_full_auto/approved_afk Story Loop execution, one current AFK slice
  at a time from planning SQLite.
- Current queue state: `running`.
- Current AFK task: `task-stage13c-ci-full-history-planning-integrity`.
- Current worker run: `worker-run-stage13c-ci-full-history-planning-integrity-inline-20260525`.
- Current plan: `plan-stage13-github-ci-integration` (`Stage 13 GitHub And CI/CD Integration`).
- Latest completed task: `task-stage13b-linux-path-normalization-ci-repair`.
- Recent pushed implementation/evidence commits before this handoff update:
  - `0ba7afbd2f65d90b5a290971012045864a7d1a43` - Stage 13A implementation.
  - `90b74e613d5de7e606bf2afb4f547b7176a9a46f` - Stage 13A evidence link.
  - `fbc0f0c99d61d0f0b9bb1bbcf2edc69d8a675ac9` - Stage 13B path-normalization repair.
  - `7e5b266f47fd505fbe23033cff1af7d8fb7bc8e5` - Stage 13B completion evidence.
- Worker backend note: local `codex --version` still fails with Access denied for the resolved
  WindowsApps executable, so native Goal Mode worker launch remains unavailable for this worker
  until the CLI path and `CODEX_HOME` are confirmed.

## Stage 13B Summary

Completed task: `task-stage13b-linux-path-normalization-ci-repair`.

- Worker run: `worker-run-stage13b-linux-path-normalization-ci-repair-inline-20260525`.
- DB result: `worker-result-stage13b-linux-path-normalization-ci-repair-result`.
- Review: `review-stage13b-linux-path-normalization-ci-repair-20260525`, 0 findings.
- Implementation commit: `fbc0f0c99d61d0f0b9bb1bbcf2edc69d8a675ac9`.
- Source CI failure: GitHub Actions run
  `https://github.com/adamowada/codex-supervisor/actions/runs/26399431134`, job `77707810921`.

Implemented:

- Normalized Windows-style adapter paths through `PureWindowsPath(value).as_posix()` before
  resolving on POSIX.
- Added regression coverage for Windows-style prompt paths, insights allowed paths, and `..\`
  traversal rejection.
- Updated `insights/workflow-patterns.md` with the cross-platform adapter lesson.

Verification passed locally with Stage 13B included:

```sh
uv run --no-sync python -B -m pytest tests/test_projects.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```

Post-repair remote outcome: GitHub Actions run
`https://github.com/adamowada/codex-supervisor/actions/runs/26399874125`, job `77709321691`,
passed all 441 Linux tests plus ruff, formatting, mypy, CLI help, file-purpose, and public hygiene,
then failed `scripts/check_planning_integrity.py` because the workflow used a shallow checkout that
did not contain historical commits linked from `plans/planning.sqlite3`. That failure is routed into
Stage 13C.

## Stage 13C Contract

Task: `task-stage13c-ci-full-history-planning-integrity`.
Status: `running`.
Worker run: `worker-run-stage13c-ci-full-history-planning-integrity-inline-20260525`.
Review required: yes, because the workflow checkout behavior defines public CI evidence and
planning-integrity trust.

Source CI failure:

- Run: `https://github.com/adamowada/codex-supervisor/actions/runs/26399874125`.
- Job: `77709321691`.
- Step: `Run publication-ready verification`.
- Class: `ci_shallow_checkout_planning_integrity`.
- First bad check: `scripts/check_planning_integrity.py`.

Allowed paths:

- `.github/workflows/verify.yml`
- `tests/test_github_ci.py`
- `plans/planning.sqlite3`
- `HANDOFF.md`
- `insights/**`
- `.agents/skills/**`

Acceptance criteria:

- The GitHub Actions `Verify` workflow fetches enough git history for planning integrity to
  validate DB commit links in clean Linux CI.
- Workflow contract tests assert the checkout history-depth requirement while preserving locked
  dependency setup and publication-ready verification.
- Focused workflow tests, planning integrity, full verification, and publication-ready verification
  pass locally, and the post-repair GitHub Actions `Verify` result is inspected or any remaining CI
  failure is shaped as follow-up work.

Verification commands:

```sh
uv run --no-sync python -B -m pytest tests/test_github_ci.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```

Stop conditions:

- A HITL task becomes current in planning SQLite.
- The repair requires repository settings, credentials, branch protection, or external secrets.
- The fix requires deleting historical commit links or weakening planning-integrity semantics.
- Post-repair CI fails for an unrelated reason; record and shape that as follow-up rather than
  widening this slice.

## Next Action

Continue the claimed `task-stage13c-ci-full-history-planning-integrity` run. Repair the workflow
checkout history depth with focused tests, run the task verification commands and review, then push
and inspect the next GitHub Actions result.
