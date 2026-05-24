# Architecture

`codex-supervisor` is a Python control plane with CLI, Codex Exec worker, MCP, plugin, and
repo-scaffold surfaces.

## Core Shape

```text
human planning session
  -> source-of-truth docs
  -> planning SQLite
  -> Codex local state reconciliation
  -> task compiler
  -> goal contract renderer
  -> story loop orchestrator
  -> queue
  -> worktree manager
  -> worker backend
  -> checks
  -> reviewer backend
  -> PR/merge/handoff
  -> insights and skill learning loop
```

## Architectural Boundaries

### Supervisor Core

Owns durable state:

- planning database;
- task queue;
- worker run records;
- source lock checks;
- project registry;
- artifact registry;
- knowledge graph update requests.

The core should be testable without launching Codex.

### Codex Local State Adapter

The supervisor may observe local Codex state as telemetry, but it must not treat Codex internal
databases as the canonical queue.

Read-only inputs:

- `~/.codex/state_5.sqlite`: threads, spawn edges, dynamic tools, and agent-job tables when
  present.
- `~/.codex/goals_1.sqlite`: per-thread goal rows when present.
- `~/.codex/logs_2.sqlite`: local execution and application logs for workflow analytics.
- `~/.codex/sqlite/codex-dev.db`: automation, automation run, and inbox tables when present.

The adapter can propose imports into `plans/planning.sqlite3`, link thread IDs and goal IDs as
evidence, detect stale work, summarize spawn trees, and surface repeated failures. It must not
write directly to these local Codex SQLite databases.

### Automation Bridge

Automations should be created, updated, or inspected through official Codex automation tooling, not
through raw SQLite writes. Automation runs are a scheduling surface for supervisor work such as
queue reconciliation, CI monitoring, project health checks, and thread wakeups.

### Goal Contract Renderer

Goal Contracts turn a supervisor task into a thread- or worker-scoped completion contract. They
include the objective, source context, in-scope and out-of-scope boundaries, verification surface,
stop condition, blocked condition, iteration policy, and record-update expectations.

Native Codex Goals may be used as an execution aid when available, but they are not the canonical
queue. The renderer should derive Goal Contracts from planning SQLite and source-of-truth docs, then
reconcile observed goal state back into planning SQLite as telemetry.

Worker launch code must verify the Codex version, pass the intended `CODEX_HOME`, and confirm the
Goals feature is enabled before depending on `/goal`. Enabling Goals through
`${CODEX_HOME}/config.toml` or `codex features enable goals` is a setup mutation; use it only when
Goal Mode setup is explicitly in scope and writes to that Codex home are allowed. Otherwise render
the Goal Contract into the worker prompt and do not edit Codex config or internal goal databases.

### Story Loop Orchestrator

The Story Loop Orchestrator applies one-story discipline to queued AFK work:

- pick one highest-priority ready vertical slice;
- prepare one fresh-context worker in an isolated workspace and launch it through the configured
  backend;
- verify and review the result;
- record progress, artifacts, learnings, and follow-up tasks;
- repeat only when another ready slice exists and policy allows it.

The story loop is a policy layer over the supervisor's queue. It should not replace planning SQLite
with `prd.json` or `progress.txt`, though it can import Ralph-inspired patterns.

### Worker Backends

Backends execute one task in one isolated context.

Backend families:

- `CodexExecBackend`: primary production backend using `codex exec --json --output-schema`.
- `ShellBackend`: deterministic checks and maintenance scripts.
- `ClawCodeBackend`: optional local-model/reference backend inspired by `HarnessLab/claw-code-agent`;
  keep it generic and do not copy source while upstream licensing is unclear.
- `SandcastleBackend`: optional TypeScript orchestration bridge if `mattpocock/sandcastle` is adopted.

### Project Adapters

Adapters translate each project into the supervisor's contracts.

Examples:

- `NlpStockPredictionAdapter`: reads tracked planning SQLite through typed helpers.
- `ObserveSafetyAdapter`: reads active markdown plans and runs plan validation commands.
- `CodexSubagentTestingAdapter`: understands harness configs, prompts, and run outputs.
- `TechResumeAdapter`: understands `insights/` wiki files and confidence labels.
- `GenericRepoAdapter`: uses `AGENTS.md`, `PLANS.md`, checks, and optional `TASKS.json`.

### MCP Server

The MCP server should expose supervisor capabilities to Codex and other harnesses:

- list projects;
- inspect plans;
- enqueue tasks;
- launch workers;
- read worker status;
- run reviewers;
- link artifacts;
- propose skill updates;
- read insights.

MCP is an interface, not the core.

### Codex Plugin

A plugin can package:

- the supervisor MCP server;
- supervisor-specific skills;
- default tool policy;
- project bootstrap templates.

## Context-Limit Strategy

The supervisor must not rely on a single long conversation. Each worker is a fresh-context run whose
prompt contains only:

- task contract;
- relevant source-of-truth pointers;
- acceptance criteria;
- constraints;
- allowed files/scope;
- verification commands;
- required result schema.

Durable continuity lives in SQLite, docs, artifacts, and insights.
