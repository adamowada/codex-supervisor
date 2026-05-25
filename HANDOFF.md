# HANDOFF.md

Last updated: 2026-05-25 06:28 PDT

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Active Goal posture: dangerous_full_auto/approved_afk Story Loop execution, one current AFK slice
  at a time from planning SQLite.
- Current queue state: `completed` for Stage 13; no open current-queue AFK/HITL task remains.
- Current AFK task: none.
- Current worker run: `worker-run-stage13e-pr-issue-evidence-links-inline-20260525` completed.
- Current plan: `plan-stage13-github-ci-integration` completed.
- Latest completed task in planning: `task-stage13e-pr-issue-evidence-links`.
- Recent pushed commits:
  - `263354c5c3867be9baa370562225c737e0e63768` - Stage 13D CI evidence implementation.
  - `622c52f685c399e12c347d64ab5a0c4aafed17d9` - Stage 13D completion and Stage 13E shaping.
  - `520b8616e4f525d05dc4d5e4c2f7a4f0e9ac495f` - Stage 13E claim.
- Worker backend note: local `codex --version` still fails with Access denied for the resolved
  WindowsApps executable, so native Goal Mode worker launch remains unavailable for this worker
  until the CLI path and `CODEX_HOME` are confirmed.

## Stage 13E Summary

Review anchor: stage13e-review.
Review result anchor: stage13e-review-result.
Summary anchor: stage13e-summary.

Task: `task-stage13e-pr-issue-evidence-links`.
Status: completed in planning SQLite; ACP and CI inspection pending.

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
snapshot line limit. This file has been compacted; rerun publication-ready after staging.

## Next Action

Rerun:

```sh
uv run --no-sync python -B scripts/verify.py --publication-ready
```

Then ACP, push, inspect the GitHub Actions `Verify` run for the pushed commit, record the resulting
CI/commit evidence in planning, and shape the next ROADMAP stage slice.
