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

## Worker Result Structured Output Schema

- `claim`: Live Worker Result schemas passed to Codex Exec must use strict Structured Outputs
  objects with `additionalProperties: false`, and acceptance-result keys should be generated from
  the task contract.
- `confidence`: confirmed
- `evidence`: failed worker run `worker-run-v1-live-worker-smoke-abspath-20260525`, OpenAI
  Structured Outputs documentation, `src/codex_supervisor/worker_backends.py`, and
  `tests/test_worker_backends.py`.
- `scope`: `CodexExecBackend` output schemas supplied through `codex exec --output-schema`.
- `supersedes`: none
- `next action`: Keep Worker Result validation stricter than the model schema when needed, but make
  the model-facing schema acceptable to the live API.

## Live Review Structured Output Schema

- `claim`: Live Review Result schemas need the same strict Structured Outputs posture as worker
  results, and review launch argv paths should be absolute when Codex Exec is launched with an
  explicit working directory.
- `confidence`: confirmed
- `evidence`: `src/codex_supervisor/review_persistence.py`,
  `tests/test_review_persistence.py`, and the live worker schema failure recorded as
  `worker-run-v1-live-worker-smoke-abspath-20260525` in `plans/planning.sqlite3`.
- `scope`: `CodexReviewBackend` launches through `codex exec --output-schema`.
- `supersedes`: none
- `next action`: Keep reviewer model schemas strict at every object boundary and keep subprocess
  paths resolved before running live review smokes.

## Worker Result Identity

- `claim`: DB-backed Worker Result IDs must include source-path context, not only a filename stem,
  because live artifact layouts commonly reuse names such as `worker-result.raw.json`.
- `confidence`: confirmed
- `evidence`: `scripts/check_planning_integrity.py` rejected the collision between
  `worker-run-stage11b-mcp-stdio-transport-inline-20260525` and
  `worker-run-v1-live-worker-smoke-trusted-20260525`; live review
  `review-v1-live-smoke-f09681c-scopefix-20260525` found the follow-up long common-prefix collision
  risk; fixed in `src/codex_supervisor/planning.py` and `tests/test_planning.py`.
- `scope`: worker result ingestion, re-ingestion, and compatibility result records in
  `plans/planning.sqlite3`.
- `supersedes`: filename-stem-only worker result IDs.
- `next action`: Keep worker-result links single-owner per run unless a structured result explicitly
  declares multiple worker runs, replace stale links when a run is re-ingested, and include a
  normalized source-path digest in generated result IDs.

## Live Review Smoke Scope

- `claim`: A live review smoke task that targets a real commit must include the full target
  changed-file set in its contract, otherwise the reviewer can correctly classify omitted files as
  source-of-truth drift even when the implementation is intentional.
- `confidence`: confirmed
- `evidence`: live review `review-v1-live-smoke-f09681c-20260525` recorded a P2 needs-HITL finding
  because the smoke task omitted `src/codex_supervisor/planning.py`, `tests/test_planning.py`, and
  `insights/release-readiness-evidence.md` from its allowed paths.
- `scope`: live `review-run-live` smoke evidence that reviews a commit instead of a single-file or
  single-feature target.
- `supersedes`: none
- `next action`: Expand the smoke task contract to match the reviewed commit scope before rerunning
  live review evidence.
