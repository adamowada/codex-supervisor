# V1 Hardening Review

- `claim`: The six-lane v1 review found that the current tree has strong planning, result,
  hygiene, and source-lock foundations, but v1 is not yet live-operational because worker launch,
  MCP mutation, real project bootstrap, live review, and release evidence still contain proposal,
  dry-run, or mock-only gaps.
- `confidence`: confirmed
- `evidence`: `plans/planning.sqlite3` plan `plan-v1-live-operational-hardening`, progress
  `progress-v1-six-lane-review-digested-20260525`, six read-only explorer reports, and the local
  production-readiness scan on 2026-05-25.
- `scope`: v1 hardening, live Codex execution, worktree isolation, MCP/plugin parity, project
  adapters, spawned-project bootstrap, review routing, release readiness, security, and public
  hygiene.
- `supersedes`: none
- `next action`: Execute `task-v1-live-story-loop-worker` first, then unblock the dependent MCP,
  live review, release evidence, and final completion-audit tasks.

## Normalized Finding Clusters

- `live-worker`: production Story Loop launch is missing; `CodexExecBackend` needs real Worker
  Result instructions, Goal Contract prompt composition, enforced launch options, isolated worktree
  setup, authoritative changed-path evidence, JSONL capture, result validation, minimal environment,
  prompt/argv redaction, and timeouts.
- `mcp`: MCP is still read-only and tests encode that obsolete contract. V1 needs default-on
  mutating tools with explicit opt-out, allowed-root enforcement, and path redaction.
- `automation`: the Codex automation bridge is proposal-only; a production apply path remains.
- `bootstrap-adapters`: spawned-project bootstrap is proposal-only, adapter task seeding can persist
  local roots, supervisor planning DBs are not the first planning adapter shape, and generated
  source-lock behavior is not project-specific yet.
- `review`: review-required tasks can be marked complete without review evidence, live reviewer
  launch is missing, review ingestion is not atomic with repair routing, and repair task id reuse
  needs equivalence checks.
- `release`: release readiness can pass stale CI/Windows evidence and shallow dry-run/demo surfaces
  instead of current live worker, review, MCP, and real bootstrap smoke evidence.
- `security-hygiene`: worker result ingestion preserves unknown raw payload fields, Codex-state
  reconciliation can link phantom artifacts, and CI action pinning needs a deliberate supply-chain
  posture.

## Confirmed Foundations

- Planning SQLite is the canonical operational store with typed helpers and integrity checks.
- Worker Result validation and DB-backed result ingestion exist.
- Source-lock, public-hygiene, file-purpose, skill, source, and aggregate verification gates exist.
- Project adapter infrastructure, Goal Contract rendering, Codex local-state read-only telemetry,
  review result schemas, review persistence, and repair-task routing all exist; the gaps are live
  launch paths, stricter evidence rules, and real scaffold/application behavior.
