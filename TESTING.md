# Testing

The test strategy protects the supervisor's core promises: reproducible planning, safe full-auto
orchestration, durable memory, and production-worthy code.

## Default Suite

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python scripts/check_protected_files.py
```

The default suite must be deterministic and must not launch real Codex workers.

## Test Layers

### Unit

- planning records and serialization;
- SQLite initialization and idempotency;
- task status transitions;
- source lock hash calculation;
- prompt rendering;
- project adapter parsing;
- result schema validation.

### Integration

- create a temporary repo;
- initialize planning database;
- compile a plan into tasks;
- create a worktree;
- run a fake worker backend;
- parse fake JSONL;
- record artifacts and progress.

### Contract

Contract tests must protect:

- worker result schema;
- task schema;
- source lock file shape;
- planning schema migrations;
- insights graph conventions.

### Live/Full-Auto

Live Codex execution must be opt-in during early implementation. Once the supervisor matures, live
full-auto smoke tests may run only in explicitly marked trusted environments.
