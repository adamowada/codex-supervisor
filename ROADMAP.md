# Roadmap

Roadmap status is descriptive, not the work selector. Fresh threads must use
`story-loop-status`, `task-current`, and `plans/planning.sqlite3` for current queue state.

## Stage 0: Bootstrap Repository

Create the repo, source-of-truth documents, ignored source clones, Python skeleton, planning
database, source locks, and clean handoff.

Status: completed and published. The canonical current state lives in `plans/planning.sqlite3`.
Bootstrap publication was ACP'd to `origin/main`, and the reproducible clean-clone gates now pass.

## Stage 1: Planning SQLite Core

Implement and test:

- schema initialization;
- typed records;
- plan CRUD helpers;
- milestone, acceptance, decision, progress, artifact, commit helpers;
- task and worker-run tables.

Status: completed. Typed helpers and CLI commands can inspect and mutate plans, decisions,
progress, artifact links, commit links, supervisor tasks, worker runs, and lifecycle status.

## Stage 2: Source Locks

Status: partial/completed locally for the bootstrap guard. The protected manifest, hash check
command, git-index tracking check, and local verification integration are present. A dedicated
intentional re-lock CLI remains future work; for now, hashes are updated through
`scripts/print_protected_hashes.py` and `scripts/check_protected_files.py`.

Implement:

- protected document manifest;
- hash check command;
- intentional re-lock command;
- CI/local command integration.

## Stage 3: Project Registry And Adapters

Implement:

- project discovery under configurable roots;
- generic adapter;
- `nlp-stock-prediction` adapter;
- `observe-safety-monorepo` adapter;
- `codex-subagent-testing` adapter;
- `tech-resume` adapter.

## Stage 4: Task Compiler

Compile plans into vertical-slice tasks:

- classify `AFK` vs `HITL`;
- infer dependencies;
- attach acceptance criteria and checks;
- produce worker prompts.

## Stage 5: Goal Contracts And Story Loop

Status: completed locally. The current implementation includes typed Goal Contract rendering,
Story Loop status/progress CLI helpers, source-authority metadata, native Goal Mode preflight
guidance, HITL-aware loop status, dependency resolution for completed blockers, and tests for stop
conditions, blocked conditions, Story Loop states, atomic progress/artifact recording, and
source-of-truth precedence metadata.

Implemented:

- Goal Contract data model and renderer;
- Goal Contract prompt sections for native Codex Goals and worker prompts;
- Story Loop policy for one ready AFK task per iteration;
- queue inspection helpers for next-ready task selection;
- progress and artifact recording for story iterations;
- tests for stop conditions, blocked conditions, and source-of-truth precedence.

## Stage 6: Codex Exec Backend

Do not start this stage from roadmap order alone. Use `story-loop-status` and the current-queue
planning state first.

Status: active ready successor plan `plan-stage6-codex-exec-backend` after the bootstrap ACP
publication checkpoint. The current task is the design/contract slice
`task-stage6-codex-exec-backend-design`.

Launch fresh-context workers:

- create worktrees;
- render prompts;
- call `codex exec --json --output-schema`;
- capture JSONL, stderr, stdout, timing, diffs, and final result;
- write worker-run records.

## Stage 7: Review And Verification Loop

Run:

- deterministic checks;
- automated code review;
- repair loops;
- final summary and handoff.

## Stage 8: Insights And Skill Learning

Implement the durable learning loop:

- classify failures;
- update `insights/`;
- propose skill changes;
- test skills against golden tasks;
- promote approved skills.

## Stage 9: Codex Local State Adapter And Automation Bridge

Implement:

- read-only adapters for local Codex SQLite databases;
- thread, spawn-tree, goal, automation, inbox, and log summaries;
- dry-run reconciliation into planning SQLite;
- provenance records for imported observations;
- stale-thread, orphaned-handoff, and repeated-failure detection;
- official Codex automation creation/update flows for recurring supervisor jobs.

## Stage 10: MCP Server And Codex Plugin

Expose supervisor operations through MCP and package project skills through a Codex plugin.

## Stage 11: GitHub And CI/CD Integration

Implement:

- branch and PR creation;
- CI status monitoring;
- CI repair loop;
- issue comments;
- release/handoff summaries.
