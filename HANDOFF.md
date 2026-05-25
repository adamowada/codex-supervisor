# HANDOFF.md

Last updated: 2026-05-25 05:03 PDT

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Active Goal posture: dangerous_full_auto/approved_afk Story Loop execution, one current AFK slice
  at a time from planning SQLite.
- Current queue state: `ready`.
- Current AFK task: `task-stage13b-linux-path-normalization-ci-repair`.
- Current plan: `plan-stage13-github-ci-integration` (`Stage 13 GitHub And CI/CD Integration`).
- Latest completed task: `task-stage13a-github-actions-verify`.
- Latest pushed commits:
  - `0ba7afbd2f65d90b5a290971012045864a7d1a43` - Stage 13A implementation.
  - `90b74e613d5de7e606bf2afb4f547b7176a9a46f` - Stage 13A evidence link.
- Worker backend note: local `codex --version` still fails with Access denied for the resolved
  WindowsApps executable, so native Goal Mode worker launch remains unavailable for this worker
  until the CLI path and `CODEX_HOME` are confirmed.

## Stage 13B Contract

Task: `task-stage13b-linux-path-normalization-ci-repair`.
Status: `ready`.
Review required: yes, because the repair changes project adapter behavior and CI evidence routing.

Source CI failure:

- Run: `https://github.com/adamowada/codex-supervisor/actions/runs/26399431134`.
- Job: `77707810921`.
- Step: `Run publication-ready verification`.
- Class: cross-platform path normalization.
- Failing tests:
  - `tests/test_projects.py::test_harness_config_adapter_normalizes_windows_prompt_separators`
  - `tests/test_projects.py::test_insights_graph_adapter_extracts_candidates_without_mutating_target`

Allowed paths:

- `src/codex_supervisor/projects.py`
- `tests/test_projects.py`
- `plans/planning.sqlite3`
- `HANDOFF.md`
- `insights/**`
- `.agents/skills/**`

Acceptance criteria:

- Project adapter path handling normalizes Windows-style relative separators for harness
  `prompt_path` and insights `allowed_paths` on POSIX/Linux without accepting unsafe absolute,
  drive-relative, or parent-traversal paths.
- Focused project-adapter tests, planning integrity, full verification, and publication-ready
  verification pass after the repair.
- The GitHub Actions `Verify` failure from run `26399431134` is recorded as the source failure, and
  the post-repair remote result is inspected or any remaining CI failure is shaped as follow-up
  work.

Verification commands:

```sh
uv run --no-sync python -B -m pytest tests/test_projects.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```

Stop conditions:

- A HITL task becomes current in planning SQLite.
- The CI failure requires repository secrets, branch protection, runner settings, or external
  credentials.
- The local repair reveals a broader adapter contract change outside `projects.py` and
  `tests/test_projects.py`.
- Post-repair CI fails for an unrelated reason; record and shape that as follow-up rather than
  widening this slice.

## Stage 13A Evidence

Completed task: `task-stage13a-github-actions-verify`.

- Worker run: `worker-run-stage13a-github-actions-verify-inline-20260525`.
- DB result: `worker-result-stage13a-github-actions-verify-result`.
- Review: `review-stage13a-github-actions-verify-20260525`, 0 findings.
- Completion progress: `progress-stage13a-github-actions-verify-completed-20260525`.
- Implementation commit: `0ba7afbd2f65d90b5a290971012045864a7d1a43`.

Implemented:

- Added `.github/workflows/verify.yml`, the first GitHub Actions workflow for the repository.
- Added `tests/test_github_ci.py` and `.github` file-purpose coverage.
- Updated `insights/workflow-patterns.md` and `.agents/skills/story-loop-runner/SKILL.md` with CI
  publication-gate and transient `worker-results/` cleanup lessons.

Verification passed locally with Stage 13A included:

```sh
uv run --no-sync python -B -m pytest tests/test_github_ci.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/check_file_justification.py
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```

Remote outcome: the published `Verify` workflow ran and failed on Linux path-normalization tests,
which is now routed into Stage 13B.

## Next Action

Claim and execute `task-stage13b-linux-path-normalization-ci-repair`. After local verification and
review, push the repair and inspect the post-repair GitHub Actions result.
