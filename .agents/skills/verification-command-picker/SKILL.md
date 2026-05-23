---
name: verification-command-picker
description: Choose the smallest useful verification commands for a repo or change. Use before running tests, lint, typecheck, build, visual checks, CI repair, or ACP.
---

# Verification Command Picker

Pick commands from repo evidence, then run narrow to broad.

## Signals

- Python: `pyproject.toml`, `uv.lock`, `pytest`, `ruff`, `mypy`.
- Node/TypeScript: `package.json`, lockfile, `pnpm`, `npm`, `eslint`, `tsc`, `vitest`, `playwright`.
- Source locks: `scripts/check_protected_files.py`.
- Frontend: local server command, browser screenshots, viewport checks.
- CI: workflow files and PR check names.

## Order

1. Run the exact narrow test or check covering the changed surface.
2. Run lint/format/typecheck for touched language.
3. Run the broader gate before ACP or handoff.
4. Say what was not run and why.
