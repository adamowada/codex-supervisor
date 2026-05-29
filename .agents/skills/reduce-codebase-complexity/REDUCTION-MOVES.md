# Reduction Moves

Use these moves to classify candidates. A good report can combine several, but each candidate should
name the primary move.

## Delete Preservation Paths

Remove aliases, fallback schemas, compatibility branches, migration scaffolds, old command names,
and tests that exist only to preserve a previous shape.

Use when:

- the product is pre-release or explicitly allows breaking changes;
- no current caller depends on the path;
- docs describe a newer active path;
- the preserved path multiplies tests or confuses operators.

After-state: one active path with no compatibility story unless the user explicitly asks for one.

## Shrink Surface

Remove or hide callable entrypoints until they are justified by active workflows and tests.

Targets:

- CLI commands;
- API routes;
- MCP tools and plugin operations;
- background jobs;
- config keys;
- exported modules;
- generated files that callers consume.

After-state: every surface maps to an active source-of-truth contract and a focused test.

## Collapse Axes

Turn independent behavior choices into data, policy, or a single lifecycle model.

Examples:

- Replace backend-specific task schemas with one attempt record plus executor metadata.
- Replace review/no-review execution forks with assurance policy.
- Replace multiple evidence formats with one evidence bundle shape.

After-state: callers learn one model; policy changes requirements without changing the route.

## Remove Modes

Delete modes that describe historical implementation choices, convenience shortcuts, or environment
accidents. Keep only modes that express real product semantics.

Watch for:

- flags that change control flow;
- enums with overlapping meanings;
- inferred modes from file presence or schema shape;
- "manual," "automatic," "fallback," or "degraded" variants that bypass policy.

After-state: either one behavior or an explicit policy decision with a single transition path.

## Make Hidden Switches Explicit

If a fork must remain, move it to a visible policy or input and test it directly. Hidden switches are
especially dangerous in agentic systems because agents cannot see why behavior changed.

After-state: no behavior fork depends on accidental environment or stale state.

## Re-layer Around Ownership

Move decisions to the layer that owns them. Delete layers that only translate names or pass objects
through.

Common repairs:

- storage stores state but does not choose policy;
- CLI parses and renders but does not own business logic;
- adapters translate transport but do not own lifecycle;
- policy evaluates requirements but does not launch work.

After-state: each layer has one reason to exist and one direction of dependency.

## Collapse Control Plane

Centralize orchestration decisions into one small model. Agentic and worker systems need this most:
multiple controllers, queues, status machines, or evidence paths create runaway state space.

After-state: one durable state model and one way to advance work.

## Lift Tests To The Smaller Contract

Delete tests that lock in removed surfaces. Add or keep tests that prove the active path.

Prefer:

- matrix tests for true axes;
- contract tests for public surfaces;
- lifecycle tests for state transitions;
- integrity checks for durable state.

After-state: fewer tests with higher leverage, not brittle coverage of every old branch.
