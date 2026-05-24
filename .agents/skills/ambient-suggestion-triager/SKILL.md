---
name: ambient-suggestion-triager
description: Review Codex ambient suggestions or local Codex inbox/automation telemetry and convert them into actionable AFK/HITL tasks or dismissals. Use when inspecting discovered suggestion queues, inbox items, automation follow-ups, proactive recommendations, or deferred follow-up ideas.
---

# Ambient Suggestion Triager

Summarize suggestions without dumping private prompt text.

## Workflow

1. If the current turn is read-only, review-only, audit-only, no-edits, or no-mutation mode, do not
   update queues, dismiss suggestions, write telemetry, or mutate planning SQLite. Return a triage
   report and the exact `afk-issue-shaper`/`planning-sqlite-operator` follow-up commands instead.
2. Inventory suggestion buckets by project, status, and recency from normalized
   `codex-state-readonly-audit` output. Treat `.codex/ambient-suggestions` as optional/discovered,
   not a guaranteed Codex path; documented local telemetry sources include inbox and automation
   tables.
3. Group duplicates by underlying action, not wording.
4. Classify each group: `AFK`, `HITL`, `dismiss`, or `needs context`.
5. For `AFK` and `HITL`, emit an `afk-issue-shaper` compatible task and route durable queue writes
   through `planning-sqlite-operator`.
6. For `dismiss`, include a short reason.
7. Preserve evidence as paths, counts, timestamps, and ids; avoid full suggestion bodies unless the user asks.

Prioritize suggestions attached to busy projects, failing checks, stale handoffs, and source-of-truth drift.
