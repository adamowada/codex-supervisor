---
name: fresh-context-worker
description: Prepare prompts for fresh-context Codex workers launched by the supervisor. Use when designing or reviewing worker prompts, result schemas, or context handoffs.
---

# Fresh Context Worker

Every worker prompt should be self-contained and small.

## Include

- task contract;
- relevant source-of-truth file pointers;
- acceptance criteria;
- allowed paths;
- verification commands;
- output schema;
- explicit stop conditions.

## Exclude

- unrelated chat history;
- full source dumps when file paths are enough;
- broad refactor permission;
- hidden tests or private fixtures.
