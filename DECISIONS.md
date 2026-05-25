# Decisions

This file records bootstrap decisions. Ongoing decisions should be written to
`plans/planning.sqlite3` first and summarized here only when they become stable project doctrine.

## D-0001: Python-First Supervisor Core

Decision: The supervisor core is primarily Python.

Rationale: Adam works heavily in Python, wants cross-platform development, and needs first-class
SQLite, filesystem, subprocess, and testing support.

## D-0002: Codex Exec Is The Primary Worker Primitive

Decision: Fresh-context production workers use `codex exec --json --output-schema` as the primary
worker primitive. `worker_backend=codex_exec` identifies the selected backend family; execution
capability and worker-run evidence are proven by planning SQLite rows, DB-backed result records,
captured raw run evidence, and verification records.

Rationale: `codex exec` is designed for automation, CI, scheduled jobs, explicit sandbox settings,
JSONL event capture, and schema-constrained output. Making it the primary primitive keeps CLI, MCP,
plugin, and automation paths aligned around one worker contract.

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
repeated explanation, vertical slice over horizontal layer task, compact handoff over bloated
session, sandbox/worktree over risky direct edits, and eval loop over "seems better." MIT licensing
allows adaptation with attribution, while repo-local editing lets Adam's personal workflow override
generic upstream defaults.

Consequence: Direct or adapted skill material belongs in `.agents/skills/`, not in ignored
`sources/` clones. Copying from any source requires license review, attribution, and a stable
decision or planning record before publication.

## D-0012: Worker Completion Records Live Only In Planning SQLite

Decision: Worker completion/result records, imported legacy evidence, and operational history live
only in `plans/planning.sqlite3`. Worker JSON files are transient import sources, not durable
repo-local artifacts; `HANDOFF.md` is a compact current handoff snapshot, not a running log.

Rationale: The supervisor needs one canonical operational store that can be queried, validated,
migrated, and handed off without accumulating parallel markdown ledgers or JSON artifacts.
SQLite-backed records preserve raw payloads and provenance while keeping the public tree clean.

Consequence: `worker-results/` is ignored and rejected by hygiene checks. Completed worker runs must
link to `worker_result_records` and `worker_result_run_links`; source-of-truth docs and `insights/`
stay focused on doctrine and synthesized learning rather than completion logs.

## D-0013: V1 Hardening Uses Mainline Verified ACP Slices

Decision: V1 hardening work is performed directly on `main` and published by ACP after each
verified vertical slice. Release tags, release artifacts, and final release action still require a
separate explicit user instruction.

Rationale: Adam authorized mainline development for this hardening run and wants timely checkpoints
without branch or PR overhead, while keeping release as a distinct human boundary.

Consequence: Before pushing, compare remote `main` with local `HEAD`; if remote `main` moved, stop
for HITL direction instead of rebasing or merging automatically.

## D-0014: Live Codex Defaults To The User Codex Home

Decision: Live Codex worker and reviewer launches default to the user's normal Codex home, with an
optional `--codex-home` override for explicit isolation or alternate credentials.

Rationale: V1 must exercise the real authenticated Codex environment by default, while still giving
operators a way to choose another home when a run needs stricter control.

Consequence: Worker preflight records the resolved Codex executable, version, intended Codex home
policy, feature state, and fallback decision. Tracked docs and planning records must not persist
machine-specific absolute paths.

## D-0015: V1 Product Paths Must Be Real

Decision: Production code paths must not depend on fake, dummy, demo-only, or scaffold-only data or
behavior. Test fixtures remain allowed, and project scaffolding remains a real production
capability when it writes actual project files and initializes supervisor state.

Rationale: The v1 done condition is a live, operational supervisor whose documented capabilities
are implemented rather than simulated.

Consequence: Live review uses real Codex subagents or `codex exec` reviewer runs, mutating MCP tools
are enabled by default with an explicit opt-out, and project scaffolding must create files,
planning SQLite, git checks, source locks, and first task contracts.

## D-0016: Local Adapter Paths Stay Out Of Tracked State

Decision: Project adapters may target locally available repositories, but tracked markdown and
planning SQLite may store only safe project identifiers and repo-relative evidence, not local
absolute roots.

Rationale: Adapter development needs local projects, while public history must not expose
machine-specific paths.

Consequence: Use ignored local configuration or runtime inputs to map project ids to local roots.
Planning records can describe adapter policy, but not the user's private filesystem layout.

## D-0017: Worker Integration Conflicts Are Contract Decisions

Decision: This v1 hardening run does not use parallel writer workers. Future worktree integration
conflicts are supervisor-managed contract decisions: mechanical edit/delete conflicts can be
resolved during integration when task contracts are clear, while contradictory contracts require
HITL or repair before merging worker output.

Rationale: Avoiding parallel writers keeps this hardening pass focused, and the durable product
should treat conflicts as integration evidence rather than as an impossible state.

Consequence: Parallel read-only exploration remains safe, but production writer fanout needs an
explicit integration policy and evidence trail before it is used.

## D-0018: Skill Promotion Requires Evidence And Evaluation

Decision: A skill update requires a source-linked insight, the skill edit, a golden eval or focused
test, and passing relevant verification before ACP.

Rationale: Durable learning should move from evidence to insight to skill only when the change is
proven, not merely because a session noticed a pattern.

Consequence: If no insight is created or updated for a workflow lesson, there is normally no skill
promotion to publish for that lesson.
