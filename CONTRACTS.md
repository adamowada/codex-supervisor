# Contracts

This file defines the current durable contracts for the simplified supervisor.

## Task Intent

A task intent is a clear unit of work.

Required fields:

- stable ID;
- plan ID;
- title;
- intent;
- assurance level;
- acceptance criteria;
- status.

Task intent does not include a permanent worker backend. Backend choice belongs to an attempt.

## Run Attempt

A run attempt is one try at satisfying a task.

Required fields:

- stable ID;
- task ID;
- executor;
- status;
- summary;
- start and finish timestamps when applicable.

Executors may include `codex`, `manual`, `shell`, `review`, or future adapters. Executor names are
not modes. They describe how the attempt ran.

## Evidence Bundle

An evidence bundle is the structured proof attached to a task or attempt.

Required fields:

- stable ID;
- task ID;
- optional attempt ID;
- assurance level;
- summary;
- checks JSON;
- artifacts JSON;
- timestamp.

Evidence must be inspectable. Raw artifacts can live outside SQLite, but the bundle must say what
exists and why it matters.

## Acceptance Decision

Acceptance is the policy decision that a task can move forward.

For now, acceptance is represented by task status plus evidence bundle records. A dedicated
acceptance table may be added only if it removes ambiguity without reintroducing mode sprawl.

## Assurance Levels

### Low

Use for exploration, diagnosis, sketches, and candidate work.

Minimum evidence:

- summary;
- known risks or gaps;
- next recommended action.

Low assurance cannot close high-risk durable work.

### Medium

Use for ordinary supervised engineering work.

Minimum evidence:

- summary;
- focused checks;
- changed artifacts or paths;
- acceptance criteria results.

### High

Use for full-auto, source-of-truth, controller, release, destructive, or trust-boundary work.

Minimum evidence:

- summary;
- strict checks;
- explicit artifacts;
- acceptance criteria results;
- risk notes;
- review evidence when review is the risk control.

## Deleted Contracts

The following old contracts are not active:

- AFK/HITL as durable task types;
- codex_exec as the primary product identity;
- native Goal mode as an architectural dependency;
- strict/degraded JSONL as a schema branch;
- review mode taxonomy;
- plugin full-AFK canary contract;
- release-readiness evidence bundle;
- spawned-project scaffold tiers.

They may return only as smaller expressions of task, attempt, evidence, and acceptance.
