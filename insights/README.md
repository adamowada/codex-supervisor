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
- `goal-mode-and-ralph-loop.md`: synthesis of Codex Goals and Ralph-informed one-story loops.
- `bootstrap-landmine-audit.md`: confirmed bootstrap drift and quality findings from six-lane
  explorer audits.
- `project-sop.md`: project bootstrap SOP distilled for spawned projects.
- `release-readiness-evidence.md`: release-readiness policy for evidence-only ACP commits that
  validate a code or doctrine commit.
- `skill-learning-loop.md`: how skills should be updated and tested over time.
- `v1-hardening-clarifications.md`: resolved v1 hardening policy for live Codex work, ACP cadence,
  MCP mutation defaults, adapters, project scaffolding, and skill promotion.
- `v1-hardening-review.md`: six-lane review synthesis and normalized v1 hardening finding clusters.
- `graph.md`: lightweight markdown knowledge graph.

Historical audit and worker-result files are evidence, not mandatory orientation. Fresh threads
should read them only when the live task references the audit or when investigating related drift.
Insights are durable memory, not operational queue state. For current work, inspect
`story-loop-status --json`, `plan-summary --current-queue`, and
`task-list --current-queue-plans-only` before treating an insight or historical audit as live.

## Reusable Insight Shape

Use this compact shape when adding machine-scannable lessons:

| Field | Meaning |
| --- | --- |
| `claim` | Durable lesson in one sentence. |
| `confidence` | `confirmed`, `inferred`, or `needs validation`. |
| `evidence` | Source files, docs, plans, logs, artifacts, or worker runs. |
| `scope` | Where the lesson applies. |
| `supersedes` | Older insight or skill guidance replaced by this lesson, if any. |
| `next action` | Skill, doc, task, test, or automation update implied by the lesson. |

## Update Rule

When a worker, reviewer, or human correction reveals reusable knowledge, update the most relevant
insight file and link the update from planning SQLite.

## Public Posture

This repository can be public, so insights should stay privacy-safe: summarize aggregate behavior,
repo-level workflow lessons, source provenance, and project names only when useful. Do not paste
private transcript content, secrets, local absolute paths, credentials, customer data, or source code
from other projects.
