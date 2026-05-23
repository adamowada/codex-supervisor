---
name: git-pr-ci-operator
description: Run a git/GitHub publishing and CI workflow. Use when Codex needs to inspect status/diff, create branches, commit, push, open or update PRs, inspect GitHub checks, fetch CI logs, rerun jobs, or merge.
---

# Git PR CI Operator

Prefer local git for repository state and GitHub connector tools for remote PR/CI state.

## Sequence

1. Inspect `git status --short --branch`, remotes, branch, and recent log.
2. Inspect diffs before staging or reviewing.
3. Run the relevant verification gate.
4. Stage only intended files.
5. Commit and push.
6. Use GitHub connector data for PR metadata, changed files, checks, workflow jobs, and logs.
7. Fix CI with `failure-loop-triage`: narrow failing job first, then broader gate.
8. Merge only when the user requested it and required checks/reviews are satisfied.

Do not rely on `gh` CLI when connector tools are available and already authenticated.
