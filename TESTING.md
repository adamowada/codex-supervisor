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
  planning database without relying on `codex-supervisor` being on `PATH`.

## Test Philosophy

- Test the model before the interface.
- Test one transition path at a time.
- Test AFK workers as process attempts, not as job-specific modes.
- Add tests with rebuilt behavior.
- Keep tests close to task, attempt, evidence, and acceptance semantics.

## Near-Term Test Growth

Next tests should cover:

- new adapter operations only after they are declared;
- acceptance behavior at `attempt-transition`;
- process evidence and assignment capture at `attempt-run`;
- plugin launch wiring for the compact MCP stdio server;
- plugin CLI launch wiring for fresh-folder full AFK setup;
- installed-cache plugin launch without `CODEX_SUPERVISOR_REPO_ROOT`;
- packaged skill instructions that require task intent, attempt, evidence, and acceptance when the
  supervisor is invoked for work;
- queue inspection through `AttemptStore`;
- planning schema integrity from the production schema builder.
