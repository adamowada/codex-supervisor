# Decisions

## D-0001: Compact State Model

Decision: The durable model is `TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision`.

Rationale: A single transition model keeps the substrate small enough to reason about, recover, and
test.

## D-0002: Planning Schema

Decision: Planning SQLite stores `meta`, `plans`, `tasks`, `attempts`, `evidence_bundles`,
`acceptance_decisions`, and `decisions`.

Rationale: These tables answer the current operational questions directly while leaving infrequent
details in structured JSON or artifact records.

## D-0003: Assurance Levels Are Policy

Decision: `low`, `medium`, and `high` are assurance levels.

Rationale: Assurance changes evidence and acceptance requirements while the core model stays stable.

## D-0004: Skills Are Guidance

Decision: Repo-local and packaged skills are bounded operating guidance, not runtime product
surface.

Rationale: Skills help agents preserve the role split, but they must stay thin and guarded so they
do not become hidden product modes.

## D-0005: Interfaces Follow The Core

Decision: CLI, MCP, plugin, automation, GitHub, and worker surfaces are adapters over the durable
model.

Rationale: Interfaces should make the substrate easier to use while preserving the same task,
attempt, evidence, acceptance, and recovery semantics.

## D-0006: CI Guards The Active Contract

Decision: CI runs the focused verification gate.

Rationale: The gate should match the current architecture and grow with rebuilt behavior.

## D-0007: Design Notes Capture Lessons

Decision: `insights/` records durable lessons that guide future design.

Rationale: These notes should help future work preserve the small substrate contract.

## D-0008: Work Semantics Stay In Task Intent

Decision: The supervisor uses generic task creation and process attempts instead of deterministic
engineering job types.

Rationale: Goal Mode can decide what work means, while Supervisor keeps durable state, evidence,
acceptance, and auditability deterministic.

## D-0009: Product Provenance Is A Target Workspace Contract

Decision: Product artifact provenance is owned by target workspace inspection and includes declared
artifacts plus git-discovered changed product paths recorded by `attempt-run`.

Rationale: Broad worker prompts can create unknown files. One provenance module gives `attempt-run`
and ACP the same product path semantics without adding job types, modes, commands, or tables.

## D-0010: Supervisor Is The Durable Goal Mode Substrate

Decision: `codex-supervisor` is the durable evidence substrate for Codex Goal Mode, not an
autonomous orchestration layer.

Rationale: Goal Mode should own strategy, sequencing, recovery, and final judgment. Supervisor
should remember, launch, verify, record evidence, enforce provenance, and expose compact recovery
state.

## D-0011: Launch Packets Stay Flexible First

Decision: Goal Mode launch packets start as free-form artifacts that Supervisor copies, hashes, and
references.

Rationale: The packet is where Goal Mode writes worker context. A strict schema should appear only
after repeated access patterns prove it will reduce more complexity than it adds.
