---
name: zoom-out
description: Produce a higher-level map of an unfamiliar code area. Use when implementation details are hard to place in the broader module, caller, contract, or domain context.
---

# Zoom Out

Map the broader context before editing.

If the current user turn is read-only, readonly, review-only, audit-only, no-edits, or no-mutation
mode, inspect and report only. Do not edit files, update planning SQLite, write reports, or mutate
trackers.

## Workflow

1. Identify the narrow area the user or current task is focused on.
2. Read the surrounding modules, callers, tests, docs, and domain glossary terms.
3. Explain how the area fits into the larger system, where data/control enters and exits, and which
   source-of-truth contracts govern it.
4. Call out uncertainty, missing tests, or likely seams for deeper follow-up.

## Result Contract

Return a concise map of relevant modules and callers, the domain vocabulary to use, the governing
contracts, and the next best skill or investigation path.
