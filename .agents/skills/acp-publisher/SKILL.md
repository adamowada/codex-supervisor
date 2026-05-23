---
name: acp-publisher
description: Safely perform Add-Commit-Push when the user says ACP or asks Codex to stage, commit, and push. Use before git add, git commit, git branch/remote setup, or git push, especially for public repos or source-of-truth changes.
---

# ACP Publisher

Treat ACP as a publish operation, not just three commands.

## Workflow

1. Run the relevant project guard first: tests, source locks, secret/path scan, or a targeted check.
2. Inspect `git status --short --ignored` and confirm ignored caches, envs, clones, logs, and build outputs stay ignored.
3. Stage with `git add -A`.
4. Inspect `git diff --cached --name-only` and `git diff --cached --stat`.
5. Stop if staged files include secrets, generated caches, vendored source clones, unrelated user edits, or unexpected binaries.
6. Commit with a concise message that names the durable outcome.
7. Push to the existing upstream, or add/rename/push exactly as the user requested.
8. Final response: commit hash, branch, remote, push result, and remaining status.

For public repos, scan for common secret tokens and local absolute paths before committing.
