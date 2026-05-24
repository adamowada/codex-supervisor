# Project SOP Knowledge

Confidence: confirmed from private local telemetry and inspected project scaffolds; public evidence
is redacted aggregate method.

Every full supervisor-managed project spawned by `codex-supervisor` should start with:

- short root source-of-truth docs;
- tracked planning SQLite;
- protected source locks when stable source-of-truth files need enforcement;
- `insights/` knowledge graph;
- repo-local skills when repeated workflows or domain knowledge justify them;
- explicit testing gates;
- clear `AFK` and `HITL` task classification.

For small projects, omit empty skill, source, lock, or insight surfaces until they have a real
purpose. The SOP is a scalability pattern, not a requirement to create hollow folders.

## Anti-Patterns

- giant always-on `AGENTS.md`;
- no durable handoff;
- chat-only plans;
- direct edits from unattended workers;
- no test or review gate;
- source clones or generated runs accidentally staged.
