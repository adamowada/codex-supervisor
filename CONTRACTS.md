# Contracts

This file defines the durable contracts for `codex-supervisor`.

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

Backend choice belongs to a run attempt.

## Run Attempt

A run attempt is one try at satisfying a task.

Required fields:

- stable ID;
- task ID;
- executor;
- status;
- summary;
- start and finish timestamps when applicable.

Executors may include `codex`, `manual`, `shell`, `review`, or future adapters. Executor names
describe transport.

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

Evidence is inspectable. Raw artifacts can live outside SQLite, while SQLite records what exists and
why it matters.

## Acceptance Decision

Acceptance is the policy decision that a task can advance.

`attempt-transition` evaluates acceptance when terminal attempt evidence is written. Task status plus
evidence bundles represent acceptance in the active schema. Inspection paths do not replay
acceptance from stored evidence. A dedicated acceptance table can be added when repeated acceptance
queries require it.

## Assurance Levels

### Low

Use for exploration, diagnosis, sketches, and candidate work.

Minimum evidence:

- summary;
- known risks or gaps;
- next recommended action.

Low assurance advances exploratory work.

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

High assurance protects durable and high-risk changes.
