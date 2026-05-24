# Decisions

This file records bootstrap decisions. Ongoing decisions should be written to
`plans/planning.sqlite3` first and summarized here only when they become stable project doctrine.

## D-0001: Python-First Supervisor Core

Decision: The supervisor core is primarily Python.

Rationale: Adam works heavily in Python, wants cross-platform development, and needs first-class
SQLite, filesystem, subprocess, and testing support.

## D-0002: Codex Exec Is The Primary Worker Primitive

Decision: Fresh-context production workers should use `codex exec --json --output-schema` once the
ROADMAP Stage 6 backend is implemented. Until then, `worker_backend=codex_exec` rows are planned
backend labels and must not be treated as proof that `codex-supervisor` can launch workers itself.

Rationale: `codex exec` is designed for automation, CI, scheduled jobs, explicit sandbox settings,
JSONL event capture, and schema-constrained output. Keeping it as the intended primitive lets Stage
6 design toward the right target without overstating current bootstrap capability.

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

Decision: One-story loops are adopted as worker execution policy: one fresh-context worker
implements one ready vertical slice, verifies it, records progress, and then stops or moves to the
next ready slice.

Rationale: The Ralph loop demonstrates a practical way to keep autonomous coding bounded: small
stories, fresh context, durable progress, quality checks, and a clear stop condition. In
`codex-supervisor`, planning SQLite replaces Ralph's `prd.json`, and insights/progress records
replace `progress.txt`.

## D-0010: Verify Codex Goal Availability Before Worker Launch

Decision: Codex-supervisor must treat native Codex Goals as an optional execution surface that
requires explicit availability checks. Worker launches should record resolved Codex executable,
`codex --version`, intended `CODEX_HOME`, config path, feature state, whether the selected worker
backend exposes an official noninteractive native-goal path, and the prompt-rendered fallback
decision before using native Goals. If `/goal` is unavailable on a Goals-capable build, set
`[features] goals = true` in `${CODEX_HOME}/config.toml` or run `codex features enable goals` only
when Goal Mode setup is explicitly in scope and writes to that Codex home are allowed. In read-only,
review-only, or already-synced worker contexts, use the prompt-rendered Goal Contract fallback
instead. Restart or start a fresh Codex session only if the running process does not pick up an
allowed config change.

Rationale: Goal mode can be disabled by feature configuration, and a worker launched with the wrong
Codex home may load a sandbox config where Goals or authentication are unavailable. Official
documentation sources for this preflight are indexed in `insights/source-index.md`.

Consequence: Goal Contracts remain useful even when native Goals are unavailable; workers can still
receive the contract in their prompt, while native Goal state is reconciled only when present.

## D-0011: Reuse MIT-Licensed Matt Pocock Skills With Attribution

Decision: `codex-supervisor` may copy and adapt selected MIT-licensed material from
`sources/mattpocock-skills` into repo-local skills when the result is aligned with Adam's workflow,
small-skill doctrine, and this repository's authority matrix. Copied or adapted skill material must
stay attributed through `ATTRIBUTIONS.md` and `.agents/skills/NOTICE.md`.

Rationale: The upstream skills encode high-quality, composable agent workflows that directly match
this project's desired operating style: small skill over giant methodology, domain glossary over
repeated explanation, vertical slice over horizontal layer task, handoff artifact over bloated
session, sandbox/worktree over risky direct edits, and eval loop over "seems better." MIT licensing
allows adaptation with attribution, while repo-local editing lets Adam's personal workflow override
generic upstream defaults.

Consequence: Direct or adapted skill material belongs in `.agents/skills/`, not in ignored
`sources/` clones. Future copying from any source still requires license review, attribution, and a
stable decision or planning record before publication.
