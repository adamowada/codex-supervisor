---
name: thread-resume-brief
description: Build a concise resume brief from Codex thread/session state, handoff files, git state, or recent work. Use when starting a new thread, recovering after compaction, resuming a project, or transferring context between workers.
---

# Thread Resume Brief

Make the next thread self-sufficient without carrying the old transcript.

Use this skill at the start of a fresh thread or after compaction. Prefer read-only inspection and a
concise status brief. Use `context-compaction-handoff` when the active thread still needs to write a
handoff artifact before transferring work.

## Gather

- project root, branch, and remote;
- latest relevant thread/session ids or handoff paths;
- current source-of-truth docs;
- changed files and git status;
- current-queue planning SQLite summary from `planning-sqlite-operator`, including
  `story-loop-status --json`; use `task-current --after-story-loop-status --json` only as the AFK
  selector after the operator's fresh-thread and environment preflight rules are satisfied;
- any conflict between `HANDOFF.md` and planning SQLite, with the database treated as canonical;
- last verification commands and results;
- queue state: ready AFK, HITL, blocked, completed, or empty;
- pending AFK/HITL tasks;
- active risks or blockers.

## Output

Use short sections: `Goal`, `State`, `Decisions`, `Files`, `Verification`, `Next`. Keep it under one screen unless the user asks for detail.
