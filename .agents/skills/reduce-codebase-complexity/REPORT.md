# Report Format

Use this structure for complexity-reduction reviews. In read-only, review-only, audit-only,
no-edits, or no-mutation mode, return the report in chat and name where it would be written.

## Markdown Report

Start with facts, not preamble:

1. **Declared Architecture** - the shape described by source-of-truth docs.
2. **Live Architecture** - the reachable code, surfaces, schemas, and tests.
3. **State-Space Drivers** - axes, modes, surfaces, hidden switches, layers, and preservation paths.
4. **Reduction Candidates** - ranked candidates.
5. **Top Recommendation** - one first move.

## Candidate Card

Use this template:

```markdown
### Candidate: <short name>

**Strength:** Strong | Worth exploring | Speculative
**Primary move:** Delete Preservation Paths | Shrink Surface | Collapse Axes | Remove Modes | Make Hidden Switches Explicit | Re-layer Around Ownership | Collapse Control Plane | Lift Tests
**Area:** `file-or-module`, `command`, `schema`, or `surface`

**State-space driver:** One sentence naming the multiplier.

**Reduction:** One sentence naming what changes.

**After-state:** One sentence describing the smaller design.

**Test impact:** Which tests disappear, move, or become simpler.

**Risk:** What could break and why that is acceptable or not.
```

## Diagrams

Use diagrams only when they clarify the reduction.

Good diagram types:

- **Surface map:** before and after list of reachable entrypoints.
- **Axis matrix:** rows are axes, columns are values; cross out collapsed axes.
- **Layer cross-section:** before has decision leakage across layers; after has one owner.
- **Control-plane flow:** before has multiple routes; after has one transition path.

Keep diagrams small enough that the after-state is visibly simpler.
