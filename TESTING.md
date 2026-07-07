# Testing

The verification strategy protects the durable Goal Mode substrate contract.

## Current Gate

Run:

```sh
uv run --no-sync python -B scripts/verify.py
```

The gate checks:

- planning database schema and seed records;
- repo-local skill inventory;
- protected source-of-truth hashes;
- focused tests for the compact durable model;
- e2e coverage for MCP stdio, the Codex plugin wrapper, and generic worker process attempts;
- e2e coverage that proves an autonomous worker receives task assignment metadata and completes an
  empty project through `attempt-run`;
- e2e coverage that the installed-cache plugin CLI launcher can initialize and inspect a fresh
  planning database with `plan-init --json` without relying on `codex-supervisor` being on `PATH`;
- e2e coverage that the installed-cache plugin CLI launcher defaults omitted planning paths to the
  invocation workspace, not the source repository;
- e2e coverage that failed process attempts cannot record supplied passing acceptance results as
  passing evidence;
- e2e coverage that verifier failures override supplied passing acceptance results;
- e2e coverage that process launch failures, missing declared artifacts, retry after blocked work,
  and running queue inspection preserve durable substrate state;
- e2e coverage that `attempt-run` copies and hashes launch packets and verifier intent files before
  worker product mutation;
- e2e coverage that `command.json` exists while an attempt is running;
- focused coverage that generic task lineage is stored, validated, and exposed through queue
  inspection;
- e2e coverage that installed-cache MCP queue inspection uses an explicit workspace ledger path
  instead of the source repository ledger;
- e2e coverage that full AFK product follow-up mutation is assigned through another worker attempt,
  preserving the Goal Mode/Supervisor role boundary;
- e2e coverage that the target-workspace ACP gate rejects direct product edits, rejects tracked
  `.codex-supervisor/**` state, and accepts product changes backed by `attempt-run` evidence;
- focused module coverage for target workspace product provenance, evidence encoding, and terminal
  attempt acceptance;
- contract coverage that `HANDOFF.md` edits are paired with `plans/planning.sqlite3` edits, so the
  readable handoff and durable ledger stay current together.

## Test Philosophy

- Test the model before the interface.
- Test one transition path at a time.
- Test workers as process attempts, not as job-specific modes.
- Test Goal Mode recovery state as compact data.
- Add tests with rebuilt behavior.
- Keep tests close to task, attempt, evidence, acceptance, lineage, and recovery semantics.

## Substrate Test Growth

Next tests should cover:

- launch-time `command.json` coverage for failed attempts;
- expanded `queue-next` and MCP recovery state;
- evidence digest generation and raw log preservation;
- warnings before hard gates for missing packet, missing launch metadata, unbacked product mutation,
  and final completion without proof.

## Live Smoke

The verification gate does not launch real Codex Desktop or a real Codex worker. It uses
deterministic subprocess workers so CI stays stable and the active contract stays reproducible.

Broader live smoke testing happens manually in separate Codex Desktop workspaces, then durable
lessons are folded back into deterministic source tests.
