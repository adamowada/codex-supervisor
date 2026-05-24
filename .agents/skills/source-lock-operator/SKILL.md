---
name: source-lock-operator
description: Maintain SHA-256 locks for top-level source-of-truth documents. Use when checking, intentionally updating, or explaining protected document hashes.
---

# Source Lock Operator

This skill is specific to repositories that use the `codex-supervisor` source-lock layout.
In this repository, protected docs are listed in `src/codex_supervisor/locks.py`. Expected hashes
live in `scripts/check_protected_files.py`. For spawned projects, use that project's configured
lock manifest or route through `spawned-project-bootstrap` before assuming these paths exist.

## Workflow

1. If the current turn is read-only, review-only, audit-only, no-edits, or no-mutation mode, do not
   update hashes. Run `uv run` commands only when dependencies are already present; otherwise inspect
   existing Git state/files and report the exact check/update commands to run later.
2. Run `uv run python -B scripts/check_protected_files.py`.
3. If a file changed unintentionally, stop and report it.
4. If a protected file is new but untracked, do not update hashes yet. During a HITL ACP checkpoint,
   report the required sequence: stage or otherwise intentionally track the protected file, refresh
   hashes, rerun the guard, then commit/push only after approval.
5. If the change was intentional, run `uv run python -B scripts/print_protected_hashes.py`.
6. Update the hash mapping in `scripts/check_protected_files.py`.
7. Re-run the check.

Never update hashes just to silence a failure.
