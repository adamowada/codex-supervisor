---
name: factory-task-decomposer
description: Decompose a plan into AFK and HITL vertical-slice tasks for the codex-supervisor queue. Use when turning planning docs, PRDs, issues, or architecture plans into implementation tasks.
---

# Factory Task Decomposer

Break work into thin, independently verifiable vertical slices.

## Task Shape

Each task needs:

- title;
- goal;
- `AFK` or `HITL`;
- blocked-by list;
- allowed scope;
- out-of-scope list;
- acceptance criteria;
- verification commands;
- evidence-based stop condition;
- Goal Contract readiness;
- expected worker backend;
- review requirement.

Prefer many small AFK tasks over one broad task. Mark tasks HITL only when a real human decision is
required.

Each AFK task should be small enough for one story-loop iteration. If a task cannot be expressed as
one Goal Contract with one stop condition, split it further.
