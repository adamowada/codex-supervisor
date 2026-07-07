# Follow-Up Plan Models

Date: 2026-05-31

## Context

Live factory smoke tests showed a real design question: after an autonomous worker completes a task
and the supervisor later discovers more product work, where should that follow-up live?

The current behavior is Model A: create new task intent, usually in a new plan, and assign the work
through another `attempt-run`. Keep this behavior for now.

## Model A: Follow-Up Work Becomes A New Plan

The current model keeps completed plans terminal. If supervisor inspection discovers cleanup, repair,
audit, warning, polish, or follow-up implementation work, the supervisor creates new task intent and
assigns it through a new worker attempt.

Why keep it now:

- It is the simplest behavior to implement and test.
- `done` stays terminal, which keeps state transitions boring.
- The existing active queue remains easy to reason about.
- It reinforces the role boundary: the supervisor manages work, workers mutate product files.
- Codex can inspect fragmented factory state and reconstruct the user-level story from plans,
  tasks, attempts, evidence, artifacts, and summaries.

Costs:

- A single user goal can spread across multiple plans.
- Human readability can suffer because follow-up causality is implicit in summaries and evidence.
- Reporting may need Codex analysis instead of direct human scanning.

This is acceptable right now because the project is still optimizing for a small state space and a
testable factory loop.

## Model B: Reopen Or Reactivate The Same Plan

This model would let the supervisor move a completed plan back to active when follow-up work appears.
The user-level goal remains grouped under one plan.

Why it is tempting:

- It gives humans a more obvious container for the whole job.
- It avoids plan sprawl in simple live smoke tests.
- It makes "finish the project" feel like one visible plan lifecycle.

Why not implement it now:

- `done` stops meaning terminal.
- The plan status machine grows a `done -> active` path.
- Queue selection, integrity checks, and e2e tests need more cases.
- Acceptance becomes harder to reason about because a previously accepted plan can become active
  again.

This model may be worth revisiting if plan fragmentation becomes a real usability problem.

## Model C: Explicit Final Supervisor Closure

This model separates task completion from plan closure. Worker tasks may finish, but the plan remains
open until the supervisor records final review or final acceptance.

Why it may be right later:

- It matches the factory mental model: workers complete units, the supervisor closes the job.
- It gives a clean place for final audit, smoke test, and release notes.
- It can represent complex multi-worker projects without pretending each task closes the whole goal.

Why not implement it now:

- It adds a new explicit plan-closing operation or policy.
- It requires tests for open-with-no-ready-tasks, final review evidence, and close failure.
- It makes the active queue less simple because a plan can be open even when no worker task is ready.
- It risks growing supervisor surface before the current factory path is stable.

Model C is the likely long-term candidate if `codex-supervisor` needs richer factory reporting or
human-facing project dashboards.

## Decision

Keep Model A. Do not add plan reactivation or explicit plan closure yet.

The current priority is a compact, inspectable, testable factory loop:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

The next pressure to watch is not whether Model A is aesthetically ideal. The real question is
whether Model A makes the factory too hard to inspect. If Codex can analyze the ledger and explain
the job clearly, Model A remains the lower-complexity choice.
