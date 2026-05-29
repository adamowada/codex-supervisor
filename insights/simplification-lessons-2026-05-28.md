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

## Stage 2 Policy Core

Assurance policy is now a pure core concern. It should not know how work was launched, which CLI
command called it, which MCP tool exposed it, or which worker backend produced evidence.

The useful boundary is:

1. A task names intent, assurance, and acceptance criteria.
2. An attempt names execution status when that record exists.
3. Evidence names summaries, checks, artifacts, acceptance results, risks, gaps, next actions, and
   review evidence.
4. Policy evaluates those inputs and returns missing requirements or failed acceptance criteria.

This keeps `low`, `medium`, and `high` from becoming new runtime modes. They are evidence policies:
`low` moves exploration forward with risks or gaps and a next action; `medium` covers ordinary
implementation with focused checks, artifacts, and acceptance results; `high` protects durable work
with strict checks, artifacts, acceptance results, risk notes, and review evidence when review is the
risk control.

The policy module can mention attempts without owning attempt lifecycle. Creating attempts, moving
them between statuses, attaching evidence, and writing SQLite rows belongs to the execution-attempt
layer. That division keeps Stage 2 small and gives Stage 3 a clear job.

## Stage 3 Execution Attempts

Run attempts are now a core shape, not a worker backend mode. An attempt records one try, its
executor name, its status, its summary, and its timestamps. The executor is transport information;
the status model stays the same for manual work, shell work, review work, and future Codex workers.

The compact lifecycle is:

1. `planned`
2. `running`
3. one of `succeeded`, `failed`, or `blocked`

The lifecycle belongs in a pure attempt model. SQLite helpers may create rows, start attempts,
complete attempts, attach evidence, and update task status, but they should not decide how CLI, MCP,
plugins, or workers expose those actions.

Evidence attachment is deliberately simple in this stage: evidence bundles link a task, an optional
attempt, assurance, summary, checks, artifacts, and creation time. More detailed acceptance payloads
can earn structure later, but the first useful invariant is relationship integrity: attempts must
point at real tasks, evidence must point at real tasks, evidence attached to an attempt must match
that attempt's task, running tasks must have one non-terminal attempt, and attempts must have
timestamps that match their status.

This stage also sharpens the next interface rule: Stage 4 builds on the compact attempt store and
keeps task, attempt, evidence, and acceptance vocabulary visible at the boundary.

## Stage 4 Small Interface

The first rebuilt interface is intentionally tiny. It has one inspection command and one mutation
command:

- `queue-next`
- `attempt-transition`

`queue-next` answers the operator's next-state question from the compact planning schema. It reports
the selected task, active attempt, latest evidence, acceptance state when it can be evaluated, and
the next transition hint.

`attempt-transition` performs one transition. It can create or start an attempt, complete an
attempt, attach evidence, evaluate acceptance, and update task status. This is enough surface to
operate the current model.

The important lesson is sequencing: CLI can be the first proof surface because it is cheap to test
and easy to inspect. MCP, plugin, automation, GitHub, CI, and spawned-project adapters should wait
until Stage 6 and declare their task intent, attempt, evidence, assurance, and acceptance behavior
one operation at a time.

## Stage 5 Worker Integration

Workers are executors, not a separate control plane. A worker run should use the same attempt,
evidence, and acceptance path as manual or shell work.

The compact worker path is:

1. Read task intent and assurance policy.
2. Build a fresh-context worker prompt from that policy.
3. Start a `RunAttempt` with executor `codex`.
4. Normalize worker output into checks, artifacts, acceptance results, risks, gaps, next actions,
   and review evidence.
5. Attach an evidence bundle.
6. Evaluate acceptance with the same policy core.

The first worker proof should be fake-worker-first. Fake execution is deterministic, fast, and
strong enough to prove prompt shape, evidence normalization, and high-assurance rejection. Live
Codex execution should enter only through a bounded verification plan that records the executable,
timeout, prompt, worker result, evidence bundle, and acceptance evaluation.

High assurance matters most here. A worker result that passes acceptance criteria but omits required
risk evidence must block, because otherwise worker integration becomes a hidden bypass around the
policy core.

## Stage 6 Interface Growth

Adapter growth is now declaration-first. A surface operation earns activation only after it declares:

1. the task intent it serves;
2. the attempt behavior it reads or performs;
3. the evidence behavior it emits or inspects;
4. the assurance levels it can support;
5. the acceptance behavior it exposes;
6. the state flow it uses;
7. the operator value that justifies the surface.

The first activated adapter operation is the read-only MCP `queue_next` tool. It is intentionally
low-risk because it only inspects planning SQLite through the compact queue interface and exposes the
same next-work answer already proven by the CLI. Mutating adapter operations should remain gated
until they have the same declaration and focused tests.

This is the broader state-space lesson from the refactor: surfaces may grow, but each operation must
collapse back onto task intent, attempts, evidence, assurance, and acceptance. If an adapter cannot
state that mapping, it is not ready to exist.

## Live Surface Alignment

The active implementation is strongest when every reachable entrypoint creates, inspects, and
mutates the same compact schema.

The live contract is:

1. `plan-init` creates the six-table compact schema.
2. Planning inspection commands read compact tables directly.
3. `queue-next` reads the next task, active attempt, latest evidence, and acceptance state.
4. `attempt-transition` validates task ownership before changing attempt state.
5. Worker execution closes attempts even when the worker throws or returns an invalid status.
6. Planning integrity checks open work relative to active plans.
7. The attempt store rejects duplicate non-terminal attempts immediately.
8. MCP exposes the same queue inspection answer through one read-only adapter operation.

Integrity checks remain the audit layer, but write paths reject invalid state before it lands. The
database also helps: a partial unique index on non-terminal attempts makes the one-active-try rule
durable.

The design lesson is small but sharp: code that is reachable is part of the product. In a pre-MVP
simplification, every reachable path should either serve the compact control plane directly or wait
outside the active surface.

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
