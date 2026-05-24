---
name: context-compaction-handoff
description: Create compact continuation handoffs before context limits, compaction, long pauses, thread transfer, or worker completion. Use when the user asks to preserve state, continue later, start fresh context, or recover from a bloated session.
---

# Context Compaction Handoff

Write a handoff that a fresh Codex thread can act on immediately.

Use this skill when the current thread is about to lose context or when a worker needs to finish
with a durable artifact. Use `thread-resume-brief` when a new thread is already starting and needs a
read-only status summary before work resumes.

If the current turn is read-only, review-only, audit-only, or no-edits mode, do not write a handoff
file or mutate planning state. Return the handoff text in chat plus the proposed target path and
recording commands for later approval.

## Include

- current objective;
- latest user instruction;
- repository and branch;
- changed files;
- commands run and results;
- source-of-truth docs touched;
- planning SQLite state from `story-loop-status --json` and, when present, `task-current --json`;
- active subagents or workers;
- blockers and unresolved decisions;
- next ready AFK task, if any;
- next HITL question, if any.

## Keep Out

- raw logs;
- full transcript history;
- duplicate reasoning;
- stale plan branches;
- private secrets or credentials.

End with one concrete next command or one concrete next prompt. If `story-loop-status` is `hitl`,
name the HITL task as the current human checkpoint instead of saying there is no task.
