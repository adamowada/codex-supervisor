---
name: afk-issue-shaper
description: Convert vague plan items, backlog notes, TODOs, or user ideas into one AFK-ready or HITL-ready vertical-slice issue. Use when work needs to enter a Codex queue, GitHub issue, planning SQLite task, or worker prompt.
---

# AFK Issue Shaper

Shape one vertical slice at a time.

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
- expected artifacts;
- review requirement;
- stop conditions.

Use `AFK` when Codex can decide and verify the slice alone. Use `HITL` only when a human product, policy, credential, payment, privacy, or deployment decision is required.

Prefer a small shippable behavior over a horizontal layer such as "build backend" or "add UI."
