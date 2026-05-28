"""Cache-safe MCP launcher for the Codex Supervisor Desktop plugin.

The plugin is copied into CODEX_HOME/plugins/cache before Desktop starts its MCP server. Relative
paths that point back to the source repo from plugins/codex-supervisor do not survive that copy, so
this launcher locates the source package from either the source layout or the Desktop marketplace
configuration and then delegates to the real Python package.

If delegation cannot start, the launcher serves a minimal MCP diagnostic server exposing only
codex_supervisor.runtime_preflight. That gives the model a visible fail-closed canary instead of an
invisible MCP startup failure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

PLUGIN_NAME = "codex-supervisor"
SOURCE_ENV_VAR = "CODEX_SUPERVISOR_REPO_ROOT"
JSON_RPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "codex-supervisor"

JsonObject = dict[str, Any]


def main() -> int:
    plugin_root = Path(__file__).resolve().parents[1]
    repo_root, diagnostic = find_repo_root(plugin_root, os.environ)
    if repo_root is None:
        return serve_unavailable_stdio(
            f"MCP startup failed: could not locate codex-supervisor source package. {diagnostic}"
        )
    command = (
        "uv",
        "run",
        "--no-sync",
        "python",
        "-B",
        "-m",
        "codex_supervisor.mcp_stdio",
        "--repo-root",
        str(repo_root),
    )
    try:
        completed = subprocess.run(command, cwd=repo_root, check=False)
    except FileNotFoundError:
        return serve_unavailable_stdio(
            "MCP startup failed: program not found: uv. Install uv or repair PATH before "
            "using codex-supervisor from Desktop."
        )
    except OSError as exc:
        return serve_unavailable_stdio(f"MCP startup failed: {exc}")
    if completed.returncode != 0:
        return serve_unavailable_stdio(
            "MCP startup failed: real codex-supervisor backend exited with code "
            f"{completed.returncode}."
        )
    return 0


def find_repo_root(plugin_root: Path, environ: Mapping[str, str]) -> tuple[Path | None, str]:
    candidates = tuple(_repo_root_candidates(plugin_root, environ))
    for candidate in candidates:
        normalized = _normalize_source_candidate(candidate)
        if _is_source_repo(normalized):
            return normalized.resolve(), ""
    tried = ", ".join(_display_path(candidate) for candidate in candidates) or "no candidates"
    return None, f"Checked {tried}."


def serve_unavailable_stdio(diagnostic: str) -> int:
    server = _DiagnosticServer(diagnostic=diagnostic)
    for raw_line in sys.stdin:
        line = raw_line.rstrip("\r\n")
        if not line:
            continue
        response = server.handle_line(line)
        if response is not None:
            _write_json_line(response)
    return 0


def _repo_root_candidates(plugin_root: Path, environ: Mapping[str, str]) -> Iterable[Path]:
    env_root = environ.get(SOURCE_ENV_VAR)
    if env_root:
        yield Path(_strip_windows_extended_prefix(env_root))

    yield plugin_root.parents[1]

    cache_info = _cache_info(plugin_root, environ)
    if cache_info is None:
        return
    codex_home, marketplace_name = cache_info
    config_path = codex_home / "config.toml"
    source = _marketplace_source(config_path, marketplace_name)
    if source:
        source_path = Path(_strip_windows_extended_prefix(source))
        yield source_path
        yield source_path / "plugins" / PLUGIN_NAME


def _cache_info(plugin_root: Path, environ: Mapping[str, str]) -> tuple[Path, str] | None:
    resolved = plugin_root.resolve()
    for cache_root in resolved.parents:
        if cache_root.name != "cache" or cache_root.parent.name != "plugins":
            continue
        try:
            relative = resolved.relative_to(cache_root)
        except ValueError:
            return None
        if len(relative.parts) < 3:
            return None
        marketplace_name = relative.parts[0]
        codex_home_raw = environ.get("CODEX_HOME")
        codex_home = (
            Path(_strip_windows_extended_prefix(codex_home_raw)).resolve()
            if codex_home_raw
            else cache_root.parent.parent.resolve()
        )
        return codex_home, marketplace_name
    return None


def _marketplace_source(config_path: Path, marketplace_name: str) -> str | None:
    if not config_path.exists():
        return None
    current_section = ""
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            continue
        if current_section != f"marketplaces.{marketplace_name}" or not line.startswith("source"):
            continue
        key, separator, value = line.partition("=")
        if separator and key.strip() == "source":
            return _unquote_toml_string(value.strip())
    return None


def _unquote_toml_string(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _normalize_source_candidate(candidate: Path) -> Path:
    resolved = candidate.resolve(strict=False)
    if _is_source_repo(resolved):
        return resolved
    if (resolved / ".codex-plugin" / "plugin.json").exists() and len(resolved.parents) >= 2:
        possible_repo = resolved.parents[1]
        if _is_source_repo(possible_repo):
            return possible_repo
    return resolved


def _is_source_repo(path: Path) -> bool:
    return (path / "pyproject.toml").exists() and (path / "src" / "codex_supervisor").is_dir()


def _strip_windows_extended_prefix(value: str) -> str:
    if value.startswith("\\\\?\\"):
        return value[4:]
    return value


def _display_path(path: Path) -> str:
    return f"<path:{path.name or '.'}>"


class _DiagnosticServer:
    def __init__(self, *, diagnostic: str) -> None:
        self.diagnostic = diagnostic
        self.initialized = False
        self.lifecycle_ready = False

    def handle_line(self, line: str) -> JsonObject | None:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            return _error_response(None, -32700, "Parse error", "Invalid JSON.")
        if not isinstance(message, dict):
            return _error_response(None, -32600, "Invalid Request", "Message must be an object.")
        method = message.get("method")
        request_id = message.get("id")
        if "id" not in message:
            if method == "notifications/initialized" and self.initialized:
                self.lifecycle_ready = True
            return None
        if method == "initialize":
            self.initialized = True
            self.lifecycle_ready = False
            return _result_response(
                request_id,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "title": "Codex Supervisor Diagnostic Launcher",
                        "version": "diagnostic",
                    },
                    "instructions": (
                        "Codex Supervisor could not start its real MCP backend. Call "
                        "codex_supervisor.runtime_preflight to see the fail-closed diagnostic."
                    ),
                },
            )
        if method == "ping":
            return _result_response(request_id, {})
        if not self.lifecycle_ready:
            return _error_response(
                request_id,
                -32002,
                "Server not initialized",
                "Call initialize and send notifications/initialized first.",
            )
        if method == "tools/list":
            return _result_response(request_id, {"tools": [_runtime_preflight_tool_definition()]})
        if method == "tools/call":
            return self._handle_tools_call(message.get("params"), request_id)
        return _error_response(request_id, -32601, "Method not found", str(method))

    def _handle_tools_call(self, params: object, request_id: object) -> JsonObject:
        if not isinstance(params, dict):
            return _error_response(
                request_id,
                -32602,
                "Invalid params",
                "params must be an object.",
            )
        tool_name = params.get("name")
        if tool_name != "codex_supervisor.runtime_preflight":
            return _error_response(
                request_id,
                -32601,
                "Method not found",
                f"Unknown diagnostic tool: {tool_name}",
            )
        result = _runtime_preflight_blocked_result(self.diagnostic)
        return _result_response(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, sort_keys=True, separators=(",", ":")),
                    }
                ],
                "structuredContent": result,
                "isError": True,
            },
        )


def _runtime_preflight_tool_definition() -> JsonObject:
    return {
        "name": "codex_supervisor.runtime_preflight",
        "description": (
            "Desktop full-AFK canary and runtime preflight diagnostic for "
            "codex_supervisor.runtime_preflight when the real Codex Supervisor MCP backend "
            "cannot start."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "full_afk": {"type": "boolean"},
                "plugin_invocation": {"type": "boolean"},
                "plugin_full_afk": {"type": "boolean"},
                "supervisor_backend": {
                    "type": "string",
                    "enum": ["mcp", "cli", "unavailable", "skill_only"],
                },
                "mcp_tools": {"type": "array", "items": {"type": "string"}},
                "cli_available": {"type": "boolean"},
                "worker_execution": {
                    "type": "string",
                    "enum": ["codex_exec", "current_thread", "blocked", "manual"],
                },
                "native_goal_mode": {"type": "boolean"},
                "supervisor_task_id": {"type": "string"},
                "goal_contract_linked": {"type": "boolean"},
                "story_loop_status_checked": {"type": "boolean"},
                "task_current_requested": {"type": "boolean"},
                "task_next_afk_requested": {"type": "boolean"},
                "scaffold_tier": {
                    "type": "string",
                    "enum": ["supervisor_managed", "base", "prototype_light", "unknown"],
                },
                "database_mode": {
                    "type": "string",
                    "enum": ["persistent_mongodb", "memory_mongodb", "none", "unknown"],
                },
                "evidence_mode": {
                    "type": "string",
                    "enum": ["strict_jsonl", "degraded_jsonl", "missing"],
                },
                "mutation_policy": {"type": "string", "enum": ["allowed", "read_only"]},
                "setup_mutations": {"type": "array", "items": {"type": "string"}},
                "allow_setup_mutations": {"type": "boolean"},
                "mcp_startup_diagnostic": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    }


def _runtime_preflight_blocked_result(diagnostic: str) -> JsonObject:
    report = {
        "ok": False,
        "status": "blocked",
        "ledger": {
            "entrypoint": "desktop_plugin",
            "required_surface": "live_mcp",
            "decision_source": "diagnostic_mcp_fallback",
            "supervisor_backend": "unavailable",
            "planning_state": "unavailable",
            "worker_execution": "blocked",
            "goal_contract": "missing",
            "project_scaffold": "unknown",
            "database_mode": "unknown",
            "evidence_mode": "unavailable",
            "mutation_policy": "blocked",
            "queue_discovery": "not_requested",
            "setup_policy": "repair_required",
            "mcp_tools_state": "diagnostic_only",
        },
        "issues": [
            {
                "code": "mcp_startup_failed",
                "severity": "blocked",
                "message": diagnostic,
                "next_action": (
                    "Repair the plugin cache, source repo path, uv installation, or PATH before "
                    "treating this as a supervisor run."
                ),
            }
        ],
        "diagnostics": {"mcp_startup_diagnostic": diagnostic},
    }
    return {"ok": False, "tool": "codex_supervisor.runtime_preflight", "data": report}


def _result_response(request_id: object, result: JsonObject) -> JsonObject:
    return {"jsonrpc": JSON_RPC_VERSION, "id": request_id, "result": result}


def _error_response(
    request_id: object,
    code: int,
    message: str,
    detail: str,
) -> JsonObject:
    return {
        "jsonrpc": JSON_RPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message, "data": {"message": detail}},
    }


def _write_json_line(message: JsonObject) -> None:
    sys.stdout.write(json.dumps(message, sort_keys=True, separators=(",", ":")))
    sys.stdout.write("\n")
    sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
