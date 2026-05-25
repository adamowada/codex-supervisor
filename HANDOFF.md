# HANDOFF.md

Last updated: 2026-05-25 05:36 PDT

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Active Goal posture: dangerous_full_auto/approved_afk Story Loop execution, one current AFK slice
  at a time from planning SQLite.
- Current queue state: `running`.
- Current AFK task: `task-stage13d-ci-run-evidence-links`.
- Current worker run: `worker-run-stage13d-ci-run-evidence-links-inline-20260525`.
- Current plan: `plan-stage13-github-ci-integration` (`Stage 13 GitHub And CI/CD Integration`).
- Latest completed task: `task-stage13c-ci-full-history-planning-integrity`.
- Recent pushed implementation/evidence commits before this handoff update:
  - `fbc0f0c99d61d0f0b9bb1bbcf2edc69d8a675ac9` - Stage 13B path-normalization repair.
  - `7e5b266f47fd505fbe23033cff1af7d8fb7bc8e5` - Stage 13B completion evidence.
  - `41fa038a1576d5c4087afd143d75b669925a2e4f` - Stage 13C claim.
  - `9e311ae99061bd8978a03d55d22ef0cbf9be4dda` - Stage 13C workflow repair.
  - `eeee711de1e2a275c01f105d8e6a3ab946027a01` - Stage 13C completion evidence.
- Worker backend note: local `codex --version` still fails with Access denied for the resolved
  WindowsApps executable, so native Goal Mode worker launch remains unavailable for this worker
  until the CLI path and `CODEX_HOME` are confirmed.

## Stage 13C Summary

Completed task: `task-stage13c-ci-full-history-planning-integrity`.

- Worker run: `worker-run-stage13c-ci-full-history-planning-integrity-inline-20260525`.
- DB result: `worker-result-stage13c-ci-history-depth-result`.
- Review: `review-stage13c-ci-history-depth-repair-20260525`, 0 findings.
- Implementation commit: `9e311ae99061bd8978a03d55d22ef0cbf9be4dda`.
- Source CI failure: GitHub Actions run
  `https://github.com/adamowada/codex-supervisor/actions/runs/26399874125`, job `77709321691`.
- Successful post-repair CI: GitHub Actions run
  `https://github.com/adamowada/codex-supervisor/actions/runs/26400531911`.

Implemented:

- Added `fetch-depth: 0` to `.github/workflows/verify.yml` so planning integrity can validate
  historical commit links in clean Linux CI.
- Added focused workflow contract coverage in `tests/test_github_ci.py`.
- Updated `insights/workflow-patterns.md` with the confirmed CI history-depth lesson.

Verification passed locally with Stage 13C included:

```sh
uv run --no-sync python -B -m pytest tests/test_github_ci.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```

## Stage 13D Contract

Task: `task-stage13d-ci-run-evidence-links`.
Status: `running`.
Worker run: `worker-run-stage13d-ci-run-evidence-links-inline-20260525`.
Review required: yes, because the slice changes planning persistence and CLI public surface.

Allowed paths:

- `src/codex_supervisor/planning.py`
- `src/codex_supervisor/cli.py`
- `tests/test_planning.py`
- `tests/test_planning_integrity.py`
- `plans/planning.sqlite3`
- `HANDOFF.md`
- `insights/**`
- `.agents/skills/**`

Acceptance criteria:

- A typed planning helper or CLI command records CI run evidence with provider, run URL, head SHA,
  workflow/job metadata, status, and conclusion without ad hoc SQL.
- Recording CI evidence creates durable planning progress and safe artifact or commit links that
  pass planning integrity and publication hygiene.
- Focused planning/CLI tests, planning integrity, full verification, and publication-ready
  verification pass with the CI evidence helper included.

Verification commands:

```sh
uv run --no-sync python -B -m pytest tests/test_planning.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```

Stop conditions:

- A HITL task becomes current in planning SQLite.
- The implementation requires GitHub credentials, secrets, repository settings, or network access
  during local tests.
- The helper cannot be implemented through typed planning APIs without ad hoc SQL mutations.
- Verification repeatedly fails without a known repo-local fix.

## Next Action

Continue the claimed `task-stage13d-ci-run-evidence-links` run. Implement the typed CI run evidence
recording path, run the task verification commands and review, then ACP the slice.
