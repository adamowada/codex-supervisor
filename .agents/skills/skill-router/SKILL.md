---
name: skill-router
description: Route a Codex-supervisor request to the smallest appropriate repo-local skill. Use when several skills could apply, when starting a fresh thread and choosing the workflow, or when deciding whether work belongs in planning SQLite, GitHub issues, review, triage, CI repair, architecture review, or handoff.
---

# Skill Router

Use this skill as a dispatcher. Prefer the smallest skill that directly matches the request; do not stack large workflows when a narrow skill will do.

## Source Order

For `codex-supervisor` and spawned projects, resolve conflicts in this order unless the repo says otherwise:

1. Locked source-of-truth docs.
2. Planning SQLite.
3. GitHub issues and PRs.
4. Handoff artifacts.
5. Chat/session history.

If the selected skill would write to the wrong source, stop and switch to the source-of-truth skill first.

## Route By Intent

- New repo setup or imported skill prerequisites: `setup-agent-docs`.
- Convert a plan into AFK/HITL work: `factory-task-decomposer`.
- Shape one vague task into an AFK-ready contract: `afk-issue-shaper`.
- Publish approved task contracts to an issue tracker: `to-issues`.
- Triage incoming issues or move issue states: `triage`.
- Start work in a clean context or isolated worker: `fresh-context-worker`.
- Guard direct edits with a worktree: `worktree-sandbox-guard`.
- Review a branch, commit, diff, or whole repo from a fresh thread: `fresh-thread-code-reviewer`.
- Fix review findings after the user agrees: `review-finding-fixer`.
- Repair CI or failing checks: `ci-repair-loop`.
- Classify and loop on a failed command: `failure-loop-triage`.
- Diagnose a hard bug or performance regression: `diagnose`.
- Improve architecture, seams, and testability: `improve-codebase-architecture`.
- Stress-test a plan against domain language and decisions: `grill-with-docs`.
- Update durable knowledge in `insights/`: `knowledge-graph-updater`.
- Maintain locked source-of-truth hashes: `source-lock-operator`.
- Choose verification commands: `verification-command-picker`.
- Create a compact handoff before context compaction: `context-compaction-handoff`.
- Resume from a compact handoff in a fresh thread: `thread-resume-brief`.
- Publish with add/commit/push after explicit approval: `acp-publisher`.

## Tie Breakers

- Planning beats publishing. If work is not approved, keep it in planning SQLite or a local task contract before creating issues.
- Review beats fixing. If the user asks for review, report findings first; use `review-finding-fixer` only after they ask to fix them.
- CI repair beats general diagnosis when there is a concrete failed job or check.
- `diagnose` beats architecture review when a bug is still unreproduced.
- `improve-codebase-architecture` beats `grill-with-docs` when the request is mainly about module depth, seams, or testability.
- `grill-with-docs` beats architecture review when the plan or vocabulary is still fuzzy.
