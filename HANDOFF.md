# HANDOFF.md

Last updated: 2026-05-25 04:27 PDT

This file is a compact handoff snapshot only. Canonical queue state, completion records, imported
legacy evidence, and operational progress are in `plans/planning.sqlite3`.

## Current Snapshot

- Active Goal posture: dangerous_full_auto/approved_afk Story Loop execution, one current AFK slice
  at a time from planning SQLite.
- Current queue state: `ready`.
- Active plan: `plan-stage12-codex-plugin-desktop-experience`
  (`Stage 12 Codex Plugin And Desktop Experience`, priority 78).
- Current AFK task: `task-stage12c-plugin-clean-discovery`.
- Worker backend note: local `codex --version` still fails with Access denied for the resolved
  WindowsApps executable, so native Goal Mode worker launch remains unavailable for this worker
  until the CLI path and `CODEX_HOME` are confirmed.

## Stage 12C Contract

Goal: add a repo-owned clean Codex Desktop plugin discovery smoke verifier that validates the plugin
source from an isolated temporary profile/project, proves manifest, skills, MCP cwd, and MCP stdio
lifecycle behavior, and keeps real Desktop install state, marketplace writes, and live worker launch
out of scope.

Allowed paths:

```text
plugins/codex-supervisor/**
scripts/verify_codex_plugin_install.py
tests/test_codex_plugin.py
scripts/check_file_justification.py
plans/planning.sqlite3
HANDOFF.md
insights/**
.agents/skills/**
```

Acceptance criteria:

- A repo-owned clean plugin install smoke verifier uses an isolated temporary Codex profile/project
  and validates plugin discovery without writing real Codex Desktop state.
- The verifier proves plugin manifest relative paths, packaged skills, MCP config cwd resolution,
  and the configured MCP stdio lifecycle from the plugin source.
- Focused plugin tests, file-purpose hygiene, planning integrity, full verification, and
  publication-ready hygiene checks pass with the clean-discovery verifier included.

Verification commands:

```sh
uv run --no-sync python -B -m pytest tests/test_codex_plugin.py -q -p no:cacheprovider
uv run --no-sync python -B scripts/check_file_justification.py
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```

Stop conditions:

- A HITL task becomes current in planning SQLite.
- The slice requires mutating a real Codex Desktop profile, marketplace registry, external
  credentials, or UI automation.
- The verifier cannot prove discovery without relying on machine-local Desktop state.
- Verification repeatedly fails without a known repo-local fix.

Out of scope:

- Actual Codex Desktop GUI automation or user profile mutation.
- Marketplace or personal plugin registry writes.
- Live Codex worker launch or mutating MCP tools.
- GitHub/CI integration, release packaging, or Stage 13 behavior.

## Stage 12B Summary

Completed task: `task-stage12b-plugin-skill-workflows`.

- Worker run: `worker-run-stage12b-plugin-skill-workflows-inline-20260525`.
- DB result: `worker-result-stage12b-plugin-skill-workflows-result`.
- Review: `review-stage12b-plugin-skill-workflows-20260525`, 0 findings.
- Completion progress: `progress-stage12b-plugin-skill-workflows-completed-20260525`.
- Implementation commit: `46f140dea6c05e6bd1deeb7036aab6346ad6c627`.

Implemented:

- Added `skills/codex-supervisor/SKILL.md` under the repo-local plugin as a Desktop-discoverable
  workflow entrypoint.
- Added `"skills": "./skills/"` to `plugins/codex-supervisor/.codex-plugin/plugin.json`.
- Documented the Desktop workflow map for project bootstrap, queue inspection, worker launch,
  review, ACP, and handoff in `plugins/codex-supervisor/README.md`.
- Extended `tests/test_codex_plugin.py` and `scripts/check_file_justification.py` for the packaged
  skill surface.

Out of scope remains unchanged for the next Stage 12 slice:

- Clean Codex Desktop profile install verification.
- Marketplace or personal plugin registry writes.
- Bulk-copying the repo-local `.agents/skills/` library into the plugin archive.
- Mutating MCP tools, GitHub/CI integration, release packaging, or live worker launch.

## Verification Evidence

Passed after the Stage 12B implementation:

```sh
uv run --no-sync python -B -m pytest tests/test_codex_plugin.py -q -p no:cacheprovider
uv run --with pyyaml --no-project python -B <plugin-creator>/scripts/validate_plugin.py plugins/codex-supervisor
uv run --with pyyaml --no-project python -B <skill-creator>/scripts/quick_validate.py plugins/codex-supervisor/skills/codex-supervisor
uv run --no-sync python -B scripts/check_file_justification.py
uv run --no-sync python -B scripts/check_planning_integrity.py
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B scripts/verify.py
uv run --no-sync python -B scripts/verify.py --publication-ready
```

`scripts/verify.py` and `scripts/verify.py --publication-ready` both passed with 435 tests plus
style, type, planning, public hygiene, source inventory, skill inventory, protected-file, and
`uv lock --check` gates.

## Prior Checkpoints

- Stage 12A completed task: `task-stage12a-plugin-mcp-scaffold`.
- Stage 12A worker run: `worker-run-stage12a-plugin-mcp-scaffold-inline-20260525`, completed with
  DB result `worker-result-stage12a-plugin-mcp-scaffold-result`.
- Stage 12A implementation commit: `02a4ae986f3ed7fed8506787b9f863fe35aac1bd`.
- Stage 12A evidence link commit: `332d2e7f5f18775d765c757ea030b754008bff1e`.
- Stage 12B shaping commit: `64c5c7924f61e120eadc2259dcca72db719757b1`.

## Next Action

Execute `task-stage12c-plugin-clean-discovery` through the Story Loop. Run the task verification
commands, perform the required fresh-thread-style review, fix accepted findings, update planning
SQLite and this handoff, then ACP the step.
