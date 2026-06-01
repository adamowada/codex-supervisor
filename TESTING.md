# Testing

The verification strategy protects the active control-plane contract.

## Current Gate

Run:

```sh
uv run --no-sync python -B scripts/verify.py
```

The gate checks:

- planning database schema and seed records;
- repo-local skill inventory;
- protected source-of-truth hashes;
- focused tests for the compact contract;
- e2e coverage for MCP stdio, the Codex plugin wrapper, and generic AFK process attempts.
- e2e coverage that proves an autonomous worker receives task assignment metadata and completes an
  empty project through `attempt-run`.
- e2e coverage that the installed-cache plugin CLI launcher can initialize and inspect a fresh
  planning database with `plan-init --json` without relying on `codex-supervisor` being on `PATH`.
- e2e coverage that the installed-cache plugin CLI launcher defaults omitted planning paths to the
  invocation workspace, not the source repository.
- e2e coverage that failed process attempts cannot record supplied passing acceptance results as
  passing evidence.
- e2e coverage that verifier failures override supplied passing acceptance results.
- e2e coverage that process launch failures, missing declared artifacts, retry after blocked work,
  and running queue inspection preserve durable factory state.
- e2e coverage that installed-cache MCP queue inspection uses an explicit workspace ledger path
  instead of the source repository ledger.
- e2e coverage that full-AFK product follow-up mutation is assigned through another worker attempt,
  preserving the supervisor role boundary.
- contract coverage that `HANDOFF.md` edits are paired with `plans/planning.sqlite3` edits, so the
  readable handoff and durable ledger stay current together.

## Test Philosophy

- Test the model before the interface.
- Test one transition path at a time.
- Test AFK workers as process attempts, not as job-specific modes.
- Add tests with rebuilt behavior.
- Keep tests close to task, attempt, evidence, and acceptance semantics.

## Near-Term Test Growth

Next tests should cover:

- new adapter operations only after they are declared;
- literal execution of the plugin MCP manifest command;
- schema/index integrity from a freshly initialized production database;
- new adapter operations only after the existing factory path stays boring.
