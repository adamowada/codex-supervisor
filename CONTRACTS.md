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
Work category belongs in intent text and acceptance criteria, not in a supervisor job type.

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

`attempt-run` is the generic AFK executor path. It starts one process in a workspace, records the
process as a run attempt, and attaches stdout, stderr, command metadata, exit code, declared
artifacts, checks, risks, gaps, optional verifier results, and acceptance results as evidence.

Process launch, timeout, nonzero exit, missing declared artifacts, and telemetry write failures are
terminal evidence. They must leave the task blocked or accepted through the same durable transition
path; they must not leave a running attempt stranded.

Before the process starts, `attempt-run` writes a task assignment JSON file and exposes it as
`CODEX_SUPERVISOR_TASK_JSON`. The assignment contains the task intent, acceptance criteria,
assurance level, attempt ID, and workspace path. Worker processes read that assignment instead of
requiring a supervisor job type.

For full AFK or autonomous-worker product work, product file mutation happens inside `attempt-run`.
The supervisor may write supervisor-owned files under `.codex-supervisor/`, launch workers, inspect
outputs, run verifiers, and record evidence. Product cleanup, repair, audit, warning, or polish work
is represented as new task intent and assigned through another worker attempt.

Declared task artifacts are verified after the process exits. A caller-supplied passing acceptance
result is forced to failing evidence when required artifacts are missing.

When content or behavior needs machine verification, `attempt-run` may run one verifier command
after the worker exits and before the terminal transition is recorded. The verifier receives the
same assignment environment and workspace as the worker. Its command metadata, stdout, stderr, and
exit code become evidence. A nonzero verifier exit code fails the attempt and forces supplied
passing acceptance results to failing evidence.

Verifier commands should prove behavior or structural contract. Literal string checks are for tasks
where the literal text is itself required.

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
