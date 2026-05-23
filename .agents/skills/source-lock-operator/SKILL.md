---
name: source-lock-operator
description: Maintain SHA-256 locks for top-level source-of-truth documents. Use when checking, intentionally updating, or explaining protected document hashes.
---

# Source Lock Operator

Protected docs are listed in `scripts/check_protected_files.py`.

## Workflow

1. Run `uv run python scripts/check_protected_files.py`.
2. If a file changed unintentionally, stop and report it.
3. If the change was intentional, run `uv run python scripts/print_protected_hashes.py`.
4. Update the hash mapping in `scripts/check_protected_files.py`.
5. Re-run the check.

Never update hashes just to silence a failure.
