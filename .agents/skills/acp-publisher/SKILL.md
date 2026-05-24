---
name: acp-publisher
description: Safely perform Add-Commit-Push when the user says ACP or explicitly asks Codex to stage, commit, and push the current work. Use for local commit/push publication only; route PR metadata, CI logs, reruns, reviews, and merges to git-pr-ci-operator.
---

# ACP Publisher

Treat ACP as a publish operation, not just three commands.

If the current user turn is read-only, review-only, audit-only, no-edits, no-mutation, or says not
to stage/commit/push, do not run ACP. Return the exact paths and commands that would be used once
publication is approved.

## Workflow

1. Run the relevant pre-stage project guard first: tests, source locks, secret/path scan, or a
   targeted check.
2. Inspect `git status --short --ignored` and confirm ignored caches, envs, clones, logs, and build outputs stay ignored.
3. Identify the intended path set from the current task, recent edits, and user instruction.
4. Stage only that path set by default.
5. Use `git add -A` only when the working tree is clean except agent-owned changes or the user
   explicitly says to publish every change.
6. Inspect `git diff --cached --name-only` and `git diff --cached --stat`.
7. Stop if staged files include secrets, generated caches, vendored source clones, unrelated user edits, or unexpected binaries.
8. For `codex-supervisor` public checkpoints, run
   `uv run python -B scripts/verify.py --publication-ready` after staging and before committing.
9. Commit with a concise message that names the durable outcome.
10. Push to the existing upstream, or add/rename/push exactly as the user requested.
11. Final response: commit hash, branch, remote, push result, and remaining status.

For public repos, scan for common secret tokens and local absolute paths before committing.
