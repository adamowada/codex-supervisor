# Testing

The test strategy protects the supervisor's core promises: reproducible planning, safe full-auto
orchestration, durable memory, and production-worthy code.

## Default Suite

```sh
uv run python -B scripts/verify.py
```

During a HITL ACP/publication checkpoint, the default suite can intentionally fail at the protected
file lock guard until intended protected files are tracked and hashes have been refreshed. In that
state, run the component checks listed in `HANDOFF.md` to verify implementation quality, then use
the default suite again after the checkpoint is staged or resolved.

The default suite expands to:

```sh
uv run python -B -m pytest -p no:cacheprovider
uv run ruff check . --no-cache
uv run ruff format --check . --no-cache
uv run mypy --no-incremental src scripts
uv run python -B -m codex_supervisor.cli --help
uv run --no-sync codex-supervisor --help
uv run python -B scripts/check_file_justification.py
uv run python -B scripts/check_public_repo_hygiene.py
uv run python -B scripts/check_planning_integrity.py
uv run python -B scripts/check_skill_inventory.py
uv run python -B scripts/check_source_inventory.py
uv run python -B scripts/check_protected_files.py
uv lock --check
```

The default suite must be deterministic and must not launch real Codex workers.
It sets `PYTHONDONTWRITEBYTECODE=1` and uses cache-safe pytest, Ruff, and mypy flags so verification
does not depend on stale cache state. Local tooling can still leave ignored environment or cache
directories such as `.venv/`, `.mypy_cache/`, or `__pycache__/` when run outside the verifier or by
dependency setup; those artifacts are ignored and must remain unstaged.

## Publication Gate

Before ACP or public release, run the stricter publication gate:

```sh
uv run python -B scripts/verify.py --publication-ready
```

This runs the full default suite and passes `--publication-ready` through to
`scripts/check_public_repo_hygiene.py`. It intentionally fails while non-ignored public files are
untracked or unstaged. It also checks that protected source-of-truth files and planning artifact
evidence are present in the git index, while ignored `sources/` clones remain unstaged.

`scripts/check_file_justification.py` protects the bootstrap shape by requiring every public file and
folder to match an intentional purpose category.

`scripts/check_skill_inventory.py` protects repo-local skills by requiring frontmatter name and
description metadata, folder/name agreement, route-map coverage, and no prohibited tool-family drift.

## Test Layers

### Current Unit And Script Coverage

- planning records and serialization;
- planning SQLite drift checks;
- completed worker-result existence, shared-result identity, and JSON result schema checks;
- SQLite initialization and idempotency;
- planning CLI creation, lifecycle, and fresh-thread error handling;
- task status transitions;
- atomic task claiming and running queue-state reporting;
- Story Loop queue reporting for active and blocked current-queue plans;
- safe task and worker-run upserts that preserve omitted contract/evidence fields by default;
- source lock hash calculation;
- Goal Contract prompt rendering;
- planning schema v2/v3 migration and critical DDL validation;
- Story Loop status and progress recording;
- public repo hygiene, file purpose, skill inventory, and source inventory checks.

### Planned Expansion

These surfaces are part of the contract but are not implemented deeply enough to call covered yet:

- project adapter parsing;
- future planning schema migrations beyond schema version 3;
- insights graph convention validation;
- fake worker backend execution;
- JSONL parsing for worker evidence.

### Future Integration

- create a temporary repo;
- initialize planning database;
- compile a plan into tasks;
- create a worktree;
- run a fake worker backend;
- parse fake JSONL;
- record artifacts and progress.

### Future Contract

Contract tests must protect:

- worker result schema;
- task schema;
- source lock file shape;
- planning schema migrations;
- insights graph conventions.

### Live/Full-Auto

Live Codex execution must be opt-in during early implementation. Once the supervisor matures, live
full-auto smoke tests may run only in explicitly marked trusted environments.
