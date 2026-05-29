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
- e2e coverage for MCP stdio and generic AFK process attempts.

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
- process evidence capture at `attempt-run`;
- queue inspection through `AttemptStore`;
- planning schema integrity from the production schema builder.
