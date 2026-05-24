---
name: knowledge-graph-updater
description: Update the insights markdown knowledge graph with provenance-backed workflow lessons. Use when a worker failure, review, source audit, or user correction reveals reusable knowledge.
---

# Knowledge Graph Updater

Write durable learning to `insights/`.

## Rules

- Do not write during a read-only explorer lane or review-only pass; return proposed insight updates
  instead.
- Use confidence labels: `confirmed`, `inferred`, `needs validation`.
- Link to source files, plans, artifacts, or worker runs when available.
- Keep claims short and reusable.
- If the lesson implies a workflow change, route the proposed skill edit through
  `skill-golden-eval-loop` before promotion. In write-enabled turns, update the relevant
  `.agents/skills/<skill>/SKILL.md` and its golden task together. In read-only turns, record the
  proposed change in `insights/skill-learning-loop.md`.
- Record the update in planning SQLite when part of an active plan.

## Insight Shape

Each durable insight should make the contract obvious:

- `claim`: the reusable lesson.
- `confidence`: `confirmed`, `inferred`, or `needs validation`.
- `evidence`: source files, docs, plans, logs, artifacts, or worker runs.
- `scope`: where the lesson applies.
- `supersedes`: older insight or skill guidance replaced by this lesson, if any.
- `next action`: skill, doc, task, test, or automation update implied by the lesson.
