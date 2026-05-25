# Codex Supervisor Plugin

This repo-local Codex Desktop plugin scaffold exposes the `codex-supervisor` MCP stdio server. It is
the Stage 12A Desktop boundary: plugin metadata, MCP wiring, and operator-facing local install notes.

## What It Provides

- `.codex-plugin/plugin.json` gives Codex Desktop discovery metadata for Codex Supervisor.
- `.mcp.json` defines a `codex-supervisor` MCP server that runs
  `uv run --no-sync python -B -m codex_supervisor.mcp_stdio` from the repository root.
- The MCP server routes through the Python core and reads `plans/planning.sqlite3` as the queue
  authority.
- `HANDOFF.md` remains the mutable resume snapshot, not the historical queue source.

## Local Use

Point Codex Desktop at `plugins/codex-supervisor` as a local plugin source from this repository. The
plugin expects to run with the repository root as its MCP working directory through the `.mcp.json`
`cwd` setting.

Run the MCP server directly during local checks:

```sh
uv run --no-sync python -B -m codex_supervisor.mcp_stdio
```

## Responsibilities

- CLI commands own deterministic repository workflows and planning SQLite mutations.
- MCP tools expose read-only supervisor inspection for Desktop and other MCP clients.
- Repo-local skills in `.agents/skills/` remain active workflow source during Stage 12A.
- Planning SQLite remains the canonical queue and worker evidence store.
- `HANDOFF.md` records the compact current resume state.

## Trust Boundary

This scaffold does not publish a marketplace entry, write personal Codex plugin registries, copy
skill bodies into the plugin archive, install into a clean Desktop profile, launch live workers, or
add mutating MCP tools. Those are later Stage 12 slices after this local MCP scaffold is verified.
