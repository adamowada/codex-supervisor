# HANDOFF.md

Last updated: 2026-05-25 07:38 PDT

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Active Goal posture: dangerous_full_auto/approved_afk Story Loop execution, one current AFK slice
  at a time from planning SQLite.
- Current plan: `plan-stage15-release-hardening`.
- Latest completed task: `task-stage15a-release-readiness-audit`.
- Worker run: `worker-run-stage15a-release-readiness-audit-inline-20260525`.
- Latest successful local gates:
  - `uv run --no-sync python -B -m pytest tests/test_release_readiness.py tests/test_file_justification.py -q -p no:cacheprovider` - 18 passed.
  - `uv run --no-sync python -B scripts/check_planning_integrity.py` - passed.
  - `uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json` - Stage 15A running before completion ingest.
  - `uv run --no-sync python -B scripts/verify.py` - 469 passed plus hygiene, source inventory, skill inventory, planning integrity, and source locks.
  - `uv run --no-sync python -B scripts/verify.py --publication-ready` - 469 passed plus publication-ready hygiene and source locks.
- Latest successful remote CI: GitHub Actions `Verify` run
  `https://github.com/adamowada/codex-supervisor/actions/runs/26405139863` for commit
  `79ec62e1e575e1709c5cdec6241403b29944297d`.
- Worker backend note: local `codex --version` still fails with Access denied for the resolved
  WindowsApps executable, so native Goal Mode worker launch remains unavailable for this worker
  until the CLI path and `CODEX_HOME` are confirmed.

## Stage 15A Summary

Review anchor: stage15a-review.
Review result anchor: stage15a-review-result.
Summary anchor: stage15a-summary.

Task: `task-stage15a-release-readiness-audit`.
Plan: `plan-stage15-release-hardening`.
Worker run: `worker-run-stage15a-release-readiness-audit-inline-20260525`.
Status: completed in planning SQLite after worker-result ingest and review-result recording.

Implemented:

- Added `src/codex_supervisor/release.py` with frozen typed release-readiness report/check
  contracts and deterministic repo-owned checks for CLI, MCP, plugin, spawned-project scaffold,
  verification, documentation, Linux CI surface, and external Windows validation.
- Added CLI command `release-readiness` with deterministic JSON and human-readable dry-run output.
- Added focused release-readiness tests for current repo evidence, empty/missing evidence, JSON
  output, and human output.
- Updated file-purpose justification for the new release audit module and tests.
- Release-readiness output currently reports 8 passing checks and 1 explicit gap:
  external Windows install validation evidence is not tracked yet.
- Review `review-stage15a-release-readiness-audit-20260525` found one accepted P3 issue: text-based
  gap checks could emit optimistic evidence. The repair now emits `present:` / `missing:` evidence
  for text contracts and covers missing CLI/docs/CI evidence in tests.
- Updated `insights/workflow-patterns.md` with durable lessons for explicit missing evidence in gap
  reports and UTF-8-without-BOM JSON import artifacts on Windows.

Verification passed locally:

```sh
uv run --no-sync python -B -m pytest tests/test_release_readiness.py tests/test_file_justification.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```

## Next Action

Run planning integrity, ACP, push, inspect remote CI, then select the next current AFK slice from
planning SQLite.

```sh
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
```
