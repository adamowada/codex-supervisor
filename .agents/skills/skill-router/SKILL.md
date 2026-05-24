---
name: skill-router
description: Route a Codex-supervisor request to the smallest appropriate repo-local skill. Use when several skills could apply, when starting a fresh thread and choosing the workflow, or when deciding whether work belongs in planning SQLite, GitHub issues, review, triage, CI repair, architecture review, or handoff.
---

# Skill Router

Use this skill as a dispatcher. Prefer the smallest skill that directly matches the request; do not stack large workflows when a narrow skill will do.

## Authority Matrix

For `codex-supervisor` and spawned projects, use an authority matrix rather than a single global
source order unless the repo says otherwise:

- locked source-of-truth docs win for durable doctrine, architecture, contracts, testing policy,
  roadmap intent, and stable operating rules;
- planning SQLite and `story-loop-status` win for active and blocked current-queue plans, current
  queue state, task status, worker runs, progress events, and handoff order;
- GitHub issues and PRs win for remote tracker state only after reconciliation into planning SQLite;
- handoff artifacts are mutable snapshots;
- chat/session history is context, not durable authority.

If the selected skill would write to the wrong source, stop and route explicitly: use
`planning-sqlite-operator` for queue state, `source-lock-operator` for protected hashes, or
`setup-agent-docs` when the repository has not defined its source-of-truth policy yet.

## Route By Intent

- New repo setup for small imported-skill prerequisites: `setup-agent-docs`.
- Full project bootstrap spawned by `codex-supervisor`: `spawned-project-bootstrap`.
- Inspect, create, update, or reconcile planning SQLite rows and current queue state: `planning-sqlite-operator`.
- Convert a plan into AFK/HITL work: `factory-task-decomposer`.
- Shape one vague task into an AFK-ready contract: `afk-issue-shaper`.
- Draft a Codex Goal-style objective or completion contract: `goal-contract-drafter`.
- Run, claim, or execute one queued story through a one-story loop: `story-loop-runner`.
- Publish approved task contracts to an issue tracker: `to-issues`.
- Triage incoming issues or move issue states: `triage`.
- Prepare a fresh-context worker prompt or manual handoff: `fresh-context-worker`.
- Create or guard an isolated worktree/sandbox: `worktree-sandbox-guard`.
- Run TDD loops: `tdd`.
- Prototype uncertain logic or UI: `prototype`.
- Step back for a higher-level system map: `zoom-out`.
- Summarize subagent findings into one digest: `subagent-run-digest`.
- Review a branch, commit, diff, or whole repo from a fresh thread: `fresh-thread-code-reviewer`.
- Fix review findings after the user agrees: `review-finding-fixer`.
- Repair CI or failing checks: `ci-repair-loop`.
- Operate PR metadata, CI checks, workflow logs, reruns, or merge workflows: `git-pr-ci-operator`.
- Classify and loop on a failed command: `failure-loop-triage`.
- Diagnose a hard bug or performance regression: `diagnose`.
- Audit local Codex state as read-only telemetry: `codex-state-readonly-audit`.
- Improve architecture, seams, and testability: `improve-codebase-architecture`.
- Stress-test a plan against domain language and decisions: `grill-with-docs`.
- Attribute claims and copied/inspired material: `source-evidence-attributor`.
- Update durable knowledge in `insights/`: `knowledge-graph-updater`.
- Evaluate, test, and refine skills over time: `skill-golden-eval-loop`.
- Triage ambient suggestions into durable work or insights: `ambient-suggestion-triager`.
- Maintain locked source-of-truth hashes: `source-lock-operator`.
- Avoid Windows shell quoting pitfalls: `windows-shell-quoting`.
- Choose verification commands: `verification-command-picker`.
- Create a compact handoff before context compaction: `context-compaction-handoff`.
- Resume from a compact handoff in a fresh thread: `thread-resume-brief`.
- Publish with add/commit/push after explicit approval: `acp-publisher`.

## Tie Breakers

- Planning beats publishing. If work is not approved, keep it in planning SQLite or a local task contract before creating issues.
- Goal Contracts beat open-ended execution. If the stop condition is unclear, draft or repair the Goal Contract before launching a worker.
- Story loops beat broad execution. If several AFK tasks are ready, run one vertical slice per iteration.
- Review beats fixing. If the user asks for review, report findings first; use `review-finding-fixer` only after they ask to fix them.
- CI repair beats general diagnosis when there is a concrete failed job or check.
- `git-pr-ci-operator` beats `acp-publisher` for PR metadata, CI logs, reruns, reviews, and merges.
- `diagnose` beats architecture review when a bug is still unreproduced.
- `improve-codebase-architecture` beats `grill-with-docs` when the request is mainly about module depth, seams, or testability.
- `grill-with-docs` beats architecture review when the plan or vocabulary is still fuzzy.
- Architecture-only code review starts in `fresh-thread-code-reviewer` for findings format, then
  uses `improve-codebase-architecture` vocabulary for the analysis lens.
