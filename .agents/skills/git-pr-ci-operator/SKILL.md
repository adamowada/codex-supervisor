---
name: git-pr-ci-operator
description: Operate PR, GitHub, and CI workflows. Use when Codex needs to create or update PRs, inspect GitHub checks, fetch CI logs, rerun jobs, review remote state, or merge; use acp-publisher for simple local add-commit-push.
---

# Git PR CI Operator

Prefer local git for repository state and GitHub connector tools for remote PR/CI state.

If the current user turn says read-only, review-only, audit-only, no-edits, or no-mutation, force
`inspect_only`: return proposed PR, CI, rerun, merge, or branch mutations instead of performing
them.

## Modes

- `inspect_only`: read git, PR, and CI state; do not stage, commit, push, rerun, merge, or mutate.
- `repair_branch`: edit and publish only when the user asked for fixes or ACP/push behavior.
- `merge`: merge only when the user explicitly requested merge and required checks/reviews pass.

Default to `inspect_only` for requests to inspect, check, review, fetch logs, or report CI status.

## Sequence

1. Inspect `git status --short --branch`, remotes, branch, and recent log.
2. Inspect diffs before staging or reviewing.
3. Use GitHub connector data for PR metadata, changed files, checks, workflow jobs, and logs.
4. In `inspect_only`, stop here and report evidence without running local verification unless the
   user explicitly asked for local checks too.
5. In `repair_branch`, fix CI with `failure-loop-triage`: narrow failing job first, then broader gate.
6. Run the relevant verification gate before publishing repaired work.
7. Stage only intended files, commit, and push only when publishing was requested.
8. In `merge`, merge only when the user requested it and required checks/reviews are satisfied.

Do not rely on `gh` CLI when connector tools are available and already authenticated.

## Result Contract

Report branch, commit hash, PR URL or number, staged paths, commands/checks run, CI job IDs or
links inspected, reruns requested, merge/push result, residual risks, and remaining git status.
