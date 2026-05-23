---
name: setup-agent-docs
description: Set up Codex-first AGENTS.md and docs/agents context for Codex-supervisor projects. Use before running imported engineering skills such as grill-with-docs, to-issues, triage, diagnose, tdd, improve-codebase-architecture, or zoom-out in a new repo, or when a repo lacks issue-tracker, triage-label, domain, or source-of-truth docs.
---

# Setup Agent Docs

Scaffold the repo-local context that small engineering skills consume. Keep it Codex-first; do not create tool-specific files for other coding agents unless the user explicitly asks.

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

Confirm one decision at a time unless the repo already documents it:

1. **Issue tracker**: GitHub connector, local markdown, planning SQLite, or other.
2. **Triage labels**: map `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`.
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

For projects spawned by `codex-supervisor`, include planning SQLite, source locks, AFK/HITL task contracts, worktree isolation, verification commands, and handoff artifacts in the docs. Prefer GitHub connector workflows over `gh` CLI when connector tools are available.

When protected docs are changed, run the repo's source-lock process and update the stored hashes intentionally.
