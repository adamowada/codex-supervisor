# Decisions

This file records bootstrap decisions. Ongoing decisions should be written to
`plans/planning.sqlite3` first and summarized here only when they become stable project doctrine.

## D-0001: Python-First Supervisor Core

Decision: The supervisor core is primarily Python.

Rationale: Adam works heavily in Python, wants cross-platform development, and needs first-class
SQLite, filesystem, subprocess, and testing support.

## D-0002: Codex Exec Is The Primary Worker Primitive

Decision: Fresh-context production workers should use `codex exec --json --output-schema`.

Rationale: `codex exec` is designed for automation, CI, scheduled jobs, explicit sandbox settings,
JSONL event capture, and schema-constrained output.

## D-0003: MCP Is An Interface, Not The Core

Decision: The supervisor may expose an MCP server, but MCP will not own orchestration state.

Rationale: The queue, planning DB, worktrees, and artifacts must be usable from CLI, tests, CI, and
MCP without coupling the system to one harness.

## D-0004: Planning State Lives In SQLite

Decision: Operational plans live in tracked SQLite at `plans/planning.sqlite3`.

Rationale: Structured rows are easier for Codex to query, update, validate, and hand off than long
markdown plans.

## D-0005: Insights Are Markdown

Decision: Durable workflow learning lives in `insights/` as markdown with provenance and confidence
labels.

Rationale: Insights should be readable by humans and agents, diffable in git, and suitable for
promotion into skills.

## D-0006: Source Clones Are Ignored

Decision: OSS inspiration sources are cloned under `sources/` but ignored by git.

Rationale: They are local reference material, not vendored project source.

## D-0007: Codex Local State Is Telemetry

Decision: Local Codex SQLite databases under `~/.codex` are read-only telemetry and reconciliation
inputs, not the canonical supervisor queue.

Rationale: Codex internal databases expose useful observations about threads, spawn graphs, goals,
logs, agent jobs, inbox items, and automation runs, but their schema and lifecycle belong to Codex.
`codex-supervisor` needs stable, project-owned state for tests, CI, handoffs, and cross-tool use.
Therefore, canonical operational state remains in `plans/planning.sqlite3`, while Codex automations
are managed through official automation tooling.

## D-0008: Goal Contracts Guide Execution

Decision: Native Codex Goals and supervisor Goal Contracts are execution contracts for threads and
workers, not the canonical project queue.

Rationale: Codex Goals provide a durable objective, validation loop, lifecycle controls, and stop
conditions for a running thread. `codex-supervisor` still needs project-owned planning state that is
testable, reviewable, and independent of Codex internal schemas. Therefore, Goal Contracts are
derived from planning SQLite tasks and reconciled back as evidence.

## D-0009: Story Loops Execute One Vertical Slice

Decision: Ralph-style story loops are adopted as worker execution policy: one fresh-context worker
implements one ready vertical slice, verifies it, records progress, and then stops or moves to the
next ready slice.

Rationale: The Ralph loop demonstrates a practical way to keep autonomous coding bounded: small
stories, fresh context, durable progress, quality checks, and a clear stop condition. In
`codex-supervisor`, planning SQLite replaces Ralph's `prd.json`, and insights/progress records
replace `progress.txt`.
