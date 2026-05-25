# Release Readiness Evidence

- `claim`: When release evidence is stored in tracked planning SQLite or compact handoff/insight
  files, a final evidence-only commit must be treated as an audit wrapper around the code or doctrine
  commit it validates.
- `confidence`: confirmed
- `evidence`: `src/codex_supervisor/release.py`, `tests/test_release_readiness.py`, and planning
  evidence under `plans/planning.sqlite3` for `plan-v1-live-operational-hardening`.
- `scope`: release-readiness audits that require current CI, Windows validation, live smoke, and
  publication-ready evidence while storing that evidence in repo-owned tracked state.
- `supersedes`: none
- `next action`: Keep live release evidence in planning SQLite, but evaluate trailing evidence-only
  commits against the latest audited code/doc commit so the final ACP can be both published and
  checkable.

## Live Codex Launch Environment

- `claim`: Windows live Codex worker subprocesses need a minimal environment allowlist that matches
  variable names case-insensitively, because required runtime keys such as `SYSTEMROOT` may not use
  the mixed-case spelling in source code.
- `confidence`: confirmed
- `evidence`: failed worker run `worker-run-v1-live-worker-smoke-cmd-20260525` in
  `plans/planning.sqlite3`, `src/codex_supervisor/worker_backends.py`, and
  `tests/test_worker_backends.py`.
- `scope`: live `codex.cmd` launches from `CodexExecBackend` on Windows.
- `supersedes`: none
- `next action`: Keep the subprocess environment allowlist minimal, but compare environment keys
  case-insensitively and preserve the host-provided key spelling.

## Live Codex Exec Paths

- `claim`: Live Codex Exec argv paths must be absolute when the supervisor also sets the subprocess
  working directory, otherwise relative `--cd`, schema, and output paths are resolved from the wrong
  directory.
- `confidence`: confirmed
- `evidence`: failed worker run `worker-run-v1-live-worker-smoke-envfix-20260525` in
  `plans/planning.sqlite3`, `src/codex_supervisor/worker_backends.py`, and
  `tests/test_worker_backends.py`.
- `scope`: `CodexExecBackend` live launches with repo-root-relative run artifacts and worktrees.
- `supersedes`: none
- `next action`: Build Codex Exec argv from resolved repo/worktree paths while preserving
  repo-relative paths only in redacted metadata and planning records.
