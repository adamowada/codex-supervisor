# Testing

The test strategy protects the supervisor's core promises: reproducible planning, safe full-auto
orchestration, durable memory, and production-worthy code.

## Default Suite

```sh
uv run python -B scripts/verify.py
```

During a HITL ACP/publication checkpoint, the protected-file lock guard can fail while intended
protected files are tracked and hashes are refreshed. In that checkpoint, run task-relevant component
checks recorded in planning SQLite or the compact `HANDOFF.md` snapshot, then run the default suite
again after the lock guard is reconciled.

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

The default suite is deterministic and does not launch real Codex workers. It sets
`PYTHONDONTWRITEBYTECODE=1` and uses cache-safe pytest, Ruff, and mypy flags so verification does
not depend on stale cache state. Local tooling can still leave ignored environment or cache
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
description metadata, folder/name agreement, route-map coverage, and no prohibited tool-family
drift.

## Required Test Surfaces

### Planning And Queue

- planning records and serialization;
- planning SQLite drift checks;
- SQLite initialization and idempotency;
- schema migrations and critical DDL validation;
- planning CLI creation, inspection, lifecycle, and fresh-thread error handling;
- task status transitions;
- atomic task claiming;
- running, ready, HITL, blocked, completed, and empty queue reporting;
- safe task and worker-run upserts that preserve omitted contract/evidence fields by default.

### Contracts And Evidence

- Worker Result Contract schema;
- task schema and AFK readiness;
- completed DB-backed worker result records;
- shared-result identity coverage through result/run links;
- supporting artifact-link relationships;
- exact acceptance-criterion evidence;
- zero-exit verification records;
- changed-file alignment with task `allowed_paths_json`;
- Goal Contract prompt rendering and native-goal fallback text.

### Source Of Truth And Hygiene

- source lock hash calculation;
- protected-file tracking;
- public repo hygiene;
- file purpose classification;
- source inventory validation;
- skill inventory validation;
- attribution and ignored-source boundaries.

### Orchestration

- Story Loop selection and stop conditions;
- progress recording;
- fake worker backend execution;
- Codex Exec worker-launch preflight;
- JSONL parsing for worker evidence;
- worktree setup, diff capture, and cleanup guards;
- review and repair-loop records.

### Project Intelligence

- project adapter parsing;
- verification command selection;
- insights graph conventions;
- skill golden task evaluation;
- Codex local state read-only imports;
- automation bridge records.

## Integration Harness

Integration tests use temporary repositories and fake worker backends to exercise the factory loop
without launching live Codex workers:

1. create a temporary repo;
2. initialize planning SQLite;
3. compile a plan into vertical-slice tasks;
4. create a worktree;
5. run a fake worker backend;
6. parse structured worker evidence;
7. record supporting artifacts, review results, progress events, DB-backed worker results, and
   compact handoff notes;
8. verify planning integrity and publication hygiene.

## Live Full-Auto

Live Codex execution is opt-in and requires an explicitly trusted environment. Live smoke tests use
disposable worktrees, narrow allowed paths, bounded tasks, structured result schemas, and verification
commands that can run repeatedly without damaging local state.
