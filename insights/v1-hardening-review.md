# V1 Hardening Review

- `claim`: The six-lane v1 review found that the tree had strong planning, result, hygiene, and
  source-lock foundations, but v1 was not yet live-operational. The live worker, MCP mutation, and
  real project bootstrap/adapters, live review integrity, and release-evidence readiness slices
  have now landed; security/public-hygiene hardening has now landed as well. Automation apply and
  current live evidence capture remain unresolved blockers.
- `confidence`: confirmed
- `evidence`: `plans/planning.sqlite3` plan `plan-v1-live-operational-hardening`, progress
  `progress-v1-six-lane-review-digested-20260525`, six read-only explorer reports, and the local
  production-readiness scan on 2026-05-25.
- `scope`: v1 hardening, live Codex execution, worktree isolation, MCP/plugin parity, project
  adapters, spawned-project bootstrap, review routing, release readiness, security, and public
  hygiene.
- `supersedes`: none
- `next action`: Continue with final completion-audit/live-smoke work, including current
  CI/Windows/live evidence capture and any remaining automation apply gap.

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
- `review`: live reviewer launch, review-required completion enforcement, prevalidated repair
  routing, and repair-task collision equivalence checks are now implemented. Keep review evidence
  tied to explicit `review_enforcement_enabled` markers so legacy planning history remains readable.
- `release`: release readiness now targets a commit, defaults to current `HEAD`, rejects stale
  CI/Windows evidence, requires current publication-ready verification plus live worker/review,
  mutating MCP, and real bootstrap smoke evidence, and explicitly excludes the factory-loop smoke as
  v1 release evidence.
- `security-hygiene`: Worker Result ingestion now caps raw JSON size and omits non-contract keys
  from tracked SQLite raw payloads; Codex-state reconciliation no longer creates phantom snapshot
  artifact links; GitHub Actions are pinned to reviewed full commit SHAs.

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
- Remaining v1 hardening clusters are still real blockers until their tasks land: current release
  evidence, automation apply, and security/public-hygiene follow-ups outside the live worker slice.

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
- Remaining v1 hardening clusters are still real blockers until their tasks land: current release
  evidence, automation apply, and security/public-hygiene follow-ups outside the MCP slice.

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
- Remaining v1 hardening clusters are still real blockers until their tasks land: current release
  evidence, automation apply, and security/public-hygiene follow-ups outside the bootstrap/adapters
  slice.

## Live Review Integrity Slice Update

- `task-v1-live-review-integrity` adds a live Codex review runner that builds a structured review
  prompt/schema, runs `codex exec`, validates the emitted `ReviewResult`, persists review evidence,
  routes accepted findings into repair tasks, and keeps needs-HITL reviews in `reviewing`.
- `review-result-ingest` and the MCP review-ingest handler now prevalidate repair task routing
  before recording review progress, then apply the prevalidated plan. Existing deterministic repair
  task IDs are treated as idempotent only when the existing task contract matches the expected
  review finding.
- Planning integrity now enforces review evidence for completed `review_required` tasks after a
  plan records `review_enforcement_enabled`; this avoids rewriting legacy history while guarding
  future completions.
- Remaining v1 hardening clusters are still real blockers until their tasks land: current live
  evidence capture, automation apply, and security/public-hygiene follow-ups outside the review
  slice.

## Release Evidence Slice Update

- `task-v1-release-current-live-evidence` makes `release-readiness` resolve a target commit
  (defaulting to `git rev-parse HEAD`) and reject stale `ci_run_recorded` and
  `release_validation_recorded` rows whose `head_sha` does not match that target.
- Release readiness now requires current-commit evidence rows for successful CI, Windows
  validation, publication-ready verification, live worker smoke, live review smoke, mutating MCP
  smoke, and real project bootstrap smoke before it can report ready.
- The spawned-project readiness check now verifies the real `spawned-project-apply` surface, not
  only dry-run classify/propose paths.
- `factory-loop-smoke` remains a deterministic local exercise but is marked `release_evidence=false`
  and its progress/evidence strings say it is not v1 release-readiness evidence.
- Remaining v1 hardening clusters are still real blockers until their tasks land: current live
  evidence capture, automation apply, and security/public-hygiene follow-ups outside the release
  readiness slice.

## Security/Public-Hygiene Slice Update

- `task-v1-security-public-hygiene-hardening` adds a Worker Result file-size cap and stores only
  contract fields in tracked `worker_result_records.raw_payload_json`; omitted unknown keys are
  listed in metadata without preserving their values.
- Codex-state reconciliation dry-runs now propose progress/finding evidence only. Apply no longer
  links `codex-state-snapshots/<hash>.json` files that do not exist, so publication-ready hygiene
  does not depend on phantom artifacts.
- `.github/workflows/verify.yml` now pins external actions to full commit SHAs resolved from
  reviewed release tags, and `tests/test_github_ci.py` enforces that supply-chain posture.
- Remaining v1 hardening blockers: final audit must record current post-ACP CI/Windows/live-smoke
  evidence, confirm release-readiness for the final target commit, and resolve the automation apply
  gap or record a deliberate product decision.
