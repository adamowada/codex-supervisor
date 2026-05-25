# HANDOFF.md

Last updated: 2026-05-25 06:07 PDT

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Active Goal posture: dangerous_full_auto/approved_afk Story Loop execution, one current AFK slice
  at a time from planning SQLite.
- Current queue state: `running`.
- Current AFK task: `task-stage13e-pr-issue-evidence-links`.
- Current worker run: `worker-run-stage13e-pr-issue-evidence-links-inline-20260525`.
- Current plan: `plan-stage13-github-ci-integration` (`Stage 13 GitHub And CI/CD Integration`).
- Latest completed task: `task-stage13d-ci-run-evidence-links`.
- Recent pushed implementation/evidence commits before this handoff update:
  - `fbc0f0c99d61d0f0b9bb1bbcf2edc69d8a675ac9` - Stage 13B path-normalization repair.
  - `7e5b266f47fd505fbe23033cff1af7d8fb7bc8e5` - Stage 13B completion evidence.
  - `41fa038a1576d5c4087afd143d75b669925a2e4f` - Stage 13C claim.
  - `9e311ae99061bd8978a03d55d22ef0cbf9be4dda` - Stage 13C workflow repair.
  - `eeee711de1e2a275c01f105d8e6a3ab946027a01` - Stage 13C completion evidence.
  - `c5fe64a85b1a76100487eab79b8a4e9e7e2fd881` - Stage 13D claim.
  - `263354c5c3867be9baa370562225c737e0e63768` - Stage 13D CI evidence implementation.
  - `622c52f685c399e12c347d64ab5a0c4aafed17d9` - Stage 13D completion and Stage 13E shaping.
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

## Stage 13D Summary

Review anchor: stage13d-review.
Review result anchor: stage13d-review-result.
Summary anchor: stage13d-summary.

Completed task: `task-stage13d-ci-run-evidence-links`.

- Added typed `CiRunEvidenceRecord` / `CiRunEvidenceRecorded` records and
  `PlanningSQLiteStore.record_ci_run_evidence`.
- Added `codex_supervisor.cli ci-run-record` to record CI provider, run URL, head SHA, status,
  conclusion, workflow/job/event metadata, optional repo-local artifact evidence, and a `ci-head`
  commit link.
- Recorded GitHub Actions run `26400531911` for head
  `9e311ae99061bd8978a03d55d22ef0cbf9be4dda` in planning SQLite as
  `progress-stage13d-ci-run-record-20260525`.
- Publication-ready verification caught that synthetic external artifact IDs such as
  `ci-runs/github-actions/26400531911` are invalid publication artifacts. The helper now stores
  external run URLs in progress details by default and only creates artifact links when the caller
  provides a real repo-local artifact ID.
- Updated `insights/workflow-patterns.md` with the durable rule that external CI evidence belongs
  in progress details plus commit links, not synthetic artifact links.
- Review `review-stage13d-ci-run-evidence-links-20260525` found one accepted P2 issue: CI evidence
  upsert must not overwrite unrelated non-CI progress IDs. The implementation now rejects that
  collision and `tests/test_planning.py` covers it.
- Worker result: `worker-result-stage13d-ci-run-evidence-links-result`.
- Implementation commit: `263354c5c3867be9baa370562225c737e0e63768`.
- Successful post-implementation CI: GitHub Actions run
  `https://github.com/adamowada/codex-supervisor/actions/runs/26401678510`.

Verification passed with Stage 13D included:

```sh
uv run --no-sync python -B -m pytest tests/test_planning.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```

## Stage 13E Contract

Task: `task-stage13e-pr-issue-evidence-links`.
Status: `running`.
Worker run: `worker-run-stage13e-pr-issue-evidence-links-inline-20260525`.
Review required: yes, because the slice changes planning persistence and CLI public surface for
GitHub evidence.

Goal: add typed planning and CLI paths for recording GitHub pull request and issue-comment evidence
into planning SQLite so PRs, comments, commits, and optional repo-local artifacts can be linked
durably without live credentials or ad hoc SQL.

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

- A typed planning helper or CLI command records GitHub pull request evidence with provider,
  repository, PR number, PR URL, title or summary, head/base refs or SHAs, state, draft/merged
  flags, and optional issue thread metadata without ad hoc SQL.
- A typed planning helper or CLI command records GitHub issue-comment evidence with provider,
  repository, issue or PR number, comment ID or URL, author when provided, and summary/details
  without requiring live GitHub credentials.
- Recording PR and issue evidence creates durable planning progress plus safe commit links or
  optional repo-local artifact links that pass planning integrity and publication hygiene.
- Focused planning/CLI tests, planning integrity, full verification, and publication-ready
  verification pass with the PR/issue evidence helper included.

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
- The scope expands into creating/updating PRs, posting comments, merging, release publishing, or
  live API fetching.
- Verification repeatedly fails without a known repo-local fix.

## Next Action

Continue the claimed `task-stage13e-pr-issue-evidence-links` run. Implement only the typed PR and
issue-comment evidence recording slice, run the task verification commands and review, then ACP the
step.
