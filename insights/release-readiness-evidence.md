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
