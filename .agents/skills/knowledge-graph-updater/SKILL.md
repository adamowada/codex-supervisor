---
name: knowledge-graph-updater
description: Update the insights markdown knowledge graph with provenance-backed workflow lessons. Use when a worker failure, review, source audit, or user correction reveals reusable knowledge.
---

# Knowledge Graph Updater

Write durable learning to `insights/`.

## Rules

- Use confidence labels: `confirmed`, `inferred`, `needs validation`.
- Link to source files, plans, artifacts, or worker runs when available.
- Keep claims short and reusable.
- If the lesson implies a workflow change, add or update a skill proposal.
- Record the update in planning SQLite when part of an active plan.
