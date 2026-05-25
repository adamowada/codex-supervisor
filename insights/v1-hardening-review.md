# V1 Hardening Review

- `claim`: The six-lane v1 review found that the tree had strong planning, result, hygiene, and
  source-lock foundations, but v1 was not yet live-operational. The live worker, MCP mutation, and
  real project bootstrap/adapters slices have now landed; live review, release evidence, automation
  apply, and security/public-hygiene hardening remain unresolved blockers.
- `confidence`: confirmed
- `evidence`: `plans/planning.sqlite3` plan `plan-v1-live-operational-hardening`, progress
  `progress-v1-six-lane-review-digested-20260525`, six read-only explorer reports, and the local
  production-readiness scan on 2026-05-25.
- `scope`: v1 hardening, live Codex execution, worktree isolation, MCP/plugin parity, project
  adapters, spawned-project bootstrap, review routing, release readiness, security, and public
  hygiene.
- `supersedes`: none
- `next action`: Continue with live review, current release evidence, security/public-hygiene, and
  final completion-audit tasks.

## Normalized Finding Clusters

- `live-worker`: production Story Loop launch is missing; `CodexExecBackend` needs real Worker
  Result instructions, Goal Contract prompt composition, enforced launch options, isolated worktree
  setup, authoritative changed-path evidence, JSONL capture, result validation, minimal environment,
  prompt/argv redaction, and timeouts.
- `mcp`: MCP needed default-on mutating tools with explicit opt-out, allowed-root enforcement, and
  path redaction. The MCP hardening slice now implements that production surface; keep it covered by
  plugin and stdio verifier tests.
- `automation`: the Codex automation bridge is proposal-only; a production apply path remains.
- `bootstrap-adapters`: spawned-project bootstrap now has a real apply path and adapter task
  seeding no longer persists local roots; keep future adapters DB-first, repo-relative, and
  project-specific instead of proposal-only.
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

## Live Worker Slice Update

- `task-v1-live-story-loop-worker` adds a production `story-loop-run-once` service/CLI path that
  claims one ready AFK task, records run/worktree metadata, creates an isolated git worktree, runs
  the live Codex Exec backend, requires git/worktree changed-path evidence, and ingests a validated
  Worker Result into planning SQLite.
- `CodexExecBackend` now composes the Goal Contract and Worker Result instructions into a stdin
  prompt, writes a run-local JSON schema artifact, redacts prompt/local paths from metadata,
  captures JSONL/stdout/stderr/final-message evidence, enforces CODEX_HOME conflicts and unsupported
  launch options fail-closed, uses bounded timeouts, and launches with a minimal environment
  allowlist.
- Remaining v1 hardening clusters are still real blockers until their tasks land: live review
  integrity, current release evidence, automation apply, and security/public-hygiene follow-ups
  outside the live worker slice.

## MCP Mutation Slice Update

- `task-v1-mutating-mcp-tools` adds default-on mutating MCP tools for plan, milestone, criterion,
  decision, task, worker-run, progress, artifact, Story Loop record, Worker Result ingestion, live
  Story Loop launch, and review-result ingestion workflows.
- Mutating tools are hidden from `tools/list` and reject dispatch when the MCP stdio server is
  started with `--disable-mutations`; the default plugin path leaves mutations enabled.
- `codex_supervisor.project_list` now rejects roots outside configured project roots and redacts
  local absolute paths from MCP results. CLI project-list output remains the operator-facing local
  view; MCP is the privacy-safe Desktop/client boundary.
- Verification evidence for this slice includes the focused MCP stdio/plugin tests and the clean
  plugin install verifier, which now requires the production mutation, launch, and review-ingest
  MCP tools.
- Remaining v1 hardening clusters are still real blockers until their tasks land: live review
  integrity, current release evidence, automation apply, and security/public-hygiene follow-ups
  outside the MCP slice.

## Real Bootstrap/Adapter Slice Update

- `task-v1-real-project-bootstrap-adapters` adds `spawned-project-apply`, which writes the selected
  scaffold into a target root with project-specific docs, generated verification scripts, generated
  protected-file hashes, initialized planning SQLite, and a first AFK task contract.
- Generated verification is tier-aware: full production scaffolds run file-purpose, source-lock,
  planning-integrity, and public-hygiene checks, while prototype-light scaffolds still verify their
  required files without calling missing supervisor-managed scripts.
- Project adapter seeding keeps `source_project` scope to safe project IDs, adapter type, and trust
  policy; local absolute roots stay in operator-facing discovery output and are not written into
  supervisor task scope. The planning SQLite adapter now prefers `supervisor_tasks` before the
  legacy `tasks` table.
- Remaining v1 hardening clusters are still real blockers until their tasks land: live review
  integrity, current release evidence, automation apply, and security/public-hygiene follow-ups
  outside the bootstrap/adapters slice.
