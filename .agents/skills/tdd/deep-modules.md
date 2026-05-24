# Deep Modules

Use the architecture skill glossary as the authority for "deep module" language:
`../improve-codebase-architecture/LANGUAGE.md`.

In TDD planning, treat a deep module as a module whose interface gives high leverage for its callers:
simple to use, hard to misuse, and able to hide meaningful implementation detail behind stable
behavior. Do not reduce depth to a line-count ratio or "small interface plus lots of code"; the
question is whether the interface buys enough behavior, clarity, and locality for the system.

When designing interfaces, ask:

- Can the public behavior be named in domain language?
- Can callers do less coordination work?
- Can invalid states or call orders be made harder?
- Can more implementation detail stay private?
- Can tests verify behavior through the public interface instead of internals?
