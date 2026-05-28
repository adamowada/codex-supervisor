# Compact Control-Plane Lessons

Date: 2026-05-28

## Conversation Result

The conversation established the product shape for `codex-supervisor`: a compact control plane that
coordinates Codex work through one transition model, one planning store, assurance-based policy, and
a narrow active surface.

The durable model is:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

This model gives every future feature a clear home. Task intent says what is wanted. A run attempt
records who or what tried to satisfy it. An evidence bundle records proof. An acceptance decision
advances, blocks, or keeps work ready.

## Control-Plane Shape

A supervisor becomes understandable when every operation strengthens the same transition model.

The preferred growth pattern is:

1. Define the task intent.
2. Choose the assurance level.
3. Run one attempt.
4. Capture evidence.
5. Apply acceptance policy.

That sequence should remain visible in code, docs, tests, and operator workflows.

## Assurance Levels

The conversation settled on three assurance levels:

- `low`
- `medium`
- `high`

Assurance is policy. It sets evidence and acceptance requirements while the core model remains
stable.

`low` is for exploration, diagnosis, sketches, and candidates. The useful output is a summary,
risks or gaps, and a next action.

`medium` is for ordinary supervised engineering work. The useful output is structured evidence,
focused checks, changed artifacts or paths, and acceptance criteria results.

`high` is for full-auto, source-of-truth, controller, release, destructive, and trust-boundary work.
The useful output is strict evidence, explicit artifacts, acceptance criteria results, risk notes,
and review evidence when review is the risk control.

Medium has a natural role as the default for ordinary implementation. It stays healthy when it stays
boring: focused checks, structured evidence, and ordinary acceptance.

## Source-Of-Truth Documents

Source-of-truth documents work best in present tense. They should describe the product that exists
and the product being built.

Good source docs:

- name the active model;
- name the active database schema;
- name the active verification gate;
- name the next build stage;
- use direct language.

This keeps the docs useful for fresh contexts and future workers.

## Planning Database

The planning database should answer operational questions directly:

- What plan is active?
- What task intent is next?
- What attempts have run?
- What evidence exists?
- What decisions shape the work?

The active schema contains:

- `meta`
- `plans`
- `tasks`
- `attempts`
- `evidence_bundles`
- `decisions`

This shape keeps the queue and evidence model inspectable. Detail can live in JSON fields while the
access pattern is still forming. Repeated queries can earn dedicated tables later.

## Skills

Skills should compress operator behavior. A healthy skill is short enough to read quickly and clear
enough to guide action.

The active repo-local skill names the model, assurance levels, planning database, handoff, source
locks, and verification command. That is enough guidance for the current product shape.

## Interfaces

Interfaces should follow the core.

CLI, MCP, plugin, automation, GitHub, and worker surfaces are useful when each operation can state:

- task intent it creates or inspects;
- attempt it runs;
- evidence it emits;
- assurance level it satisfies;
- acceptance behavior it supports.

This rule keeps public surface area aligned with the state model.

## Testing

Tests should protect the active contract.

The first tests cover:

- planning schema;
- seed records;
- skill inventory;
- source locks;
- the compact work model.

Future tests should grow with rebuilt behavior:

- assurance policy mapping;
- attempt recording;
- evidence bundle validation;
- acceptance evaluation;
- inspection and mutation commands.

## Local Hygiene

Ignored local artifacts should stay disposable. Development environments, caches, run outputs,
source-study clones, and temporary worktrees are local conveniences. The tracked product contract
belongs in source docs, planning SQLite, scripts, tests, and insights.

Keeping the workspace clean keeps fresh-context work honest: if a future worker needs something, it
should be either tracked, recreated by a documented command, or recorded in the planning database.

## Design Questions For Future Work

Ask these before adding a feature:

1. Which task intent does this serve?
2. Which attempt records the work?
3. Which evidence bundle proves the result?
4. Which assurance level applies?
5. Which acceptance decision advances the task?
6. Which focused test protects the behavior?

Features with clear answers can grow the supervisor. Features with vague answers need more design.

## Takeaway

The supervisor should feel small from the inside. The work can be ambitious, but the control plane
should stay centered on task intent, attempts, evidence, acceptance, and assurance.
