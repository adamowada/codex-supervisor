---
name: improve-codebase-architecture
description: Find deepening opportunities in a codebase, informed by configured domain docs, locked source-of-truth documents, planning records, and ADRs. Use when the user wants to improve architecture, find refactoring opportunities, consolidate tightly-coupled modules, improve testability, or make a codebase more AI-navigable.
---

# Improve Codebase Architecture

Surface architectural friction and propose **deepening opportunities**: refactors that turn shallow modules into deep ones. The aim is testability and AI-navigability.

## Glossary

Use these terms exactly in every suggestion. Consistent language is the point. Full definitions live in [LANGUAGE.md](LANGUAGE.md).

- **Module** - anything with an interface and an implementation.
- **Interface** - everything a caller must know to use the module: types, invariants, error modes, ordering, config.
- **Implementation** - the code inside.
- **Depth** - leverage at the interface: a lot of behavior behind a small interface.
- **Seam** - where an interface lives; a place behavior can be altered without editing in place.
- **Adapter** - a concrete thing satisfying an interface at a seam.
- **Leverage** - what callers get from depth.
- **Locality** - what maintainers get from depth: change, bugs, and knowledge concentrated in one place.

Key principles:

- **Deletion test**: imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across callers, it was earning its keep.
- **The interface is the test surface.**
- **One adapter = hypothetical seam. Two adapters = real seam.**

This skill is informed by the project's domain model. Domain language gives names to good seams; decision records identify choices the skill should not re-litigate.

## Process

### 1. Explore

Read the repo's configured source-of-truth docs first. For `codex-supervisor`, read the protected top-level docs, `insights/`, and planning SQLite records relevant to the review. For spawned projects, read `docs/agents/source-of-truth.md`, `docs/agents/domain.md`, `CONTEXT.md`, `CONTEXT-MAP.md`, and ADRs when present; if those lightweight docs are absent, fall back to the spawned-project top-level scaffold (`README.md`, `AGENTS.md`, `PLANS.md`, `ARCHITECTURE.md`, `CONTRACTS.md`, `SOP.md`, and `HANDOFF.md`).

Then walk the codebase. Spawn read-only Codex explorer subagents when the host exposes subagent
tools; otherwise explore locally or prepare self-contained read-only prompts. Do not follow rigid
heuristics. Explore organically and note where you experience friction:

- Where does understanding one concept require bouncing between many small modules?
- Where are modules **shallow**, with an interface nearly as complex as the implementation?
- Where have pure functions been extracted just for testability, but the real bugs hide in how they are called?
- Where do tightly-coupled modules leak across their seams?
- Which parts of the codebase are untested, or hard to test through their current interface?

Apply the deletion test to anything you suspect is shallow. Would deleting it concentrate complexity, or just move it? "Concentrates" is the signal.

### 2. Present Candidates

Prefer a concise Markdown summary unless the user asks for a visual report or the architecture is easier to compare visually.

For `codex-supervisor` and spawned projects, write generated reports under `artifacts/architecture-reviews/` so they stay ignored by git. If the repo has no ignored artifact path, use the OS temp directory and tell the user the absolute path.

If the current turn is read-only, review-only, audit-only, no-edits, or no-mutation, do not write
generated reports or update durable knowledge. Return the ranked candidates in chat and include the
proposed report path or knowledge-graph updates as follow-up actions.

When creating HTML, use [HTML-REPORT.md](HTML-REPORT.md). Prefer static local CSS and inline diagrams when the report must work offline. CDN-based Tailwind or Mermaid is acceptable only when network access is allowed and the report notes that dependency.

For each candidate, include:

- **Files/modules** - which modules are involved.
- **Problem** - why the current architecture is causing friction.
- **Solution** - plain English description of what would change.
- **Benefits** - explained in terms of locality, leverage, and tests.
- **Before / after diagram** - when visual comparison helps.
- **Recommendation strength** - `Strong`, `Worth exploring`, or `Speculative`.

End with a **Top recommendation**: which candidate to tackle first and why.

Use project domain vocabulary plus [LANGUAGE.md](LANGUAGE.md) vocabulary. If a domain glossary defines "Order," talk about "the Order intake module," not a generic handler name.

**Decision conflicts:** if a candidate contradicts an existing decision record, surface it only when the friction is real enough to warrant revisiting that decision. Mark it clearly.

Do not propose interfaces yet in interactive mode. After candidates are presented, ask the user:
"Which of these would you like to explore?" In approved AFK or dangerous full-auto mode, choose the
top recommendation only when the source-of-truth docs and planning task make the priority clear;
otherwise return the ranked candidates as HITL follow-up tasks.

### 3. Grilling Loop

Once the user picks a candidate, run a grilling conversation. Walk the design tree with them: constraints, dependencies, the shape of the deepened module, what sits behind the seam, and which tests survive.

Side effects happen only in configured durable sources:

- **New domain term?** Update the configured glossary source, or use `knowledge-graph-updater` for `codex-supervisor` insights.
- **Fuzzy term sharpened?** Update the same durable source immediately if the session permits edits.
- **User rejects the candidate with a load-bearing reason?** Offer to record the decision where the repo keeps decisions. Use [ADR-FORMAT.md](../grill-with-docs/ADR-FORMAT.md) only when ADRs are configured.
- **Want alternative interfaces for the deepened module?** Use [INTERFACE-DESIGN.md](INTERFACE-DESIGN.md).
