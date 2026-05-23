# Architecture

`codex-supervisor` is a Python control plane with optional MCP and plugin surfaces.

## Core Shape

```text
human planning session
  -> source-of-truth docs
  -> planning SQLite
  -> task compiler
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

### Worker Backends

Backends execute one task in one isolated context.

Initial backends:

- `CodexExecBackend`: primary production backend using `codex exec --json --output-schema`.
- `ShellBackend`: deterministic checks and maintenance scripts.
- `ClawCodeBackend`: optional local-model/reference backend inspired by `HarnessLab/claw-code-agent`.
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
