# Out-Of-Scope Knowledge Base

Read-only/no-mutation guard: in read-only, readonly, review-only, audit-only, no-edits, or
no-mutation mode, draft only. Do not close issues, change labels, write `.out-of-scope/` records, or
mutate planning SQLite; return proposed tracker and file mutations for later approval.

The `.out-of-scope/` directory stores durable records of rejected feature requests.

It exists for:

- institutional memory: why a feature was rejected;
- deduplication: how to recognize repeated requests without re-litigating them.

## Authorization Gate

Do not close issues, add `wontfix`, or write `.out-of-scope/` records unless the maintainer has
authorized the decision or the repo's current full-auto policy explicitly allows that action.
Surfacing a likely match is safe; taking irreversible tracker action needs authorization.

## Directory Structure

```text
.out-of-scope/
dark-mode.md
plugin-system.md
graphql-api.md
```

Use one file per concept, not one file per issue. Multiple issues requesting the same thing belong
in the same concept file.

## File Format

Write a short durable rationale:

```markdown
# Dark Mode

This project does not support dark mode or user-facing theming.

## Why This Is Out Of Scope

The rendering pipeline assumes a single color palette defined in `ThemeConfig`. Supporting multiple
themes would require a theme context provider, per-component theme-aware style resolution, and a
persistence layer for preferences.

## Prior Requests

- #42: Add dark mode support
- #87: Night theme for accessibility
```

Good reasons reference project scope, technical constraints, strategic decisions, or prior source of
truth. Avoid temporary reasons such as "not enough time."

## Triage Flow

1. Read existing `.out-of-scope/*.md` files during triage.
2. Match by concept similarity, not keyword only.
3. Surface likely matches to the maintainer.
4. If authorized, append the new issue to the existing concept or create a new concept file.
5. Comment on the issue with the decision.
6. Close with the configured out-of-scope label only after authorization.

If the maintainer reconsiders a concept, delete or update the concept file and triage the new issue
normally. Historical issues do not need to be reopened unless the maintainer asks.
