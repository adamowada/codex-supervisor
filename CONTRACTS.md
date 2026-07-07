# Contracts

This file defines the durable substrate contracts for `codex-supervisor`.

## Goal Mode Boundary

Goal Mode owns objective, strategy, sequencing, launch packet content, failure diagnosis, retry or
repair decisions, and final completion judgment.

Supervisor owns durable state, worker launch records, evidence, provenance, acceptance, and compact
recovery state. Supervisor must not become a second autonomous orchestration layer.

## Task Intent

A task intent is a clear unit of work chosen by Goal Mode or an operator.

Required fields:

- stable ID;
- plan ID;
- title;
- intent;
- assurance level;
- acceptance criteria;
- status.

Backend choice belongs to a run attempt. Work category belongs in intent text, launch packet
content, and acceptance criteria, not in a supervisor job type.

## Launch Packet

A launch packet is Goal Mode's free-form worker context for one task or attempt.

Recorded fields when a packet is supplied:

- packet path;
- packet hash;
- verifier intent path when present;
- verifier intent hash when present;
- task ID;
- attempt ID when launch begins;
- creation time.

Supervisor copies and hashes launch packets. Supervisor may surface packet identity in queue state
and evidence. Supervisor does not require a strict packet schema until repeated access patterns earn
one.

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

`attempt-run` is the generic worker executor path. It starts one process in a workspace, records the
process as a run attempt, and attaches stdout, stderr, command metadata, exit code, declared
artifacts, git-discovered product paths, checks, risks, gaps, optional verifier results, and
acceptance results as evidence.

Substrate launch metadata must be written at launch time, not only after process exit. The
`command.json` record includes command, cwd, launcher, model/reasoning, timeout, task id, attempt
id, packet hash, verifier hash, git head, and start time.

Process launch, timeout, nonzero exit, missing declared artifacts, and telemetry write failures are
terminal evidence. They must leave the task blocked or accepted through the same durable transition
path; they must not leave a running attempt stranded.

Before the process starts, `attempt-run` writes a task assignment JSON file and exposes it as
`CODEX_SUPERVISOR_TASK_JSON`. The assignment contains the task intent, acceptance criteria,
assurance level, attempt ID, workspace path, and substrate launch packet references when present.
Worker processes read that assignment instead of requiring a supervisor job type.

The packaged Codex worker launcher is the default Codex worker path. It must launch workers with
`model_reasoning_effort="xhigh"` unless the user explicitly requests different worker reasoning
behavior.

For Goal Mode, full AFK, or autonomous-worker product work, product file mutation happens inside
`attempt-run`. The supervisor may write supervisor-owned files under `.codex-supervisor/`, launch
workers, inspect outputs, run verifiers, and record evidence. Product cleanup, repair, audit,
warning, polish, or final-proof work is represented as new task intent and assigned through another
worker attempt.

Declared task artifacts are verified after the process exits. A caller-supplied passing acceptance
result is forced to failing evidence when required artifacts are missing.

Product artifact provenance includes both caller-declared artifacts and changed product paths
discovered from the target git workspace after `attempt-run` finishes. Product paths exclude
`.gitignore` and `.codex-supervisor/**`. ACP uses the same provenance rule to require every changed
product path to be backed by succeeded `attempt-run` evidence.

When content or behavior needs machine verification, `attempt-run` may run one verifier command
after the worker exits and before the terminal transition is recorded. The verifier receives the
same assignment environment and workspace as the worker. Its command metadata, stdout, stderr, and
exit code become evidence. A nonzero verifier exit code fails the attempt and forces supplied
passing acceptance results to failing evidence.

Verifier commands should prove behavior or structural contract. Literal string checks are for tasks
where the literal text is itself required.

## Task Lineage

Lineage links task intent without adding workflow-specific job types.

Allowed relation names:

- `retry_of`
- `repair_of`
- `review_of`
- `shipping_proof_of`

Lineage is stored on task intent as generic relation data. A repair is not a special supervisor
mode; it is a task linked to the task that needs repair.

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

Evidence is structured before storage. The active schema keeps the compact `checks_json` and
`artifacts_json` fields, and the evidence codec owns how checks, acceptance results, risks, gaps,
next actions, review evidence, command references, packet references, and digest references are
encoded into those fields. Terminal acceptance is stored as a separate decision row linked to the
evidence bundle instead of being inferred from check strings.

Evidence digests summarize raw logs and artifacts for Goal Mode recovery. Digests should include
verifier result, changed files, declared artifacts, warnings, log sizes, important tails,
risk/gap/next-action notes, and acceptance rationale.

## Acceptance Decision

Acceptance is the policy decision that a task can advance.

`attempt-transition` evaluates acceptance when terminal attempt evidence is written. Every terminal
attempt with evidence writes one `acceptance_decisions` row linked to the task, attempt, and evidence
bundle. The row records the policy actor, accepted/rejected result, rationale, and structured
evaluation JSON. Task status is the current-state projection of that durable decision.

Inspection paths read stored state. They do not replay acceptance from evidence and they do not
reinterpret old decisions through newer policy code.

Goal Mode may decide the larger goal is complete only after final proof is recorded or after an
explicit unsupervised exception is declared.

## Recovery State

`queue-next` and `codex_supervisor.queue_next` are read-only recovery paths. They must never mutate
state.

The substrate target is compact recovery state sufficient for Goal Mode to resume:

- active plan and task;
- active attempt and liveness age;
- latest evidence;
- latest acceptance decision;
- launch packet and verifier hashes;
- lineage;
- git summary;
- warning flags;
- next suggested transition.

## Assurance Levels

### Low

Use for diagnosis, sketches, and candidate work.

Minimum evidence:

- summary;
- known risks or gaps;
- next recommended action.

Low assurance advances early work.

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
