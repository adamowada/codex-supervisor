---
name: codex-supervisor
description: Operate the compact codex-supervisor control plane through task intent, attempts, evidence, acceptance, and assurance policy.
---

# Codex Supervisor

Use this skill for work inside this repository.

## Model

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

## Operating Rules

- Keep the state space small.
- Use assurance levels as policy: `low`, `medium`, `high`.
- Keep `plans/planning.sqlite3` on the schema from `PLANS.md`.
- Keep `HANDOFF.md` current and compact.
- Refresh protected-file hashes after intentional source-of-truth edits.

## Verification

Run:

```sh
uv run --no-sync python -B scripts/verify.py
```

The verification gate covers the active planning schema, skill inventory, source locks, and focused
contract tests.
