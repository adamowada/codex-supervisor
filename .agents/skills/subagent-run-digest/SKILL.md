---
name: subagent-run-digest
description: Summarize and compare subagent runs, explorer reports, worker outputs, spawn graphs, temp worktrees, or multi-agent experiment results. Use when coordinating many Codex agents or recovering from subagent fanout.
---

# Subagent Run Digest

Collapse many agents into one decision-ready artifact.

## Digest Shape

- parent objective;
- agent roster and roles;
- status: completed, open, failed, timed out, or closed;
- per-agent finding summary;
- changed files or read-only scope;
- agreements;
- disagreements;
- unresolved questions;
- recommended integration order;
- next AFK task.

For `.codex` state, use `thread_spawn_edges`, thread metadata, worktree paths, and session indexes. Avoid dumping raw private transcripts.
