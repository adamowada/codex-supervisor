# HANDOFF.md

Last updated: 2026-05-25 04:55 PDT

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Active Goal posture: dangerous_full_auto/approved_afk Story Loop execution, one current AFK slice
  at a time from planning SQLite.
- Current queue state: `completed`.
- Current AFK task: none. `story-loop-status --json` reports no open work remains on the active
  Stage 13 plan after Stage 13A completed.
- Current plan: `plan-stage13-github-ci-integration` remains active for follow-up Stage 13 slices.
- Latest completed task: `task-stage13a-github-actions-verify`.
- Latest completed plan: `plan-stage12-codex-plugin-desktop-experience`
  (`Stage 12 Codex Plugin And Desktop Experience`).
- Worker backend note: local `codex --version` still fails with Access denied for the resolved
  WindowsApps executable, so native Goal Mode worker launch remains unavailable for this worker
  until the CLI path and `CODEX_HOME` are confirmed.

## Stage 13A Summary

Plan: `plan-stage13-github-ci-integration`.
Task: `task-stage13a-github-actions-verify`.
Status: `completed`.
Worker run: `worker-run-stage13a-github-actions-verify-inline-20260525`.
DB result: `worker-result-stage13a-github-actions-verify-result`.
Review: `review-stage13a-github-actions-verify-20260525`, 0 findings.
Completion progress: `progress-stage13a-github-actions-verify-completed-20260525`.

Implemented:

- Added `.github/workflows/verify.yml`, the first GitHub Actions workflow for the repository.
- The workflow runs on pushes and pull requests to `main`, uses read-only `contents` permissions,
  installs uv, sets up Python 3.14, runs `uv sync --dev --locked`, and runs
  `uv run python -B scripts/verify.py --publication-ready`.
- Added `tests/test_github_ci.py` to contract-test triggers, read-only/no-secrets posture, action
  setup, Python version, and verification commands.
- Added `.github` workflow purpose coverage to `scripts/check_file_justification.py`.
- Captured the CI publication-gate lesson in `insights/workflow-patterns.md`.

### Stage 13A Review

Fresh-thread-style review was completed against the staged diff because workflow files define public
CI behavior. Result: 0 accepted, 0 waived, 0 needs-HITL findings.

### Stage 13A Verification

Passed with Stage 13A included:

```sh
uv run --no-sync python -B -m pytest tests/test_github_ci.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/check_file_justification.py
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```

Stop conditions:

- A HITL task becomes current in planning SQLite.
- The workflow requires secrets, deployment credentials, paid services, or release publishing.
- GitHub workflow semantics cannot be locally contract-tested without a new dependency or external
  service.
- Verification repeatedly fails without a known repo-local fix.

Remote preflight:

- Repository: `adamowada/codex-supervisor`.
- Default branch: `main`.
- Pre-slice head: `2ea64701e714afeba15df526b07e93cf749ae29f`.
- GitHub connector observed 0 workflow runs and 0 commit statuses for that head.

Residual Stage 13A risk:

- Remote GitHub Actions execution is not observed until the workflow commit is pushed and GitHub
  schedules a run.
- Later Stage 13 slices still need PR metadata, CI status ingestion, repair-loop routing, merge
  policy, release notes, and post-merge cleanup.

## Stage 12C Summary

Completed task: `task-stage12c-plugin-clean-discovery`.

- Worker run: `worker-run-stage12c-plugin-clean-discovery-inline-20260525`.
- DB result: `worker-result-stage12c-plugin-clean-discovery-result`.
- Review: `review-stage12c-plugin-clean-discovery-20260525`, 0 findings.
- Completion progress: `progress-stage12c-plugin-clean-discovery-completed-20260525`.
- Implementation commit: `66e122ca591af35840788a21ca9a281215b7377a`.
- Stage 12 plan status: `completed`.

Implemented:

- Added `scripts/verify_codex_plugin_install.py`, a clean local plugin discovery smoke verifier.
- The verifier creates an isolated temporary `codex-home` and fresh project, validates plugin
  manifest relative paths and packaged skills, resolves the MCP cwd to the repo root, and exercises
  the configured MCP stdio server through `initialize` and `tools/list`.
- Documented the smoke-check command in `plugins/codex-supervisor/README.md`.
- Expanded `tests/test_codex_plugin.py` to cover verifier discovery and MCP lifecycle behavior.
- Added file-purpose coverage for the new verifier.
- Captured the command-safety shaping lesson in `insights/workflow-patterns.md` and
  `.agents/skills/afk-issue-shaper/SKILL.md`.

Residual Stage 12 risk:

- The verifier proves clean local plugin source discovery and MCP stdio startup, but it does not
  automate the Codex Desktop GUI or mutate a real Desktop profile.
- Marketplace or personal plugin registry writes remain out of scope.
- Live worker launch and mutating MCP tools remain out of scope until backend preflight and queue
  scope explicitly allow them.

## Verification Evidence

Passed after the Stage 12C implementation:

```sh
uv run --no-sync python -B scripts/verify_codex_plugin_install.py
uv run --no-sync python -B -m pytest tests/test_codex_plugin.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/check_file_justification.py
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```

`scripts/verify.py` and `scripts/verify.py --publication-ready` both passed with 436 tests plus
style, type, planning, public hygiene, source inventory, skill inventory, protected-file, and
`uv lock --check` gates.

## Prior Stage 12 Checkpoints

- Stage 12A completed task: `task-stage12a-plugin-mcp-scaffold`.
- Stage 12A worker run: `worker-run-stage12a-plugin-mcp-scaffold-inline-20260525`, completed with
  DB result `worker-result-stage12a-plugin-mcp-scaffold-result`.
- Stage 12A implementation commit: `02a4ae986f3ed7fed8506787b9f863fe35aac1bd`.
- Stage 12A evidence link commit: `332d2e7f5f18775d765c757ea030b754008bff1e`.
- Stage 12B completed task: `task-stage12b-plugin-skill-workflows`.
- Stage 12B worker run: `worker-run-stage12b-plugin-skill-workflows-inline-20260525`, completed
  with DB result `worker-result-stage12b-plugin-skill-workflows-result`.
- Stage 12B implementation commit: `46f140dea6c05e6bd1deeb7036aab6346ad6c627`.
- Stage 12B evidence link commit: `1be4832a26ab9918a46c163a0b0d9af1cb8f4682`.
- Stage 12C shaping commit: `f75c304`.
- Stage 12C claim commit: `7660bf4`.

## Next Action

Shape the next ROADMAP Stage 13 slice in planning SQLite. The practical next AFK slice is to inspect
the first remote workflow/check result after the Stage 13A commit is pushed and record CI evidence,
a repair task, or a HITL blocker in planning SQLite. Do not create or merge PRs, configure secrets,
or change branch protection unless a later task contract explicitly scopes that work.
