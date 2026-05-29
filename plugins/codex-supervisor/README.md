# Codex Supervisor Plugin

This is the thin Codex Desktop wrapper for `codex-supervisor`.

It provides:

- `.codex-plugin/plugin.json` for plugin discovery.
- `.mcp.json` for the `codex-supervisor` MCP server.
- `scripts/mcp_launcher.py` to start the repository's compact MCP stdio server.
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
