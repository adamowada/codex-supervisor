# Simplification Lessons From The Control-Plane Reset

Date: 2026-05-28

## Context

This insight records the architectural lessons from the conversation that led to the ruthless
simplification refactor. The discussion started with a concern that the supervisor/worker contract
and control plane kept growing. It then examined what would happen if restrictions were loosened,
whether strictness should be modeled as two or three levels, how that would affect tests, how the
current codebase and testing architecture already contain many mode-like axes, and how the CLI, MCP,
plugin, skill, planning, review, and worker surfaces had expanded.

The final user direction was explicit: the project is pre-release and pre-MVP; nothing depends on
legacy behavior; compatibility worries must not preserve the state-space problem. The user asked for
source-of-truth documents, planning database, skills, CI, and insights to be deleted or completely
rewritten, with a simplified fresh planning database.

## Core Lesson

The main problem was not any single strict rule. The main problem was that every rule became a new
axis.

The system had accumulated many independent dimensions:

- task type;
- worker backend;
- runtime execution mode;
- native Goal availability;
- evidence mode;
- review mode;
- worker profile;
- full-AFK flags;
- publication flags;
- controller mutation flags;
- plugin readiness;
- MCP tool inventory;
- CLI compatibility aliases.

Each axis may have been reasonable when introduced. Together they created a state space too large to
engineer comfortably. Testing then became whack-a-mole because every bug fix added another guard,
and every guard became another behavior combination.

The lesson is severe: a control plane should not grow by adding axes. It should grow by strengthening
one transition model.

## The Replacement Model

The replacement model is:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

This model is intentionally plain.

A task says what is wanted. An attempt says what tried to do it. Evidence says what happened.
Acceptance says whether that is enough.

Most old concepts can fit inside this model without becoming top-level axes:

- Codex execution is an attempt executor.
- Manual work is an attempt executor.
- Review is either an attempt or evidence required by policy.
- Goal Contracts are task-intent rendering, not queue authority.
- JSONL is evidence, not a database mode.
- MCP and plugin calls are interfaces over the same operations, not their own control planes.
- Full-auto is high-assurance policy, not a separate workflow universe.

If a concept cannot fit into this model, it should be treated as unproven.

## Assurance Levels

The conversation considered strictness modes, including low/high and low/medium/high. The important
resolution was to avoid calling them modes. Mode language invites parallel state machines. Assurance
language keeps the concept attached to acceptance policy.

`low` is for exploration. It can produce useful insight but should not close durable work.

`medium` is for ordinary supervised implementation. It requires structured evidence and focused
checks.

`high` is for work that crosses trust boundaries: source-of-truth edits, controller changes,
release-like work, destructive changes, or full-auto execution. It requires strict evidence and
review when review is the risk control.

The hard rule is that assurance levels must not fork the schema, task taxonomy, backend taxonomy,
runtime taxonomy, review taxonomy, or interface taxonomy. They only change what evidence is required
before acceptance.

## Why Medium Is Worth Keeping

Medium is worth keeping only if it remains the default ordinary-work policy. It is not worth keeping
as a negotiated middle ground full of exceptions.

There is a natural medium:

- not exploratory;
- not release-critical;
- not source-of-truth/controller/destructive/full-auto;
- still real engineering work that needs checks and structured evidence.

Medium becomes harmful if it starts accumulating special cases. The moment medium needs its own
backend behavior, CLI options, review routes, or database branches, it should be collapsed back into
low or high.

## Source-Of-Truth Lesson

Source-of-truth documents can become traps. They start as clarity, then become treaties that protect
old complexity.

In this repo, the protected documents had become a late-stage factory description. They encoded
Stage 6 and later assumptions as doctrine: live Codex Exec, plugin canaries, release gates, review
promotion, spawned-project scaffolds, local Codex state reconciliation, and many operational
hardening lessons.

Those were not wrong in isolation. They were wrong as the active contract for a pre-MVP project that
needed simplification.

The lesson: source-of-truth documents should protect current intent, not historical ambition. If the
intent changes, rewrite the docs and re-hash them. Do not build compatibility layers around stale
doctrine.

## Planning Database Lesson

The old planning database was internally consistent and still a problem.

It had dozens of plans, many tasks, worker runs, result records, hundreds of progress events, and
large event vocabularies. Integrity passed, but passing integrity only proved that the old complexity
was self-consistent.

That is an important distinction. Consistency is not simplicity. Auditability is not necessarily
clarity. A database can faithfully preserve a state-space problem.

The fresh database intentionally keeps only:

- metadata;
- plans;
- tasks;
- attempts;
- evidence bundles;
- decisions.

The branch is the archive. The product database is not.

## Skills Lesson

Skills became a second control plane.

The repo had a large skill mesh: routers, operators, reviewers, fixers, issue shapers, bootstrappers,
handoff builders, CI operators, publication helpers, and workflow-specific skills. Many were useful,
but together they made the operator think through a routing graph before doing the work.

The lesson: skills should compress operator behavior, not encode product architecture. A skill is
healthy when it is a short reminder. It is unhealthy when it becomes a hidden workflow engine.

The reset keeps one repo-local skill. More skills can return only when they remove complexity.

## CLI, MCP, And Plugin Surface Lesson

The old surface was too big for pre-MVP:

- 64 CLI commands;
- 34 MCP tools;
- many mutable operations;
- packaged Desktop plugin wiring;
- plugin install expectations;
- runtime preflight canaries.

That surface made testing feel combinatorial because it was combinatorial. Each public operation
needed state, permission, evidence, failure, and interface semantics.

The lesson: public surface should lag core clarity. Rebuild one operation at a time after the
transition model is stable.

## CI And Testing Lesson

The old test suite became a preservation engine.

Tests are valuable when they protect intended behavior. They are harmful when they keep deleted
behavior alive by accident.

For the simplification branch, current tests receive zero authority. The right move is not to port
them. The right move is to write small tests for the fresh model and add more only as behavior is
rebuilt.

CI should be correspondingly small. It should guard the active contract, not the historical factory.

## Safety Lesson

Loosening restrictions does not mean removing safety. It means moving safety to fewer places.

The durable safety model is:

- isolate attempts;
- record evidence;
- require assurance-appropriate acceptance;
- make high-risk work explicit.

That is simpler than scattering safety across task types, backend names, runtime modes, review
routes, plugin canaries, and special-case completion gates.

## Future Design Tests

Before adding any feature back, ask:

1. Does it fit `TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision`?
2. Does it reduce state space or increase it?
3. Is it policy, execution, evidence, or interface?
4. Can assurance level handle the risk without a new mode?
5. Can one focused test prove the behavior?
6. Can the feature be deleted later without a compatibility layer?

If the answer is no, the feature is too early.

## Final Takeaway

The project did not need a more elaborate supervisor contract. It needed the courage to delete the
old one.

The ruthless path is not reckless. It is the safer path for a pre-MVP control plane because it keeps
the system small enough to reason about.
