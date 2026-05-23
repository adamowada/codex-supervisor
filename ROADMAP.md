# Roadmap

## Stage 0: Bootstrap Repository

Create the repo, source-of-truth documents, ignored source clones, Python skeleton, planning
database, source locks, and clean handoff.

Status: in progress.

## Stage 1: Planning SQLite Core

Implement and test:

- schema initialization;
- typed records;
- plan CRUD helpers;
- milestone, acceptance, decision, progress, artifact, commit helpers;
- task and worker-run tables.

## Stage 2: Source Locks

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

## Stage 5: Codex Exec Backend

Launch fresh-context workers:

- create worktrees;
- render prompts;
- call `codex exec --json --output-schema`;
- capture JSONL, stderr, stdout, timing, diffs, and final result;
- write worker-run records.

## Stage 6: Review And Verification Loop

Run:

- deterministic checks;
- automated code review;
- repair loops;
- final summary and handoff.

## Stage 7: Insights And Skill Learning

Implement the durable learning loop:

- classify failures;
- update `insights/`;
- propose skill changes;
- test skills against golden tasks;
- promote approved skills.

## Stage 8: MCP Server And Codex Plugin

Expose supervisor operations through MCP and package project skills through a Codex plugin.

## Stage 9: GitHub And CI/CD Integration

Implement:

- branch and PR creation;
- CI status monitoring;
- CI repair loop;
- issue comments;
- release/handoff summaries.
