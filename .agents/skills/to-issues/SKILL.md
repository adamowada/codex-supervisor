---
name: to-issues
description: Break an approved plan, spec, PRD, or planning SQLite task set into independently-grabbable issue drafts or tracker issues using tracer-bullet vertical slices. Use when the user wants to convert a plan into implementation tickets, publish AFK/HITL task contracts, or move planned work from Codex-supervisor planning into a configured issue tracker.
---

# To Issues

Break a plan into independently-grabbable issues using vertical slices (tracer bullets).

The issue tracker, triage label vocabulary, and source-of-truth order should already be documented. If not, run `setup-agent-docs` first.

For `codex-supervisor` spawned projects, planning SQLite is the durable queue and GitHub issues are a publishing surface. Do not let issue text contradict locked source-of-truth docs or active planning records.

## Process

### 1. Gather Context

Work from the highest-authority available source:

1. Locked source-of-truth docs.
2. Planning SQLite plans/tasks.
3. Existing issue tracker items.
4. Handoff artifacts.
5. Chat/session context.

If the user passes an issue reference, planning task id, URL, or path, fetch the full artifact before drafting.

### 2. Explore The Codebase

If you have not already explored the codebase, do so to understand the current state. Issue titles and descriptions should use the project's domain glossary vocabulary, respect ADRs and locked docs, and avoid stale file-path instructions.

### 3. Draft Vertical Slices

Break the plan into **tracer bullet** issues. Each issue is a thin vertical slice that cuts through all integration layers end-to-end, not a horizontal slice of one layer.

Slices may be `HITL` or `AFK`. HITL slices require human interaction, such as an architectural decision, design review, credential access, or production approval. AFK slices can be implemented and verified without human interaction. Prefer AFK over HITL where possible, but do not pretend uncertain work is AFK-ready.

<vertical-slice-rules>
- Each slice delivers a narrow but complete path through every layer.
- A completed slice is demoable or verifiable on its own.
- Prefer many thin slices over few thick ones.
- Each slice has acceptance criteria and verification commands.
- Each slice states what is out of scope.
</vertical-slice-rules>

### 4. Quiz The User

Present the proposed breakdown before publishing. For each slice, show:

- **Title**: short descriptive name.
- **Type**: HITL / AFK.
- **Blocked by**: which other slices must complete first.
- **User stories covered**: which user stories this addresses, if present.
- **Verification**: commands or checks that prove completion.
- **Publication target**: planning SQLite, issue tracker, or draft markdown.

Ask the user:

- Does the granularity feel right?
- Are the dependency relationships correct?
- Should any slices be merged or split further?
- Are the correct slices marked as HITL and AFK?

Iterate until the user approves the breakdown.

### 5. Publish Only When Configured

If planning SQLite is active, upsert the approved slices as supervisor tasks first. If a GitHub connector is available and the repo uses GitHub issues, prefer connector tools over the `gh` CLI. If no tracker is configured, emit issue markdown/task contracts and tell the user where the durable queue should live before publishing.

Publish approved issues in dependency order so you can reference real issue identifiers in the "Blocked by" field. Apply the configured `ready-for-agent` or HITL label/state only after the issue body is complete.

<issue-template>
## Parent

A reference to the parent issue on the issue tracker, if the source was an existing issue.

## What to build

A concise description of this vertical slice. Describe the end-to-end behavior, not layer-by-layer implementation.

Avoid specific file paths or code snippets because they go stale fast. Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can, inline only the decision-rich part and note that it came from a prototype.

## Acceptance criteria

- [ ] Criterion 1.
- [ ] Criterion 2.
- [ ] Criterion 3.

## Blocked by

- A reference to the blocking ticket, or "None - can start immediately."

## Verification

- Command or check that proves this slice is done.

## Out of scope

- Adjacent behavior that should not be changed in this issue.
</issue-template>

Do not close, retitle, or otherwise modify any parent issue unless the user explicitly asks.
