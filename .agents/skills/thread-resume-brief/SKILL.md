---
name: thread-resume-brief
description: Build a concise resume brief from Codex thread/session state, handoff files, git state, or recent work. Use when starting a new thread, recovering after compaction, resuming a project, or transferring context between workers.
---

# Thread Resume Brief

Make the next thread self-sufficient without carrying the old transcript.

## Gather

- project root, branch, and remote;
- latest relevant thread/session ids or handoff paths;
- current source-of-truth docs;
- changed files and git status;
- last verification commands and results;
- pending AFK/HITL tasks;
- active risks or blockers.

## Output

Use short sections: `Goal`, `State`, `Decisions`, `Files`, `Verification`, `Next`. Keep it under one screen unless the user asks for detail.
