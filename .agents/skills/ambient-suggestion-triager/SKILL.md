---
name: ambient-suggestion-triager
description: Review Codex ambient suggestions and convert them into actionable AFK/HITL tasks or dismissals. Use when inspecting .codex/ambient-suggestions, project suggestion queues, proactive recommendations, or deferred follow-up ideas.
---

# Ambient Suggestion Triager

Summarize suggestions without dumping private prompt text.

## Workflow

1. Inventory suggestion buckets by project, status, and recency.
2. Group duplicates by underlying action, not wording.
3. Classify each group: `AFK`, `HITL`, `dismiss`, or `needs context`.
4. For `AFK` and `HITL`, emit an `afk-issue-shaper` compatible task.
5. For `dismiss`, include a short reason.
6. Preserve evidence as paths, counts, timestamps, and ids; avoid full suggestion bodies unless the user asks.

Prioritize suggestions attached to busy projects, failing checks, stale handoffs, and source-of-truth drift.
