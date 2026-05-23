# ADR Format

Use the repo's configured decision-record path. If `setup-agent-docs` has not established one, ask before creating a new ADR directory.

Common default:

```text
docs/adr/0001-slug.md
docs/adr/0002-slug.md
```

For `codex-supervisor` itself, durable decisions belong in the protected source-of-truth system and planning SQLite; update locks after changing protected docs.

## Template

```md
# {Short title of the decision}

{1-3 sentences: what's the context, what did we decide, and why.}
```

That's it. An ADR can be a single paragraph. The value is in recording that a decision was made and why, not in filling out sections.

## Optional Sections

Only include these when they add genuine value. Most ADRs will not need them.

- **Status** frontmatter (`proposed | accepted | deprecated | superseded by ADR-NNNN`) - useful when decisions are revisited.
- **Considered Options** - only when the rejected alternatives are worth remembering.
- **Consequences** - only when non-obvious downstream effects need to be called out.

## Numbering

Scan the configured ADR directory for the highest existing number and increment by one.

## When To Offer An ADR

All three of these must be true:

1. **Hard to reverse** - the cost of changing your mind later is meaningful.
2. **Surprising without context** - a future reader will wonder why the decision was made.
3. **The result of a real trade-off** - there were genuine alternatives and one was chosen for specific reasons.

If a decision is easy to reverse, skip it. If it is not surprising, nobody will wonder why. If there was no real alternative, there is nothing to record beyond "we did the obvious thing."

## What Qualifies

- **Architectural shape.** Example: "The write model is event-sourced, the read model is projected into Postgres."
- **Integration patterns between contexts.** Example: "Ordering and Billing communicate via domain events, not synchronous HTTP."
- **Technology choices that carry lock-in.** Database, message bus, auth provider, or deployment target.
- **Scope decisions.** Example: "Customer data is owned by the Customer context; other contexts reference it by ID only."
- **Deliberate deviations from the obvious path.** Example: "Use manual SQL instead of an ORM because X."
- **Constraints not visible in the code.** Example: "Response times must stay under 200ms because of a partner API contract."
- **Rejected alternatives when the rejection is non-obvious.** Record these so the same option is not re-litigated later.
