# HANDOFF.md

Last updated: 2026-05-25 06:34 PDT

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Active Goal posture: dangerous_full_auto/approved_afk Story Loop execution, one current AFK slice
  at a time from planning SQLite.
- Current queue state: `ready`.
- Current AFK task: `task-stage14a-spawned-project-tier-classifier`.
- Current worker run: `worker-run-stage13e-pr-issue-evidence-links-inline-20260525` completed.
- Current plan: `plan-stage14-spawned-project-factory-sop`.
- Latest completed task in planning: `task-stage13e-pr-issue-evidence-links`.
- Recent pushed commits:
  - `263354c5c3867be9baa370562225c737e0e63768` - Stage 13D CI evidence implementation.
  - `622c52f685c399e12c347d64ab5a0c4aafed17d9` - Stage 13D completion and Stage 13E shaping.
  - `520b8616e4f525d05dc4d5e4c2f7a4f0e9ac495f` - Stage 13E claim.
  - `3461945e57450e81d60b19053630214b005c3fd9` - Stage 13E implementation and completion.
- Latest successful remote CI: GitHub Actions `Verify` run
  `https://github.com/adamowada/codex-supervisor/actions/runs/26403022698`.
- Worker backend note: local `codex --version` still fails with Access denied for the resolved
  WindowsApps executable, so native Goal Mode worker launch remains unavailable for this worker
  until the CLI path and `CODEX_HOME` are confirmed.

## Stage 13E Summary

Review anchor: stage13e-review.
Review result anchor: stage13e-review-result.
Summary anchor: stage13e-summary.

Task: `task-stage13e-pr-issue-evidence-links`.
Status: completed in planning SQLite, pushed, and verified by remote CI.

Implemented:

- Added typed `PullRequestEvidenceRecord` / `PullRequestEvidenceRecorded` and
  `IssueCommentEvidenceRecord` / `IssueCommentEvidenceRecorded`.
- Added `PlanningSQLiteStore.record_pull_request_evidence` and
  `PlanningSQLiteStore.record_issue_comment_evidence`.
- Added CLI commands `pr-evidence-record` and `issue-comment-record` for credential-free recording
  of GitHub PR and issue-comment evidence.
- Durable progress details now store provider/repository/URL/remote IDs and optional metadata;
  optional repo-local artifacts create artifact links; optional SHAs create commit links.
- Review `review-stage13e-pr-issue-evidence-links-20260525` found one accepted P2 issue: re-recorded
  PR/comment evidence could leave stale commit links behind. The repair removes obsolete `pr-head`
  and `issue-comment-commit` links when evidence is replaced or cleared.
- Updated `insights/workflow-patterns.md` with the durable rule that typed evidence upserts must
  remove stale derived links.

Verification passed locally:

```sh
uv run --no-sync python -B -m pytest tests/test_planning.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/verify.py
```

Publication-ready verification initially failed only because this handoff exceeded the compact
snapshot line limit. This file was compacted, and publication-ready verification passed after
staging.

## Stage 14A Ready Task

Task: `task-stage14a-spawned-project-tier-classifier`.
Plan: `plan-stage14-spawned-project-factory-sop`.
Review required: yes, because it adds a new core model and CLI public surface.

Goal: add a deterministic, credential-free spawned-project scaffold recommendation model and CLI
dry-run command so `codex-supervisor` can choose SOP tiers for prototypes versus
production-intended projects before creating files.

Allowed paths: `src/codex_supervisor/spawned_projects.py`, `src/codex_supervisor/cli.py`,
`tests/test_spawned_projects.py`, `tests/test_file_justification.py`,
`scripts/check_file_justification.py`, `plans/planning.sqlite3`, `HANDOFF.md`, and `insights/**`.

Stop instead of guessing if the slice requires a real external project, user product/publication
policy, a new verification script beyond command-safety scope, or repeated unknown
publication-ready failure.

## Next Action

Claim and execute `task-stage14a-spawned-project-tier-classifier` as the next AFK Story Loop slice.
Use its planning SQLite task contract as authority and run:

```sh
uv run --no-sync python -B -m pytest tests/test_spawned_projects.py tests/test_file_justification.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```
