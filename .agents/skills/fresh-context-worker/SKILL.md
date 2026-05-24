---
name: fresh-context-worker
description: Prepare prompts and handoffs for fresh-context Codex workers. Use when designing or reviewing worker prompts, result schemas, or context handoffs; until the Stage 6 backend exists, do not imply the supervisor can launch workers automatically.
---

# Fresh Context Worker

Every worker prompt should be self-contained and small.

Until ROADMAP Stage 6 is implemented, prepare a manual worker handoff or current-thread execution
prompt. Do not claim `codex-supervisor` can launch Codex Exec workers automatically.

If the current user turn is read-only, review-only, audit-only, no-edits, or no-mutation mode, do
not start workers, create worktrees, write prompt artifacts, update planning state, or mutate git or
trackers. Return the proposed worker prompt, context bundle, result schema, and next commands only.

If using native Codex Goals, route through `goal-contract-drafter` and apply its Goal Mode preflight,
including the `${CODEX_HOME}/config.toml` `[features] goals = true` fallback.

## Include

- task contract;
- Goal Contract from `goal-contract-drafter`;
- relevant source-of-truth file pointers;
- acceptance criteria;
- allowed paths;
- verification commands;
- output schema;
- explicit stop conditions.
- where to record progress, artifacts, and reusable learnings.

## Standard Result Schema

Require workers to return a JSON result matching `../worker-result-contract.md`. Use those field
names because they mirror `CONTRACTS.md`; do not invent a parallel schema inside prompts. In
particular, `artifacts` must include the JSON `result_path`, while `changed_files` should stay
focused on implementation or durable-documentation paths covered by task `allowed_paths`.

## Exclude

- unrelated chat history;
- full source dumps when file paths are enough;
- broad refactor permission;
- hidden tests or private fixtures.
- multiple unrelated stories in one worker prompt.
