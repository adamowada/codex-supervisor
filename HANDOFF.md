# Handoff

## Current State

This repository has been bootstrapped as a Python-first `codex-supervisor` project.

Present:

- git repo initialized;
- shallow source clones under ignored `sources/`;
- source-of-truth docs;
- Python package skeleton;
- planning SQLite contract;
- source lock guard;
- initial `insights/` knowledge graph;
- repo-specific skills.

The next Codex session should begin implementation from `ROADMAP.md`, starting with Stage 1 unless
the user reprioritizes.

## Next Recommended Session Prompt

```text
Read README.md, AGENTS.md, PLANS.md, ARCHITECTURE.md, CONTRACTS.md, ROADMAP.md, SOP.md, TESTING.md,
DECISIONS.md, and insights/README.md.

Then inspect the Python package and tests. Begin Stage 1 from ROADMAP.md: complete the planning
SQLite core. Keep all changes scoped, run the default checks, update plans/planning.sqlite3 through
typed helpers, and do not edit locked source-of-truth docs unless the plan explicitly requires it.
```

## Important Constraints

- Do not stage or commit unless the user asks.
- Do not vendor source clones.
- Keep the project cross-platform.
- Treat dangerous/full-auto operation as the target mode.
- Preserve the split between durable source of truth, operational SQLite state, and generated run
  artifacts.
