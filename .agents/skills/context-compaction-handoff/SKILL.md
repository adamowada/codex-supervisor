---
name: context-compaction-handoff
description: Create compact continuation handoffs before context limits, compaction, long pauses, thread transfer, or worker completion. Use when the user asks to preserve state, continue later, start fresh context, or recover from a bloated session.
---

# Context Compaction Handoff

Write a handoff that a fresh Codex thread can act on immediately.

## Include

- current objective;
- latest user instruction;
- repository and branch;
- changed files;
- commands run and results;
- source-of-truth docs touched;
- active subagents or workers;
- blockers and unresolved decisions;
- next AFK task;
- next HITL question, if any.

## Keep Out

- raw logs;
- full transcript history;
- duplicate reasoning;
- stale plan branches;
- private secrets or credentials.

End with one concrete next command or one concrete next prompt.
