---
name: codex-supervisor
description: Operate the simplified pre-MVP codex-supervisor repo without resurrecting legacy skills, plugin surfaces, or historical planning behavior.
---

# Codex Supervisor

Use this skill for work inside this repository.

## Rules

- Treat the project as pre-MVP.
- Give no preservation weight to historical tests, old planning rows, old skill routing, old plugin
  packaging, or old CLI/MCP surfaces.
- Work from the fresh model:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

- Use assurance levels as policy only: `low`, `medium`, `high`.
- Keep `plans/planning.sqlite3` on the fresh schema from `PLANS.md`.
- Keep `HANDOFF.md` current and compact.
- When protected source-of-truth docs change intentionally, refresh hashes.

## Verification

Run:

```sh
uv run --no-sync python -B scripts/verify.py
```

That is the active gate. Do not run deleted historical gates to decide whether this simplified
contract is acceptable.
