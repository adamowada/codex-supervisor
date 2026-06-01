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
- For full AFK, autonomous worker, unattended worker, or worker-assigned file mutation, create the
  task with `--assurance high` unless the user explicitly requests a lower assurance level.
- For full AFK, autonomous worker, unattended worker, or worker-assigned file mutation, the
  supervisor **MUST NOT mutate product files directly**. Product mutations belong inside
  `attempt-run`; supervisor-owned setup, verifier, and evidence files belong under
  `.codex-supervisor/`.
- When acceptance depends on machine-checkable facts, use `attempt-run --verify-command` to record an
  independent verifier result before acceptance is finalized.
- When work already belongs to an existing task, acceptance **MUST** be recorded on that task. You
  **MUST NOT** create acceptance-only follow-up tasks; create follow-up task intent only for new
  product work, repair, cleanup, audit, or polish.
- Prefer workspace Python verifiers at `.codex-supervisor/verify.py` over inline shell or
  PowerShell verifier logic.
- Verifiers should prove behavior or structural contract. Literal string checks should only be used
  when the literal text is itself required.
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
