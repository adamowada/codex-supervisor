---
name: codex-supervisor
description: Top-level orchestrator for explicit Codex-supervisor, agentic engineering factory, full-auto, multi-phase, worker-coordination, Story Loop, or project-supervision requests. For ordinary implementation, debugging, review, or docs work, route to the smallest child skill first.
---

# Codex Supervisor

Use this as the thin conductor for the project. It defines the top-level loop, routes to smaller skills, and enforces global invariants. Do not duplicate the detailed procedures of child skills.

## Global Invariants

- Use an authority matrix, not a single global source order:
  - locked source-of-truth docs win for durable doctrine, architecture, contracts, testing policy,
    roadmap intent, public repo policy, and stable operating rules;
  - `plans/planning.sqlite3` wins for active and blocked current-queue plans, current task, task
    status, worker runs, progress events, handoff order, and operational queue state;
  - GitHub issues/PRs win for remote tracker state only after reconciliation into planning SQLite;
  - `HANDOFF.md` is a mutable snapshot and must yield to the live database for execution order;
  - chat history is context, not durable authority.
- Durable state beats conversation memory. Do not let chat be the only record of plans, decisions, tasks, verification, or handoff state.
- Prefer vertical slices that produce demoable, testable behavior.
- Prefer AFK-ready task contracts with Goal Contracts, but mark HITL honestly when judgment, secrets, external access, design approval, or production action is required.
- Use worktrees or sandboxed workers for risky, broad, or full-auto implementation.
- Keep worker context small and self-contained.
- Verify with the narrowest meaningful check first, then broaden when the change touches shared behavior.
- Review before merging or publishing production-impacting work.
- Update durable knowledge when a lesson should survive the thread.
- Create a handoff before context compaction, thread transfer, or long unattended work.

## Operating Modes

- `read_only`: inspect and report only; no file, database, tracker, or git mutations.
- `interactive`: ask before ambiguous or irreversible steps.
- `approved_afk`: continue through queued work after the user approves the contract.
- `dangerous_full_auto`: assume permission prompts are not the safety boundary; rely on scope,
  isolation, verification, review, and audit trails.

Latest user instruction wins. Durable project policy can satisfy repeated approval gates, but
read-only and review-only requests always override full-auto behavior for that turn.

## Operating Loop

1. **Orient.** Read the minimum stable bootstrap set first: this skill, `README.md`, `AGENTS.md`,
   `PLANS.md`, `insights/README.md`, current git state, and live active or blocked current-queue
   planning SQLite records. Read `HANDOFF.md` only after the live queue names the current state or
   task.
2. **Select phase.** Decide whether the project needs planning, task shaping, implementation, review, failure repair, architecture work, knowledge update, handoff, or publishing.
3. **Route.** Use `skill-router` and then invoke the smallest relevant child skill.
4. **Contract.** Ensure the current task has goal, scope, out-of-scope, acceptance criteria, verification commands, allowed paths, blockers, HITL/AFK classification, and a Goal Contract.
5. **Isolate.** Use a worktree or fresh-context worker when full-auto work could collide with active user edits or span multiple tasks.
6. **Execute.** Implement one vertical slice or repair loop at a time. Use story-loop discipline for queued AFK work. Keep unrelated refactors out unless the selected skill says they are part of the task.
7. **Verify.** Run targeted checks, then broader checks as risk demands. Record failures through the failure skills instead of hand-waving.
8. **Review.** Use fresh-context review for branches, commits, diffs, or whole-repo reviews. For
   `review_required=true` full-AFK work, create a separate AFK review task by default and promote
   clean results through typed review promotion. Escalate to HITL only when the review result needs
   human authority, product judgment, credentials, or risk acceptance. Fix findings only after user
   or policy approval.
9. **Record.** Update planning SQLite for live state, `HANDOFF.md` for mutable resume context,
   `insights/` for durable learning, issue trackers for reconciled remote state, and protected
   source-of-truth docs only when stable doctrine, contracts, architecture, testing policy, or
   public repo policy changes. Never write task progress, stage progress, or queue status into
   protected docs.
10. **Continue or hand off.** Pick the next ready task, publish if explicitly requested, or create a compact handoff for a fresh thread/worker.

## Fresh Thread Bootstrap Contract

When starting or resuming `codex-supervisor` in a fresh Codex thread:

1. Read this skill and enough of `AGENTS.md` to identify the bootstrap commands.
2. Run `git status --short --branch`.
3. Run `git rev-parse --short HEAD`.
4. If writes and dependency setup are allowed, run `uv python install 3.14`,
   `uv sync --dev`, and `uv run python --version`. In read-only mode, skip setup and use the
   existing environment.
5. Read the minimum stable orientation set: `README.md`, `AGENTS.md`, `PLANS.md`, and
   `insights/README.md`. Do not read mutable `HANDOFF.md` before the live queue unless the user
   explicitly asks for handoff prose first.
6. Run `uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json` under the same
   environment condition.
7. Run `uv run --no-sync python -B -m codex_supervisor.cli plan-summary --current-queue` only when
   the environment is already synced or dependency setup is allowed.
8. Run `uv run --no-sync python -B -m codex_supervisor.cli task-current --after-story-loop-status
   --json` only to select an executable AFK task after step 6 has established queue state.
   In strict read-only mode with no synced environment, use existing command output, Git state, or
   the read-only SQLite fallback below and report that typed CLI orientation needs dependency setup.
