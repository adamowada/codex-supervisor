---
name: fresh-context-worker
description: Prepare prompts for fresh-context Codex workers launched by the supervisor. Use when designing or reviewing worker prompts, result schemas, or context handoffs.
---

# Fresh Context Worker

Every worker prompt should be self-contained and small.

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

## Exclude

- unrelated chat history;
- full source dumps when file paths are enough;
- broad refactor permission;
- hidden tests or private fixtures.
- multiple unrelated stories in one worker prompt.
