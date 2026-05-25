---
name: afk-issue-shaper
description: Convert vague plan items, backlog notes, TODOs, or user ideas into one AFK-ready or HITL-ready vertical-slice issue. Use when work needs to enter a Codex queue, GitHub issue, planning SQLite task, or worker prompt.
---

# AFK Issue Shaper

Shape one vertical slice at a time.

If the current user turn is read-only, review-only, audit-only, no-edits, or no-mutation mode, shape
the issue contract only. Do not write planning SQLite rows, create GitHub issues, update trackers,
or write prompt artifacts; return the proposed durable write commands for later approval.

## Output Contract

Include:

- title;
- mode: `AFK` or `HITL`;
- goal;
- user-visible outcome;
- allowed paths;
- out-of-scope;
- blocked-by;
- acceptance criteria;
- verification commands;
- evidence-based stop condition;
- blocked condition;
- Goal Contract draft or source fields;
- expected artifacts;
- review requirement;
- classification reason.

Use `AFK` when Codex can decide and verify the slice alone. Use `HITL` only when a human product, policy, credential, payment, privacy, or deployment decision is required.

Prefer a small shippable behavior over a horizontal layer such as "build backend" or "add UI."

Before launch, the issue should map directly to `supervisor_tasks` columns and be convertible into a
Goal Contract without new human input.

Use only planning-safe verification commands in the task contract. New `scripts/*.py` verifiers are
not automatically accepted by planning SQLite command-safety checks; either include explicit
command-safety promotion in the slice or use focused pytest/full verify as canonical commands and
run the new script as extra evidence during review or handoff.
