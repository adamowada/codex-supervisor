# Testing

The old test suite was removed as an acceptance authority. It tested the accumulated factory, not
the simplified product.

## Current Gate

Run:

```sh
uv run --no-sync python -B scripts/verify.py
```

The current gate checks:

- fresh planning database schema and seed records;
- minimal skill inventory;
- protected source-of-truth hashes;
- focused tests for the simplified contract.

## Test Philosophy

- Test the model before the interface.
- Test one transition path instead of every historical mode combination.
- Add tests when behavior is rebuilt.
- Delete tests when the behavior they protect is intentionally deleted.

## Not Currently Required

The following are not current gates:

- old CLI command matrix;
- old MCP tool matrix;
- plugin packaging;
- release-readiness automation;
- spawned-project scaffolds;
- legacy worker result ingestion;
- old planning integrity rules.

Those gates can return only with rebuilt behavior.
