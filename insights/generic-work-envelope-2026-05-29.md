# Generic Work Envelope

Date: 2026-05-29

## Lesson

An agentic engineering factory does not need deterministic job types for each engineering activity.
It needs a deterministic ledger around work that Codex is free to interpret and execute.

The stable envelope is:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Codex should own the semantics of the task: whether it is starting a project, fixing a bug,
reviewing a design, writing tests, splitting a module, or creating follow-up work. The supervisor
should own the accounting: every task has durable intent, every execution is a recorded attempt,
every completion claim has evidence, and every advancement has an acceptance decision.

## Complexity Pattern

The tempting failure mode is to add one supervisor operation per work category:

```text
start-project
fix-bug
write-tests
review-pr
update-docs
prepare-release
```

That grows the surface and creates hidden state-space multiplication. Each job type eventually wants
its own flags, acceptance rules, worker prompts, retries, failure semantics, and tests. The
supervisor becomes a taxonomy of engineering work instead of a compact control plane.

The smaller pattern is:

```text
task-create
attempt-run
attempt-transition
queue-next
```

`task-create` records what work should exist. `attempt-run` executes one worker process in a
workspace. `attempt-transition` records manual or already-run transitions. `queue-next` inspects
durable state. These operations do not know whether the task is a project start or a bug fix. That
meaning stays in the task intent and acceptance criteria.

## Boundary

The supervisor can safely let Codex manage Codex when the following remains deterministic:

- task intent is durable;
- attempts have explicit executors, status, timestamps, and summaries;
- AFK execution runs in an explicit workspace;
- stdout, stderr, command metadata, exit code, artifacts, checks, risks, gaps, and acceptance
  results are recorded as evidence;
- acceptance is evaluated from task, attempt, evidence, and assurance policy;
- failed workers terminalize attempts instead of leaving durable state running.

This is the useful split:

```text
Codex decides:
- what work exists;
- how to decompose it;
- what command or tool to run;
- which artifacts matter;
- what follow-up work remains.

Supervisor enforces:
- durable task intent;
- one recorded attempt per execution;
- evidence before acceptance;
- assurance policy;
- inspectable state transitions;
- resumability after failure.
```

## Practical Consequence

The first AFK implementation should be generic process execution, not a project-specific launcher.
A tiny project smoke test is valuable, but the operation being tested is not "start project." The
operation being tested is "run this process as an attempt and record enough evidence to accept or
block the task."

That gives the future system room to become an engineering factory without turning the supervisor
into a switch statement. The factory grows by letting Codex create better task intents and worker
commands, while the supervisor keeps the same evidence ledger.
