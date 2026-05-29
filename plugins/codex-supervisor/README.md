# Codex Supervisor Plugin

This is the thin Codex Desktop wrapper for `codex-supervisor`.

It provides:

- `.codex-plugin/plugin.json` for plugin discovery.
- `.mcp.json` for the `codex-supervisor` MCP server.
- `scripts/mcp_launcher.py` to start the repository's compact MCP stdio server.
- `scripts/cli_launcher.py` to forward Desktop CLI calls to the source repository without relying
  on `PATH`. When a compact command omits `--path`, the launcher uses the current workspace ledger
  at `.codex-supervisor/planning.sqlite3`.
- `skills/codex-supervisor/SKILL.md` as the Desktop-visible entrypoint.

The plugin is packaging only. The product contract remains in the Python package:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

The active MCP operation is read-only queue inspection:

```text
codex_supervisor.queue_next
```

When the plugin is launched from the source tree, the launcher finds the repository automatically.
When launched from the installed Codex cache, it resolves the source repository from
`CODEX_HOME/config.toml` and the configured `codex-supervisor-local` marketplace. Set
`CODEX_SUPERVISOR_REPO_ROOT` only when overriding that lookup intentionally.

For full AFK work in a fresh folder, initialize `.codex-supervisor/planning.sqlite3`, create one
task intent, and run the worker through `attempt-run`. The worker receives the durable assignment at
`CODEX_SUPERVISOR_TASK_JSON`; stdout, stderr, command metadata, assignment metadata, artifacts,
checks, risks, and acceptance results are recorded through the same evidence path. Failed worker
processes cannot record supplied passing acceptance results as passing evidence.
