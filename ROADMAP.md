# Roadmap

This roadmap replaces the old stage ladder. It is intentionally shorter.

## Stage 0: Cut The Accumulated Surface

Done when:

- source-of-truth docs describe the simplified system;
- historical skills are removed;
- plugin packaging is removed from the active surface;
- historical insights are replaced by current lessons;
- historical tests are removed as acceptance criteria;
- CI checks only the new minimal contract.

## Stage 1: Fresh Planning Core

Done when:

- `plans/planning.sqlite3` uses the fresh schema;
- new seed records name the simplification plan;
- integrity checks validate only the fresh schema;
- future work can be selected from `plans` and `tasks` without old compatibility aliases.

## Stage 2: Core Policy

Build the policy layer that maps task intent to assurance level.

Done when:

- low, medium, and high assurance are defined in code;
- each level has evidence requirements;
- acceptance can be evaluated without branching across task type, backend, runtime mode, and review
  mode.

## Stage 3: Execution Attempts

Rebuild execution as attempts.

Done when:

- manual, shell, and Codex attempts share one record shape;
- attempts produce evidence bundles;
- failure and blocked states do not require separate mode-specific code paths.

## Stage 4: Small Interface

Add one CLI inspection command and one CLI mutation command.

Done when:

- each command maps cleanly to the core model;
- no command exists only for compatibility;
- tests cover the operation contract, not historical behavior.

## Stage 5: Worker Integration

Reconnect fresh-context Codex workers.

Done when:

- Codex execution is one attempt executor;
- worker prompts are generated from task intent and assurance;
- results become evidence bundles;
- high-assurance work cannot complete without required evidence.

## Stage 6: Optional Interfaces

Only after the core is stable, reconsider MCP, Desktop plugin packaging, automation, GitHub, CI/CD,
and spawned-project scaffolds.

Done when:

- each added interface proves it reduces operator effort without adding an independent mode axis.
