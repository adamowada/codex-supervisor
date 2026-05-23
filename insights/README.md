# Codex Supervisor Insight Wiki

This directory is the durable learning memory for `codex-supervisor`.

Use it for synthesized, provenance-backed knowledge about:

- agentic engineering workflows;
- worker failure modes;
- skill improvements;
- project bootstrap patterns;
- source integrations;
- prompt and task design;
- context management.

## Confidence Labels

- `confirmed`: directly supported by source code, docs, tests, or observed runs.
- `inferred`: reasonable synthesis from available evidence, but not yet directly verified.
- `needs validation`: useful hypothesis that should be tested before becoming SOP.

## Core Files

- `source-index.md`: cloned source corpus and what each repo is useful for.
- `workflow-patterns.md`: recurring workflow patterns extracted from sources and Adam's projects.
- `codex-usage-skill-synthesis.md`: aggregate `.codex` usage evidence behind repo-local skills.
- `project-sop.md`: project bootstrap SOP distilled for spawned projects.
- `skill-learning-loop.md`: how skills should be updated and tested over time.
- `open-questions.md`: unresolved design questions for future planning sessions.
- `graph.md`: lightweight markdown knowledge graph.

## Update Rule

When a worker, reviewer, or human correction reveals reusable knowledge, update the most relevant
insight file and link the update from planning SQLite.