9. Treat top-level `queue_state` from `story-loop-status --json` as the queue state machine:
   `ready` means continue with the current AFK task, `running` means report the claimed worker task
   and wait/monitor, `hitl` means report the human checkpoint and pause, `blocked` means report
   blockers, and `completed` or `empty` means no executable AFK task remains. The default
   `story-loop-status` view includes active and blocked current-queue plans; use `--all` for
   completed, abandoned, or superseded history.
10. If `story-loop-status` returns `queue_state: "hitl"`, run
   `uv run --no-sync python -B -m codex_supervisor.cli task-show <current_task_id> --json` and
   report that task as the current human checkpoint.
11. After the queue state and current task are known, read `HANDOFF.md` as a mutable snapshot, then
   read only the source-of-truth docs and insight files relevant to that task. Use
   `insights/README.md` as the index for insight files.
12. Treat `plans/planning.sqlite3` as the execution authority. If it disagrees with `HANDOFF.md`,
   follow the database and update the handoff after inspection when writes are allowed; in read-only
   mode, propose the handoff update instead.
13. Confirm the selected task's allowed paths, acceptance criteria, verification commands, and
   worker backend assumptions before editing.
14. Use `uv run python -B scripts/check_protected_files.py` after source-of-truth edits or before
   publication. During an active HITL ACP checkpoint, this may intentionally fail until new
   protected files are tracked.
15. Use `uv run python -B scripts/verify.py` as the final local gate unless the task explicitly limits
   verification to a narrower command. Treat failures as evidence to triage, not as proof that
   `HANDOFF.md` is the queue authority.

Strict read-only SQLite fallback:

```sh
python -B -c "import json, sqlite3; c=sqlite3.connect('file:plans/planning.sqlite3?mode=ro', uri=True); c.row_factory=sqlite3.Row; rows=c.execute(\"\"\"SELECT p.plan_id,p.status AS plan_status,p.priority,st.task_id,st.title,st.status AS task_status,st.task_type,st.worker_backend,st.blocked_by_json FROM supervisor_tasks st JOIN plans p ON p.plan_id=st.plan_id WHERE p.status IN ('active','blocked') ORDER BY p.status='active' DESC,p.priority DESC,st.status='ready' DESC,st.updated_at DESC,st.task_id\"\"\").fetchall(); print(json.dumps([dict(r) for r in rows], indent=2)); c.close()"
```

## Child Skill Dispatch

`skill-router` is the single authoritative child-skill route map. After applying this skill's global
invariants, fresh-thread bootstrap checks, and stop conditions, load `skill-router` to choose the
smallest child skill that fits the task.

Do not duplicate the child-skill table here. Repeating the route map creates drift between the
top-level doctrine and the executable routing inventory.

## Full-Auto Doctrine

When the user has granted dangerous/full-auto operation, spend autonomy on throughput, not sloppiness:

- Queue many tasks, but execute each task against a clear contract.
- Treat native Codex Goals as execution contracts, not as the canonical queue.
- Treat native Codex Goals as allowed only when linked to a supervisor task and rendered Goal
  Contract.
- For full-AFK work, run the callable runtime preflight first. If it reports skill-only mode,
  current-thread worker fallback, missing supervisor backend, memory database fallback, degraded
  evidence, or unapproved setup mutations, record a blocker/HITL decision instead of implementing.
- Desktop plugin full-AFK work must be authorized by a live MCP `runtime_preflight` canary in the
  current Desktop session. CLI preflight can diagnose package/cache/startup problems after MCP
  failure, but it cannot approve plugin full-AFK readiness or override a successful live MCP canary.
- `tool_search` is not MCP inventory. Use it to discover callable tools, but let the live MCP
  `runtime_preflight` handler inventory the server tool surface before deciding required tools are
  missing. For Desktop plugin canary discovery, search for `canary` or
  `Desktop full-AFK canary fail-closed execution-mode ledger`; name-only queries such as
  `runtime_preflight` are not reliable. Do not pass `tool_search` results as authoritative
  `mcp_tools`, and do not pass `mcp_startup_diagnostic` merely because discovery went through
  `tool_search`.
- Plugin full-AFK project bootstrap always uses the supervisor-managed scaffold tier.
- After `spawned-project-apply`, treat the generated scaffold task as already completed by the
  deterministic apply step and the bootstrap plan as complete. Seed or compile the user's concrete
  implementation request as a new project-local plan/task before calling `story-loop-run-once`; do
  not launch a Codex worker merely to redo scaffold creation.
- Post-worker browser smoke is evidence even when it passes: record `browser_smoke_passed` or
  `browser_smoke_failed` progress, link screenshots or logs when present, and refresh `HANDOFF.md`
  before declaring completion. Manual promotion bookkeeping may complete only with
  `promotion_completed` progress naming the promotion task and source task. Prefer OS-neutral
  file-list copy/promotion steps over shell-specific patch pipelines when planning mutations are
  already present in the main checkout. Run verification as separate command invocations instead of
  relying on shell-specific chained command lines. For JSON-heavy queue mutations, prefer repo-local
  input files, stdin, or typed `--*-json-file` surfaces when available instead of nested
  shell-quoted JSON.
- Full-AFK review-required work uses a separate AFK review task by default; use HITL only for
  findings or decisions that require human authority.
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

## Result Contract

Report the selected plan/task IDs, mode, route choice, changed files, planning rows updated, commands
run, verification evidence, residual risks, and the next AFK/HITL action.
