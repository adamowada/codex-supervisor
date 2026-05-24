---
name: codex-supervisor
description: Top-level orchestrator for running an agentic engineering factory with Codex-supervisor. Use when the user asks Codex to manage a project, execute a multi-phase plan, coordinate workers, continue autonomously after planning, maximize production-quality output, or operate full-auto through planning, implementation, verification, review, handoff, and publication.
---

# Codex Supervisor

Use this as the thin conductor for the project. It defines the top-level loop, routes to smaller skills, and enforces global invariants. Do not duplicate the detailed procedures of child skills.

## Global Invariants

- Source order is locked docs, planning SQLite, GitHub issues/PRs, handoff artifacts, then chat history unless the repo documents a different order.
- Durable state beats conversation memory. Do not let chat be the only record of plans, decisions, tasks, verification, or handoff state.
- Prefer vertical slices that produce demoable, testable behavior.
- Prefer AFK-ready task contracts with Goal Contracts, but mark HITL honestly when judgment, secrets, external access, design approval, or production action is required.
- Use worktrees or sandboxed workers for risky, broad, or full-auto implementation.
- Keep worker context small and self-contained.
- Verify with the narrowest meaningful check first, then broaden when the change touches shared behavior.
- Review before merging or publishing production-impacting work.
- Update durable knowledge when a lesson should survive the thread.
- Create a handoff before context compaction, thread transfer, or long unattended work.

## Operating Loop

1. **Orient.** Read `AGENTS.md`, protected source-of-truth docs, `docs/agents/` if present, active planning SQLite records, and current git state.
2. **Select phase.** Decide whether the project needs planning, task shaping, implementation, review, failure repair, architecture work, knowledge update, handoff, or publishing.
3. **Route.** Use `skill-router` and then invoke the smallest relevant child skill.
4. **Contract.** Ensure the current task has goal, scope, out-of-scope, acceptance criteria, verification commands, allowed paths, blockers, HITL/AFK classification, and a Goal Contract.
5. **Isolate.** Use a worktree or fresh-context worker when full-auto work could collide with active user edits or span multiple tasks.
6. **Execute.** Implement one vertical slice or repair loop at a time. Use story-loop discipline for queued AFK work. Keep unrelated refactors out unless the selected skill says they are part of the task.
7. **Verify.** Run targeted checks, then broader checks as risk demands. Record failures through the failure skills instead of hand-waving.
8. **Review.** Use fresh-context review for branches, commits, diffs, or whole-repo reviews. Fix findings only after user or policy approval.
9. **Record.** Update planning SQLite, source-of-truth docs, insights, issue tracker state, and handoff artifacts as appropriate.
10. **Continue or hand off.** Pick the next ready task, publish if explicitly requested, or create a compact handoff for a fresh thread/worker.

## Route Map

- Bootstrap repo agent context: `setup-agent-docs`.
- Choose among overlapping workflows: `skill-router`.
- Decompose plans into phases and vertical slices: `factory-task-decomposer`.
- Shape one task into an AFK/HITL contract: `afk-issue-shaper`.
- Draft thread/worker completion contracts: `goal-contract-drafter`.
- Run one-story fresh-context loops: `story-loop-runner`.
- Operate planning SQLite: `planning-sqlite-operator`.
- Launch or prepare clean-context workers: `fresh-context-worker`.
- Guard risky/full-auto work: `worktree-sandbox-guard`.
- Convert approved contracts to issues: `to-issues`.
- Triage incoming issues: `triage`.
- Run TDD loops: `tdd`.
- Prototype uncertain logic or UI: `prototype`.
- Repair failing commands: `failure-loop-triage`.
- Repair CI: `ci-repair-loop`.
- Diagnose hard bugs or performance regressions: `diagnose`.
- Review branches, commits, diffs, PRs, or everything: `fresh-thread-code-reviewer`.
- Fix accepted review findings: `review-finding-fixer`.
- Improve architecture: `improve-codebase-architecture`.
- Stress-test plans and terminology: `grill-with-docs`.
- Step back and reassess direction: `zoom-out`.
- Update durable insights: `knowledge-graph-updater`.
- Maintain protected document hashes: `source-lock-operator`.
- Pick verification commands: `verification-command-picker`.
- Summarize subagent runs: `subagent-run-digest`.
- Prepare/resume handoffs: `context-compaction-handoff`, `thread-resume-brief`.
- Publish with add, commit, push: `acp-publisher`.
- Operate git, PRs, and CI: `git-pr-ci-operator`.

## Full-Auto Doctrine

When the user has granted dangerous/full-auto operation, spend autonomy on throughput, not sloppiness:

- Queue many tasks, but execute each task against a clear contract.
- Treat native Codex Goals as execution contracts, not as the canonical queue.
- Parallelize read-only exploration, independent workers, CI inspection, and review where safe.
- Never run two writers against the same files or branch without an explicit coordination plan.
- Prefer worker outputs that are easy to review: diffs, test results, result summaries, issue/task ids, and handoff notes.
- Escalate to HITL only for true ambiguity, external authority, missing credentials, destructive production actions, or conflicts between durable sources.

## Stop Conditions

Stop and report instead of continuing when:

- Durable sources disagree and no precedence rule resolves the conflict.
- The current task lacks acceptance criteria or verification and cannot be made AFK-ready from available context.
- Verification repeatedly fails and the failure class is unknown.
- The user asks for review-only, read-only, or no edits.
- Publishing, merging, deleting, or production-impacting action has not been authorized.
