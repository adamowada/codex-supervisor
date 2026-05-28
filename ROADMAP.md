# Roadmap

## Stage 1: Foundation Contract

Done when:

- source-of-truth docs describe the compact control plane;
- planning SQLite uses the schema from `PLANS.md`;
- repo-local skill guidance matches the active model;
- CI runs the focused verification gate;
- the current insight set records design lessons.

## Stage 2: Policy Core

Build the policy layer that maps task intent to assurance level.

Done when:

- low, medium, and high assurance are defined in code;
- each level has evidence requirements;
- acceptance uses one core path across task, attempt, and evidence records.

## Stage 3: Execution Attempts

Represent execution as attempts.

Done when:

- manual, shell, and Codex attempts share one record shape;
- attempts produce evidence bundles;
- succeeded, failed, and blocked attempts follow one status model.

## Stage 4: Small Interface

Add one inspection command and one mutation command.

Done when:

- each command maps cleanly to the core model;
- tests cover the operation contract;
- the command surface stays small enough to audit by inspection.

## Stage 5: Worker Integration

Connect fresh-context Codex workers as attempt executors.

Done when:

- worker prompts are generated from task intent and assurance;
- worker results become evidence bundles;
- high-assurance work requires the evidence named in policy.

## Stage 6: Interface Growth

Add MCP, Desktop plugin packaging, automation, GitHub, CI/CD, and spawned-project scaffolds as
adapters when the core model is ready for them.

Done when:

- each interface operation maps to task intent, attempt, evidence, and acceptance;
- focused tests cover the adapter contract;
- the operation reduces operator effort.
