# Domain Docs

Domain docs give agents a compact project language.

Single-context repos use:

```text
CONTEXT.md
docs/adr/
```

Multi-context repos use:

```text
CONTEXT-MAP.md
src/<context>/CONTEXT.md
src/<context>/docs/adr/
```

`CONTEXT.md` is a glossary, not a spec. ADRs record surprising, durable tradeoffs.
