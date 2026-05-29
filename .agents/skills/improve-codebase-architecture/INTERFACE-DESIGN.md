# Interface Design

When the user wants to explore alternative interfaces for a chosen deepening candidate, use this parallel subagent pattern. It is based on "Design It Twice" (Ousterhout): the first idea is unlikely to be the best.

Uses the vocabulary in [LANGUAGE.md](LANGUAGE.md): **module**, **interface**, **seam**, **adapter**, **leverage**, and **locality**.

## Process

### 1. Frame The Problem Space

Before spawning subagents, write a user-facing explanation of the problem space for the chosen candidate:

- The source-of-truth docs and planning records that constrain the design.
- The constraints any new interface would need to satisfy.
- The dependencies it would rely on, and which category they fall into (see [DEEPENING.md](DEEPENING.md)).
- A rough illustrative code sketch to ground the constraints. This is not a proposal; it only makes the constraints concrete.

Show this to the user, then proceed to Step 2. The user can read while the subagents work in parallel.

### 2. Spawn Subagents

Spawn 3+ read-only Codex explorer subagents in parallel when the host exposes subagent tools;
otherwise prepare separate self-contained design prompts or explore the variants locally. Each lane
must produce a **radically different** interface for the deepened module.

Prompt each subagent with a separate technical brief: relevant modules, coupling details, dependency category from [DEEPENING.md](DEEPENING.md), what sits behind the seam, and which source-of-truth docs must be preserved. The brief is independent of the user-facing problem-space explanation in Step 1.

Give each agent a different design constraint:

- Agent 1: "Minimize the interface. Aim for 1-3 entry points max. Maximize leverage per entry point."
- Agent 2: "Maximize flexibility. Support many use cases and extension."
- Agent 3: "Optimize for the most common caller. Make the default case trivial."
- Agent 4, if applicable: "Design around ports and adapters for cross-seam dependencies."

Include both [LANGUAGE.md](LANGUAGE.md) vocabulary and the project's domain vocabulary in the brief so each subagent names things consistently.

Each subagent outputs:

1. Interface: types, methods, params, invariants, ordering, and error modes.
2. Usage example showing how callers use it.
3. What the implementation hides behind the seam.
4. Dependency strategy and adapters.
5. Trade-offs: where leverage is high, where it is thin.

### 3. Present And Compare

Present designs sequentially so the user can absorb each one, then compare them in prose. Contrast by **depth**, **locality**, and **seam placement**.

After comparing, give your own recommendation: which design is strongest and why. If elements from different designs combine well, propose a hybrid. Be opinionated.