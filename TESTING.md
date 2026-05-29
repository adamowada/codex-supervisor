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
- focused tests for the compact contract.

## Test Philosophy

- Test the model before the interface.
- Test one transition path at a time.
- Add tests with rebuilt behavior.
- Keep tests close to task, attempt, evidence, and acceptance semantics.

## Near-Term Test Growth

Next tests should cover:

- new adapter operations only after they are declared;
- acceptance behavior at `attempt-transition`;
- queue inspection through `AttemptStore`;
- planning schema integrity from the production schema builder.
