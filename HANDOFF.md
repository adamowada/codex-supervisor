# HANDOFF.md

Last updated: 2026-05-25 04:46 PDT

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Active Goal posture: dangerous_full_auto/approved_afk Story Loop execution, one current AFK slice
  at a time from planning SQLite.
- Current queue state: `ready`.
- Current AFK task: `task-stage13a-github-actions-verify` on
  `plan-stage13-github-ci-integration`.
- Current slice: ROADMAP Stage 13A, add the first GitHub Actions verification workflow and local
  workflow contract tests so pushes and pull requests to `main` can produce public CI evidence.
- Latest completed plan: `plan-stage12-codex-plugin-desktop-experience`
  (`Stage 12 Codex Plugin And Desktop Experience`).
- Worker backend note: local `codex --version` still fails with Access denied for the resolved
  WindowsApps executable, so native Goal Mode worker launch remains unavailable for this worker
  until the CLI path and `CODEX_HOME` are confirmed.

## Stage 13A Ready Contract

Plan: `plan-stage13-github-ci-integration`.
Task: `task-stage13a-github-actions-verify`.
Status: `ready`.
Review required: yes, because GitHub Actions workflow files define public CI behavior.

Allowed paths:

- `.github/workflows/verify.yml`
- `tests/test_github_ci.py`
- `scripts/check_file_justification.py`
- `plans/planning.sqlite3`
- `HANDOFF.md`
- `insights/**`
- `.agents/skills/**`

Acceptance criteria:

- Repository includes a GitHub Actions verification workflow that runs on pull requests and pushes
  to `main` without requiring secrets.
- The workflow runs the repo-owned setup and verification commands needed for public CI evidence,
  including `uv sync` and publication-ready verification.
- Focused workflow contract tests, file-purpose hygiene, planning integrity, full verification, and
  publication-ready hygiene checks pass with the workflow included.

Verification commands:

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

Claim and execute `task-stage13a-github-actions-verify`. Keep the slice scoped to the workflow,
focused workflow contract tests, file-purpose hygiene, planning SQLite, and this handoff. After
implementation, run the task verification commands, complete a fresh-thread-style review, ingest the
worker result, update the Stage 13A completion evidence, and ACP.
