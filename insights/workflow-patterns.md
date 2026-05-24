# Workflow Patterns

## Fresh Context Over Long Context

Confidence: confirmed from private local telemetry and cross-project source review; public evidence
is redacted aggregate method.

Long Codex sessions eventually degrade. The supervisor should turn durable state into task prompts
and launch fresh workers instead of pushing one conversation indefinitely.

## Vertical Slices Over Horizontal Layers

Confidence: confirmed.

Matt Pocock's `to-issues` and `tdd` skills both push toward thin end-to-end slices. The supervisor
should compile plans into independently verifiable vertical tasks, not "build all models, then all
APIs, then all UI."

## Source Locks For Stable Doctrine

Confidence: confirmed.

`codex-subagent-testing` uses SHA-256 protected files to prevent casual drift in top-level source of
truth. `codex-supervisor` adopts that pattern for stable docs.

## SQLite For Operational Planning

Confidence: confirmed.

`nlp-stock-prediction` shows that tracked SQLite planning state gives Codex a queryable, durable
coordination substrate while leaving human-facing doctrine in markdown.

## Insights As Durable Learning Memory

Confidence: inferred.

`tech-resume` demonstrates a useful markdown insight wiki. `codex-supervisor` extends the pattern to
workflow learning and skill evolution.

## Goal Contracts Over Open-Ended Execution

Confidence: confirmed.

Codex Goals make long-running work safer when the objective, validation surface, constraints,
boundaries, and stop condition are explicit. `codex-supervisor` should derive Goal Contracts from
planning SQLite tasks and source-of-truth docs, then treat native Codex Goal state as execution
telemetry rather than project authority.

## One Story Per Fresh Context

Confidence: inferred.

Ralph demonstrates that autonomous coding loops become easier to control when each iteration starts
with fresh context, selects one incomplete story, runs checks, records progress, and stops or moves
to the next story. `codex-supervisor` should apply this as Story Loop policy over `AFK` supervisor
tasks.

## Current Queue Over Active Only

Confidence: confirmed.

Fresh threads need to see blocked successor plans as part of the current queue. Use
`story-loop-status --json`, `plan-summary --current-queue`, and
`task-list --current-queue-plans-only` for orientation; reserve active-only views for deliberately
narrow audits.
