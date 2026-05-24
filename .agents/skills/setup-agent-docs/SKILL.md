---
name: setup-agent-docs
description: Set up lightweight Codex-first AGENTS.md and docs/agents context for imported engineering skills. Use when a repo lacks issue-tracker, triage-label, domain, or source-of-truth docs needed by small skills. Do not use as the full codex-supervisor spawned-project bootstrap.
---

# Setup Agent Docs

Scaffold the repo-local context that small engineering skills consume. Keep it Codex-first; do not create tool-specific files for other coding agents unless the user explicitly asks.

This is not the full spawned-project bootstrap contract. Projects spawned by `codex-supervisor`
still need the top-level source-of-truth set, planning SQLite, source locks, verification scripts,
insights graph, handoff artifacts, and project-specific SOP from `SOP.md` and `CONTRACTS.md`.

If the current user turn is read-only, readonly, review-only, audit-only, no-edits, or no-mutation
mode, do not create or edit docs. Return the proposed file list, contents outline, and source-lock
follow-up instead.

## Explore First

Read:

- `git remote -v`
- `AGENTS.md`
- `CONTEXT.md` and `CONTEXT-MAP.md`
- `docs/adr/`
- `docs/agents/`
- existing issue, planning, roadmap, or source-of-truth docs
- planning SQLite schema or records when present

## Decisions

Confirm one decision at a time in interactive mode unless the repo already documents it. In approved
AFK or dangerous full-auto mode, derive each decision from durable sources, record assumptions, and
classify unresolved choices as HITL blockers.

1. **Issue tracker**: GitHub connector, local markdown, planning SQLite, or other.
2. **Triage labels**: map category roles `bug` and `enhancement`, plus state roles
   `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`.
3. **Domain docs**: single `CONTEXT.md`, multi-context `CONTEXT-MAP.md`, or another glossary location.
4. **Source of truth**: which docs, databases, or issue trackers win when records disagree.
5. **Locking**: which source-of-truth docs require hash checks before completion.
6. **AFK policy**: which task types can run full-auto and which require HITL.

## Write

Update or create:

- `AGENTS.md` with an `## Agent skills` block.
- `docs/agents/issue-tracker.md`.
- `docs/agents/triage-labels.md`.
- `docs/agents/domain.md`.
- `docs/agents/source-of-truth.md`.

Use this skill directory's companion templates as starting points when they match the chosen policy:
`domain.md`, `issue-tracker-github.md`, `issue-tracker-local.md`, `triage-labels.md`, and
`source-of-truth.md`. Adapt names and authority rules to the target repo instead of copying stale
`codex-supervisor` examples verbatim.

For projects spawned by `codex-supervisor`, use `spawned-project-bootstrap` for the full scaffold.
This skill may supply only the lightweight issue-tracker, triage-label, domain, or source-of-truth
docs that the smaller engineering skills need. Prefer GitHub connector workflows over `gh` CLI when
connector tools are available.

When protected docs are changed, run the repo's source-lock process and update the stored hashes intentionally.

## Result Contract

Report the source-of-truth files created or updated, issue/queue system chosen, planning-state
location, assumptions, HITL blockers, verification commands, and follow-up source-lock work.
