# Goal Mode And Ralph Loop

Confidence: mixed. Source facts are confirmed where tied to official docs, tracked source
inventory, or local telemetry. Project policy below is inferred unless backed by implementation or
tests.

## Evidence

- OpenAI's Codex Goals documentation describes goals as durable objectives with validation loops,
  lifecycle controls, evidence-based stop conditions, and lifecycle commands including `/goal`,
  `/goal pause`, `/goal resume`, and `/goal clear`.
- Native Codex Goals require a Codex build that supports Goals. Run `codex --version` before relying
  on `/goal`, then update Codex if needed; the official cookbook says Goals are available starting in
  Codex 0.128.0.
- Current official Codex use-case docs say Goals-capable installs may need
  `[features] goals = true` in `${CODEX_HOME}/config.toml` or `codex features enable goals` before
  `/goal` is visible.
- Worker launches must use the intended `CODEX_HOME`; otherwise Codex may load a sandbox home where
  Goals are disabled or auth is unavailable.
- Local `~/.codex/goals_1.sqlite` has the shape for thread-scoped goals. Treat row counts as
  time-sensitive telemetry, not stable doctrine.
- `sources/README.md` pins `sources/snarktank-ralph` at commit
  `6c53cb0b831ebe8739c6a003e22af14902d8b0b5` with observed MIT license posture.
- The tracked source inventory pins `sources/snarktank-ralph` to commit
  `6c53cb0b831ebe8739c6a003e22af14902d8b0b5`. The local clone is an inspection cache; durable
  evidence should cite the pinned upstream commit, tracked inventory, or tracked excerpts rather
  than relying on mutable ignored files. At that pinned revision, Ralph's README, prompt, and Ralph
  skill describe one unfinished story per iteration, quality checks, passing commits, progress
  updates, reusable learnings, and a right-sized-story rule that should fit in one fresh context
  window.

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
- Explicit Codex version, `CODEX_HOME`, and Goals feature verification before fresh-context worker
  launch.
- Treat `codex features enable goals` or `[features] goals = true` as a write-enabled preflight; in
  read-only mode, use a prompt-rendered Goal Contract fallback instead.

## Project Implication

Goal Contract and Story Loop support is now implemented locally and should remain the execution
bridge before the Codex Exec backend. Future work should preserve that contract, tighten it through
active planning tasks, and avoid reimplementing Stage 5 unless the database explicitly opens a new
task for it.
