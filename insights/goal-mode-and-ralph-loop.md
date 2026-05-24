# Goal Mode And Ralph Loop

Confidence: confirmed.

## Evidence

- OpenAI's Codex Goals documentation describes goals as durable objectives with validation loops,
  lifecycle controls, and evidence-based stop conditions.
- Local `~/.codex/goals_1.sqlite` currently has the shape for thread-scoped goals, but no active
  rows in the audited environment.
- `sources/snarktank-ralph` is MIT licensed and implements a fresh-context loop where each iteration
  picks one unfinished story, runs checks, commits, records progress, and repeats until stories pass.

## Synthesis

`codex-supervisor` should not replace planning SQLite with either native Codex Goals or Ralph's
`prd.json`. Instead:

- planning SQLite remains the canonical queue;
- Goal Contracts guide a thread or worker toward one evidence-based finish line;
- Story Loop policy executes one vertical slice per fresh-context worker;
- insights capture reusable lessons that Ralph would place in `progress.txt` or `AGENTS.md`;
- native Codex Goal state and local Codex databases are reconciled back as telemetry.

## Useful Ralph Patterns

- One story per iteration.
- Fresh worker context every iteration.
- Durable progress between iterations.
- Checks before marking a story passed.
- Commit history as part of memory.
- Reusable codebase learnings promoted before the next iteration.

## Useful Codex Goal Patterns

- One durable objective at a time.
- Explicit context to read first.
- Clear in-scope and out-of-scope boundaries.
- Validation commands or artifacts.
- Stop condition and blocked condition.
- Pause, resume, clear, or budget-limited lifecycle handled by Codex tooling rather than raw DB
  writes.

## Project Implication

The next implementation stage should add Goal Contract and Story Loop support before the Codex Exec
backend. This gives every worker a precise objective and every multi-worker run a bounded loop.
