# Decisions

## D-0001: No Legacy Preservation

Decision: Pre-MVP legacy behavior has zero preservation weight.

Rationale: No external users depend on the old state space. Preserving compatibility would preserve
the complexity that made development feel like whack-a-mole.

## D-0002: Fresh Planning Schema

Decision: Replace the historical planning schema with a smaller database centered on plans, tasks,
attempts, evidence bundles, and decisions.

Rationale: The old schema encoded too many accumulated operational incidents as permanent product
concepts.

## D-0003: Assurance Levels Are Policy

Decision: `low`, `medium`, and `high` are assurance levels, not execution modes.

Rationale: They should change evidence and acceptance requirements without multiplying backend,
runtime, review, CLI, MCP, or schema paths.

## D-0004: Skills Are Guidance, Not Control Plane

Decision: The repo-local skill surface is reduced to a single simplified supervisor skill.

Rationale: The old skill mesh routed work through many overlapping workflows and recreated the
state-space problem outside the Python code.

## D-0005: Plugin Surface Is Removed For Now

Decision: The packaged Desktop plugin is removed from the active repo surface.

Rationale: A plugin should be an adapter over a stable core. The core is being rebuilt.

## D-0006: CI Guards The Current Contract

Decision: CI runs the minimal verification gate for the simplified contract.

Rationale: Running historical tests would turn deleted behavior back into requirements.

## D-0007: Insights Are Curated, Not Historical Storage

Decision: Historical insight files are replaced by current lessons from the simplification
conversation.

Rationale: Durable learning should guide future design, not force the project to keep every
incident-specific hardening rule.
