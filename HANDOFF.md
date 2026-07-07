# HANDOFF.md

Last updated: 2026-07-07

This is the current resume snapshot.

## Current State

Branch: `feature/substrate`

Master plan: `SUBSTRATE_PLAN.md`

Current product identity: `codex-supervisor` is the durable evidence substrate for Codex Goal Mode.
Goal Mode owns objective, strategy, sequencing, launch packet content, recovery decisions, and final
completion judgment. Supervisor owns durable state, launch records, worker assignment, evidence,
product provenance, acceptance, auditability, and compact recovery state.

Current model:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Active surface:

- CLI: `plan-init`, `task-create`, `queue-next`, `attempt-transition`, `attempt-run`
- MCP: `codex_supervisor.queue_next`
- Plugin: thin Desktop wrapper around the same source CLI and MCP stdio server
- Repo-local skills: `codex-supervisor`, `improve-codebase-architecture`,
  `reduce-codebase-complexity`

Planning database:

- `meta`
- `plans`
- `tasks`
- `attempts`
- `evidence_bundles`
- `acceptance_decisions`
- `decisions`

`plans/planning.sqlite3` and `HANDOFF.md` must stay current together.

## Substrate Pivot

The source-of-truth docs, repo-local skill, packaged Desktop skill, plugin README, plugin metadata,
package metadata, protected lock manifest, planning ledger, and handoff now align around the
substrate role split:

- Goal Mode thinks, sequences, recovers, and decides completion.
- Supervisor remembers, launches, verifies, records evidence, enforces product provenance, and
  exposes compact recovery state.
- Worker processes remain ephemeral and receive intelligence from Goal Mode launch packets.
- Work categories stay in task intent, launch packets, acceptance criteria, and generic lineage,
  not supervisor job types.

`SUBSTRATE_PLAN.md` is protected as a source-of-truth file for the branch plan. Protected source
locks were refreshed in `scripts/check_protected_files.py` and `src/codex_supervisor/locks.py`.

## Current Verification

Focused checks completed:

```text
AI prose audit over steering Markdown and plugin guidance
No matches for the audited stock phrase set after edits.

uv run --no-sync python -B scripts/check_protected_files.py
Protected source-of-truth files are unchanged.

uv run --no-sync python -B scripts/check_skill_inventory.py
Skill inventory checks passed.

uv run --no-sync python -B scripts/check_planning_integrity.py
Fresh planning integrity checks passed.
```

Full verification completed:

```text
uv run --no-sync python -B scripts/verify.py
106 passed
```

## Planning Ledger

Active plan:

- `plan-substrate-20260707`: `Goal Mode substrate pivot`

Accepted tasks:

- `task-align-substrate-docs-20260707`: aligned source contracts, skills, metadata, protected
  hashes, planning ledger, handoff, and verification with the substrate branch plan.
- `task-remove-ai-prose-steering-docs-20260707`: tightened steering docs using the Pangram and
  Grammarly common-AI-prose references, refreshed protected hashes, and verified the repo.
- `task-launch-packet-capture-20260707`: added `attempt-run --launch-packet` and
  `--verifier-intent`, copied and hashed those files before worker product mutation, injected
  packet references into assignment metadata and worker environment, wrote launch-time
  `command.json` with workspace and cwd metadata, added focused e2e coverage, refreshed source
  locks, and verified the repo.
- `task-generic-lineage-20260707`: added `tasks.lineage_json`, `task-create --lineage`, queue
  projection of task lineage, integrity validation for lineage references, schema v3 migration,
  focused tests, source-lock refresh, and verified the repo.
- `task-recovery-state-20260707`: added latest acceptance reads, compact `recovery_state` output
  through CLI and MCP, liveness file age when available, packet hash recovery, lineage projection,
  git summary, warning flags, focused tests, source-lock refresh, and verified the repo.
- `task-evidence-digests-20260707`: added compact evidence digests to terminal evidence, exposed
  parsed digests through latest evidence and recovery state, preserved raw artifact references,
  refreshed source locks, and verified the repo.
- `task-linked-repair-20260707`: made blocked queue inspection surface repair-lineage guidance,
  allowed linked repair tasks to reactivate blocked plans through task intent, refreshed source
  locks, and verified the repo.

Ready next task:

- `task-shipping-proof-20260707`: represent shipping and final proof as supervised task intent and
  recovery evidence.

## Next Action

Implement final proof workflow for `task-shipping-proof-20260707`.
