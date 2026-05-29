---
name: reduce-codebase-complexity
description: Ruthlessly evaluate a codebase for simplification opportunities. Use when the user wants to reduce state space, remove legacy preservation, shrink public surfaces, collapse mode-like axes, simplify control planes, re-layer architecture, or identify high-leverage deletion and consolidation candidates.
---

# Reduce Codebase Complexity

Surface **reduction candidates**: changes that make a codebase smaller, easier to test, and easier
to reason about by removing unnecessary state space. The aim is fewer axes, fewer paths, fewer
surfaces, and clearer layers.

## Glossary

Use these terms consistently. Full definitions live in [LANGUAGE.md](LANGUAGE.md).

- **State Space** - the behavior combinations created by axes, modes, surfaces, and lifecycle states.
- **Axis** - an independent choice that multiplies behavior.
- **Mode** - an axis value that changes execution semantics.
- **Surface** - a callable or documented entrypoint that users, tools, tests, or agents can reach.
- **Layer** - an architectural band with a specific responsibility.
- **Control Plane** - code that decides what work happens, when, and under which policy.
- **Active Path** - the intended route through the system.
- **Preservation Path** - code kept only to protect prior behavior, migration, compatibility, or audit shape.
- **Reduction Candidate** - a concrete simplification move with a smaller after-state.

Key principles:

- **The multiplication test**: every new axis multiplies tests, states, and reader effort.
- **Reachable code is product surface.** Dormant but callable behavior still counts.
- **Compatibility has a carrying cost.** In pre-MVP or explicitly breaking-change contexts, give
  preservation paths no default weight.
- **Policy is not mode.** Prefer stable data, policy, or evidence requirements over execution forks.
- **One active path beats many clever paths.**

## Process

### 1. Explore

Read the repo's source-of-truth documents first: product overview, architecture, contracts, roadmap,
testing strategy, decisions, operating instructions, and current handoff or planning state when
available. Then inspect the actual code and tests to see what is live.

Then inventory the live code and tests with `rg --files` or `git ls-files` before using broader
filesystem walks. Avoid treating ignored caches, generated artifacts, virtual environments, and
build outputs as product surface unless the user explicitly asks to audit local artifacts.

Spawn read-only Codex explorer subagents when the host exposes subagent tools and the current task
permits delegation; otherwise explore locally or prepare self-contained read-only prompts. Give
explorers separate lenses:

- surface inventory;
- axis and mode inventory;
- layer and control-plane inventory;
- test matrix and verification inventory.

Do not treat docs as true until code agrees. Record mismatches between declared architecture and
reachable behavior.

### 2. Build The Complexity Map

Identify the current state-space drivers:

- public CLI, API, UI, MCP, plugin, worker, job, and config surfaces;
- axis-like fields, flags, enum values, modes, profiles, strategies, and fallbacks;
- hidden mode switching based on environment, data shape, feature gates, or inferred state;
- preservation paths, migrations, aliases, adapters, compatibility branches, and duplicate schemas;
- layers that pass data through without owning policy or behavior;
- control-plane logic split across transport, storage, runtime, and orchestration code;
- tests that encode old surfaces or force many behavior combinations.

Use [REDUCTION-MOVES.md](REDUCTION-MOVES.md) to classify likely moves.

### 3. Present Candidates

Prefer a concise Markdown report unless the user asks for an HTML artifact. If generating a report,
use [REPORT.md](REPORT.md). In read-only, readonly, review-only, audit-only, no-edits, or
no-mutation mode, do not edit files, write reports, mutate planning state, or update trackers;
return candidates in chat.

For each candidate, include:

- **Area** - files, modules, commands, schemas, or docs involved.
- **State-space driver** - which axis, mode, surface, layer, or preservation path multiplies work.
- **Reduction** - what to delete, merge, make explicit, or collapse.
- **After-state** - the smaller architecture in plain language.
- **Test impact** - which tests disappear, move up a level, or become focused.
- **Risk** - what can break and why that risk is acceptable or unacceptable.
- **Recommendation strength** - `Strong`, `Worth exploring`, or `Speculative`.

End with a **Top recommendation**: the first candidate to pursue and why.

### 4. Grilling Loop

After presenting candidates, ask the user which one to explore. For an approved or clearly scoped
implementation pass, choose the top recommendation only when the repo's source docs and active task
make the priority clear.

For the selected candidate, grill the design:

- What behavior remains essential?
- Which axes become data or policy?
- Which modes disappear?
- Which surfaces remain callable?
- Which layer owns the decision?
- Which tests prove the smaller path?
- What can be deleted immediately?

If the user chooses a breaking simplification context, do not add compatibility scaffolding unless
the user explicitly asks for it.

### 5. Implementation Shape

When mutation is in scope, reduce before abstracting:

1. Delete unreachable or preservation-only paths.
2. Collapse surfaces onto the active path.
3. Collapse axes into data, policy, or a single lifecycle state model.
4. Move control-plane decisions into one layer.
5. Remove tests that only preserve deleted behavior.
6. Add focused tests for the smaller contract.
7. Update source-of-truth docs so they read as if the simplified design was always intended.

Keep the after-state small enough to explain in one diagram or one paragraph.
