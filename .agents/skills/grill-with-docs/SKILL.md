---
name: grill-with-docs
description: Run a grilling session that challenges a plan against the existing domain model, locked source-of-truth docs, planning records, glossary terms, and ADRs. Use when the user wants to stress-test a plan, sharpen terminology, resolve assumptions one by one, or update durable project knowledge as decisions crystallize.
---

<what-to-do>

Interview the user relentlessly about every aspect of the plan until you reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one by one. For each question, provide your recommended answer.

If the current user turn is read-only or review-only, do not edit durable docs, insights, planning
SQLite, issues, or tracker state. Return challenged assumptions, recommended answers, and proposed
source-of-truth updates only.

Ask one question at a time, waiting for feedback before continuing in interactive mode. In approved
AFK or dangerous full-auto mode, derive answers from durable sources, record assumptions, and turn
unresolved decisions into explicit HITL blockers instead of stalling.

If a question can be answered by exploring the codebase or source-of-truth docs, explore instead of asking.

</what-to-do>

<supporting-info>

## Source Awareness

Start by finding the repo's documented authority matrix. For `codex-supervisor` spawned projects:

- locked source-of-truth docs govern durable doctrine, architecture, contracts, testing policy,
  roadmap intent, and stable operating rules;
- planning SQLite and `story-loop-status` govern active and blocked current-queue plans, current
  queue state, task status, worker runs, progress events, and handoff order;
- GitHub issues and PRs are remote tracker state after reconciliation;
- handoff artifacts are mutable snapshots;
- chat/session history is context.

Read `docs/agents/source-of-truth.md` when present. In `codex-supervisor` itself, read the protected top-level docs plus `insights/` before changing durable knowledge.

## Domain Awareness

During exploration, look for domain docs:

- `docs/agents/domain.md`
- `CONTEXT.md`
- `CONTEXT-MAP.md`
- `docs/adr/`
- context-specific `CONTEXT.md` and `docs/adr/` folders referenced by `CONTEXT-MAP.md`

Only create or update `CONTEXT.md`, `CONTEXT-MAP.md`, or `docs/adr/` when those docs are part of the repo's established source-of-truth system. If not, propose where the glossary or decision should live and ask before creating new document families.

## During The Session

### Challenge Against The Glossary

When the user uses a term that conflicts with existing language, call it out immediately. Example: "Your glossary defines cancellation as X, but you seem to mean Y. Which is it?"

### Sharpen Fuzzy Language

When the user uses vague or overloaded terms, propose a precise canonical term. Example: "You're saying account. Do you mean Customer or User? Those are different things."

### Discuss Concrete Scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force precise boundaries between concepts.

### Cross-Reference With Code

When the user states how something works, check whether the code agrees. If the code contradicts the plan, surface the contradiction and ask which source should change.

### Update Durable Knowledge Inline

When a term is resolved, update the configured glossary source immediately if that source is allowed to change in this session. Use [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md) for `CONTEXT.md` style glossaries.

In `codex-supervisor`, durable learning belongs in `insights/` via `knowledge-graph-updater`, and source-of-truth document changes require `source-lock-operator`.

Glossary docs should be devoid of implementation details. Do not treat a glossary as a spec, scratch pad, or repository for implementation decisions.

### Offer ADRs Sparingly

Only offer to create an ADR when all three are true:

1. **Hard to reverse** - the cost of changing your mind later is meaningful.
2. **Surprising without context** - a future reader will wonder why the decision was made.
3. **The result of a real trade-off** - there were genuine alternatives and one was chosen for specific reasons.

If any of the three is missing, skip the ADR. Use [ADR-FORMAT.md](./ADR-FORMAT.md) only when the repo has adopted ADRs or the user approves adding them.

</supporting-info>
