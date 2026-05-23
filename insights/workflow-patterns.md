# Workflow Patterns

## Fresh Context Over Long Context

Confidence: confirmed.

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
