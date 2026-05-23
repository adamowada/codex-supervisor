---
name: worktree-sandbox-guard
description: Prepare or verify isolated worktrees and scoped sandboxes for AFK/full-auto Codex work. Use before dangerous/full-access tasks, worker launches, large edits, parallel implementation, or unattended project automation.
---

# Worktree Sandbox Guard

Full-auto work belongs in a bounded workspace.

## Checklist

- Inspect current branch, status, and uncommitted files.
- Identify allowed paths and forbidden paths.
- Use a disposable worktree for unattended implementation or risky parallel work.
- Keep worker artifacts under ignored `runs/`, `worktrees/`, `artifacts/`, or equivalent folders.
- Capture verification commands before launch.
- Require a handoff artifact from the worker.
- Before cleanup, resolve absolute paths and verify they are inside the intended workspace.

Direct edits are acceptable only for small, scoped, supervised changes in a clean or understood worktree.
