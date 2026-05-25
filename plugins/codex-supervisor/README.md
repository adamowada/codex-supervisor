# Codex Supervisor Plugin

This repo-local Codex Desktop plugin exposes the `codex-supervisor` MCP stdio server and a
Desktop workflow skill. It is the Stage 12 Desktop boundary for plugin metadata, MCP wiring,
operator-facing local install notes, and workflow routing.

## What It Provides

- `.codex-plugin/plugin.json` gives Codex Desktop discovery metadata for Codex Supervisor.
- `.mcp.json` defines a `codex-supervisor` MCP server that runs
  `uv run --no-sync python -B -m codex_supervisor.mcp_stdio` from the repository root.
- `skills/codex-supervisor/SKILL.md` gives Desktop a packaged workflow entrypoint for queue
  inspection, project bootstrap, worker launch, review, ACP, and handoff.
- The MCP server routes through the Python core, reads `plans/planning.sqlite3` as the queue
  authority, and exposes default-on mutating tools for planning, task, progress, artifact, Story
  Loop launch, and review-result ingestion workflows.
- `HANDOFF.md` remains the mutable resume snapshot, not the historical queue source.

## Local Use

Point Codex Desktop at `plugins/codex-supervisor` as a local plugin source from this repository. The
plugin expects to run with the repository root as its MCP working directory through the `.mcp.json`
`cwd` setting.

Run the MCP server directly during local checks:

```sh
uv run --no-sync python -B -m codex_supervisor.mcp_stdio
```

The mutating MCP tools are enabled by default. Start the server with `--disable-mutations` when a
read-only Desktop session is intentionally required:

```sh
uv run --no-sync python -B -m codex_supervisor.mcp_stdio --disable-mutations
```

Verify the plugin source from a clean local discovery context:

```sh
uv run --no-sync python -B scripts/verify_codex_plugin_install.py
```

## Workflow Map

| Desktop workflow | Route through |
| --- | --- |
| Project bootstrap | `spawned-project-bootstrap` or `setup-agent-docs`, then planning SQLite through CLI helpers |
| Queue inspection | MCP tools or `uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json` |
| Worker launch | `story-loop-runner`, `goal-contract-render`, `task-claim`, and Codex Exec only after backend preflight |
| Review | `fresh-thread-code-reviewer` and `review-result-ingest` for durable review progress |
| ACP | `acp-publisher`, `uv run --no-sync python -B scripts/verify.py --publication-ready`, then scoped Git add/commit/push |
| Handoff | `context-compaction-handoff` or `thread-resume-brief`, with `HANDOFF.md` updated after planning SQLite |

## Responsibilities

- CLI commands own deterministic repository workflows and remain the reference surface for planning
  SQLite mutations.
- MCP tools expose supervisor inspection and guarded mutation for Desktop and other MCP clients.
- `codex_supervisor.project_list` only accepts configured project roots and redacts local absolute
  paths from returned data.
- The packaged plugin skill is a Desktop entrypoint; repo-local skills in `.agents/skills/` remain
  the detailed workflow source during Stage 12.
- Planning SQLite remains the canonical queue and worker evidence store.
- `HANDOFF.md` records the compact current resume state.

## Trust Boundary

This plugin does not publish a marketplace entry, write personal Codex plugin registries,
bulk-copy the repo-local skill library into the plugin archive, or install into a clean Desktop
profile. Live workers and review ingestion are exposed through production MCP tools and still depend
on the selected backend, Codex executable, `CODEX_HOME`, Goal Mode preflight, and planning SQLite
task contract.
