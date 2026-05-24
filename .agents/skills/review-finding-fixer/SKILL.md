---
name: review-finding-fixer
description: Turn code review findings into fixes after the user says to fix all identified issues. Use when remediating review results from fresh-thread reviews, PR reviews, architecture reviews, quality reviews, or bug reviews.
---

# Review Finding Fixer

Fix every valid finding unless HITL rejects it or the behavior is intentionally designed.

If the current user turn is read-only, review-only, audit-only, or no-edits mode, do not edit files.
Return the normalized checklist and the proposed fix plan instead.

## Workflow

1. Normalize findings into a checklist with severity, file, claim, evidence, and proposed fix.
2. Mark each finding: `fix`, `HITL-disagreed`, `intentional`, `duplicate`, or `needs clarification`.
3. Ask the user only for findings that require a product, policy, architecture, or intentional-behavior decision.
4. Fix `fix` items in priority order, keeping changes scoped to the reviewed surface.
5. Add or update tests when a finding is behavioral.
6. Run the narrow verification command for each cluster, then the broader gate.
7. Produce a closure table: finding, action, files changed, verification, residual risk.

Do not silently skip a finding. If an issue is there on purpose, record why so future reviews do not rediscover it as a bug.

For architecture findings, prefer an AFK vertical slice unless the fix needs a design decision. Use `afk-issue-shaper` for larger refactors.
