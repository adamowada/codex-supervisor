---
name: fresh-context-worker
description: Prepare prompts and handoffs for fresh-context Codex workers. Use when designing or reviewing worker prompts, result schemas, backend preflight evidence, or context handoffs for isolated Codex worker execution.
---

# Fresh Context Worker

Every worker prompt should be self-contained and small.

Do not infer worker-launch capability from `ROADMAP.md`. Worker execution is available only when
the selected `worker_backend`, environment preflight, and planning SQLite evidence show a launchable
path. If no launchable backend is available, prepare a manual worker handoff or record a blocker;
do not claim `codex-supervisor` launched a worker.

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
names because they mirror `CONTRACTS.md`; do not invent a parallel schema inside prompts.
`changed_files` should stay focused on implementation or durable-documentation paths covered by task
`allowed_paths`. Raw JSON result files under ignored runtime directories are transient import
sources; after ingestion, durable evidence lives in planning SQLite, with `artifacts` reserved for
tracked supporting docs/reports, tracked insight or handoff anchors, or external URLs.

## Exclude

- unrelated chat history;
- full source dumps when file paths are enough;
- broad refactor permission;
- hidden tests or private fixtures.
- multiple unrelated stories in one worker prompt.
