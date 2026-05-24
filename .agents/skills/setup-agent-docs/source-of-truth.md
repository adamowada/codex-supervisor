# Source Of Truth

Record the repo's authority matrix.

Typical matrix for `codex-supervisor` spawned projects:

- Locked source-of-truth docs govern durable doctrine, architecture, contracts, testing policy,
  roadmap intent, and stable operating rules.
- Planning SQLite governs active and blocked current-queue plans, current queue state, task status,
  worker runs, progress events, and handoff order.
- GitHub issues and PRs govern remote tracker state only after reconciliation into planning SQLite.
- Handoff artifacts are mutable snapshots.
- Chat/session history is context, not durable authority.

When sources disagree, stop and surface the conflict unless the repo documents a clear precedence rule.
