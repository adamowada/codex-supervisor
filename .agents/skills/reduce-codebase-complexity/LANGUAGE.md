# Language

Shared vocabulary for complexity-reduction reviews. Use these terms instead of ad hoc substitutes
so candidates are comparable.

## Terms

**State Space**
The total set of behavior combinations a maintainer, caller, tester, or agent must reason about.
Axes, modes, surfaces, lifecycle states, fallbacks, adapters, and config switches all expand it.

**Axis**
An independent choice that can vary. Examples: backend, task type, execution transport, evidence
format, source adapter, review level, feature gate, or trust level. Each real axis multiplies test
and reasoning cost.

**Mode**
A named axis value that changes semantics. A mode is expensive when callers must know different
rules, ordering, evidence, error handling, or lifecycle behavior for each value.

**Surface**
Anything reachable: CLI commands, functions, APIs, MCP tools, plugins, background jobs, config
keys, documented workflows, database schemas, and generated artifacts. If users or tests can call
it, it is surface.

**Layer**
An architectural band with a responsibility. Good layers own decisions. Weak layers translate or
pass through without reducing knowledge required by callers.

**Control Plane**
The part of a system that decides what happens, when, under which policy, and with which evidence.
Control-plane complexity is dangerous because every worker, adapter, and operator path depends on
it.

**Active Path**
The intended route through the system. It should be obvious from docs, tests, and code.

**Preservation Path**
Code retained to protect prior behavior, compatibility, migration, audit trails, aliases, old
schemas, old adapters, or old tests. Preservation paths are valid only when the project explicitly
values that cost.

**Hidden Switch**
A behavior fork caused by inference, environment, filesystem state, schema shape, feature flags, or
data content rather than an explicit interface decision.

**Reduction Candidate**
A proposed change whose after-state has less state space. It may delete, merge, collapse, move, or
make explicit.

## Tests

**Multiplication Test**
Ask how many behavior combinations a choice creates. If adding one value creates N more fixtures,
branches, docs, or test rows, it is an axis and must earn its keep.

**Deletion Test**
Imagine deleting the code. If no essential behavior disappears, delete it. If essential behavior
reappears scattered across callers, consolidate it behind a better active path.

**Surface Test**
Ask who can call it. If the answer is "tests," "old docs," "a plugin," "an agent," or "maybe a
future user," it is still surface until removed or made unreachable.

**Mode Test**
Ask whether different values change semantics. If yes, either collapse them, make the policy
explicit, or move the variation behind one interface.

## Preferred Framing

- Say **axis** instead of option when the choice multiplies behavior.
- Say **mode** only when semantics change.
- Say **surface** instead of API when reachability matters.
- Say **active path** instead of happy path.
- Say **preservation path** instead of compatibility when compatibility has not been chosen as a
  goal.
- Say **control plane** for decision-making machinery, not worker implementation.
