"""Verify the repo-local Codex Desktop plugin from a clean local profile."""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]
Runner = Callable[[Sequence[str], Path, str, int], subprocess.CompletedProcess[str]]

PLUGIN_RELATIVE_PATH = Path("plugins") / "codex-supervisor"
MANIFEST_RELATIVE_PATH = Path(".codex-plugin") / "plugin.json"
MCP_PROTOCOL_VERSION = "2025-11-25"
REQUIRED_MCP_TOOLS = frozenset(
    {
        "codex_supervisor.story_loop_status",
        "codex_supervisor.task_show",
    }
)


class PluginInstallVerificationError(RuntimeError):
    """Raised when the plugin cannot be discovered from a clean local profile."""


def verify_codex_plugin_install(
    *,
    repo_root: Path | None = None,
    plugin_root: Path | None = None,
    runner: Runner | None = None,
    timeout_seconds: int = 30,
) -> JsonObject:
    """Verify plugin discovery and MCP startup without touching real Codex state."""

    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    source = (plugin_root or root / PLUGIN_RELATIVE_PATH).resolve()
    command_runner = runner or _default_runner

    with tempfile.TemporaryDirectory(prefix="codex-supervisor-plugin-") as temp_root:
        clean_root = Path(temp_root)
        clean_codex_home = clean_root / "codex-home"
        clean_project = clean_root / "fresh-project"
        clean_codex_home.mkdir()
        clean_project.mkdir()

        manifest = _load_json_object(source / MANIFEST_RELATIVE_PATH)
        mcp_path = _manifest_relative_path(source, manifest, "mcpServers")
        skills_root = _manifest_relative_path(source, manifest, "skills")
        skill_names = _discover_skills(skills_root)
        mcp_tools = _verify_mcp_stdio(source, mcp_path, root, command_runner, timeout_seconds)

        return {
            "ok": True,
            "plugin": _require_string(manifest, "name"),
            "plugin_source": PLUGIN_RELATIVE_PATH.as_posix(),
            "clean_profile_isolated": clean_codex_home.exists() and clean_project.exists(),
            "real_codex_home_mutated": False,
            "skills": sorted(skill_names),
            "mcp_tools": sorted(mcp_tools),
        }


def main() -> int:
    """Run the clean plugin install verifier."""

    try:
        summary = verify_codex_plugin_install()
    except PluginInstallVerificationError as exc:
        print(f"Plugin install verification failed: {exc}")
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _default_runner(
    command: Sequence[str],
    cwd: Path,
    payload: str,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        tuple(command),
        cwd=cwd,
        input=payload,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )


def _load_json_object(path: Path) -> JsonObject:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PluginInstallVerificationError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PluginInstallVerificationError(f"invalid JSON in {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise PluginInstallVerificationError(f"{path} must contain a JSON object")
    return payload


def _manifest_relative_path(plugin_root: Path, manifest: JsonObject, key: str) -> Path:
    raw_value = _require_string(manifest, key)
    relative = Path(raw_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise PluginInstallVerificationError(f"manifest {key} must stay inside the plugin")
    resolved = (plugin_root / relative).resolve()
    try:
        resolved.relative_to(plugin_root)
    except ValueError as exc:
        raise PluginInstallVerificationError(f"manifest {key} resolves outside the plugin") from exc
    if not resolved.exists():
        raise PluginInstallVerificationError(f"manifest {key} path does not exist: {raw_value}")
    return resolved


def _discover_skills(skills_root: Path) -> tuple[str, ...]:
    skill_files = sorted(skills_root.glob("*/SKILL.md"))
    if not skill_files:
        raise PluginInstallVerificationError("plugin skills directory contains no skills")
    skill_names = []
    for skill_file in skill_files:
        frontmatter = _skill_frontmatter(skill_file)
        name = _frontmatter_value(frontmatter, "name")
        description = _frontmatter_value(frontmatter, "description")
        if not name or not description:
            raise PluginInstallVerificationError(f"{skill_file} needs name and description")
        skill_names.append(name)
    return tuple(skill_names)


def _skill_frontmatter(skill_file: Path) -> str:
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise PluginInstallVerificationError(f"{skill_file} is missing YAML frontmatter")
    frontmatter_end = text.find("\n---", 4)
    if frontmatter_end < 0:
        raise PluginInstallVerificationError(f"{skill_file} frontmatter is not closed")
    return text[4:frontmatter_end]


def _frontmatter_value(frontmatter: str, key: str) -> str:
    prefix = f"{key}:"
    for line in frontmatter.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _verify_mcp_stdio(
    plugin_root: Path,
    mcp_path: Path,
    repo_root: Path,
    runner: Runner,
    timeout_seconds: int,
) -> tuple[str, ...]:
    mcp = _load_json_object(mcp_path)
    servers = mcp.get("mcpServers")
    if not isinstance(servers, dict) or set(servers) != {"codex-supervisor"}:
        raise PluginInstallVerificationError("MCP config must expose one codex-supervisor server")
    server = servers["codex-supervisor"]
    if not isinstance(server, dict):
        raise PluginInstallVerificationError("codex-supervisor MCP server must be an object")
    command = _require_string(server, "command")
    args = _require_string_list(server, "args")
    cwd = _resolve_mcp_cwd(plugin_root, server, repo_root)
    payload = _mcp_lifecycle_payload()

    completed = runner((command, *args), cwd, payload, timeout_seconds)
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "no stderr"
        raise PluginInstallVerificationError(f"MCP stdio command failed: {stderr}")
    responses = _parse_json_lines(completed.stdout)
    if [response.get("id") for response in responses] != ["install-init", "tools-list"]:
        raise PluginInstallVerificationError("MCP stdio lifecycle returned unexpected responses")
    tools_result = responses[1].get("result")
    if not isinstance(tools_result, dict):
        raise PluginInstallVerificationError("MCP tools/list result must be an object")
    tools = tools_result.get("tools")
    if not isinstance(tools, list):
        raise PluginInstallVerificationError("MCP tools/list result must include tools")
    tool_names: list[str] = []
    for tool in tools:
        if isinstance(tool, dict):
            tool_name = tool.get("name")
            if isinstance(tool_name, str):
                tool_names.append(tool_name)
    missing_tools = REQUIRED_MCP_TOOLS - set(tool_names)
    if missing_tools:
        missing = ", ".join(sorted(missing_tools))
        raise PluginInstallVerificationError(f"MCP tools/list missing expected tools: {missing}")
    return tuple(tool_names)


def _resolve_mcp_cwd(plugin_root: Path, server: JsonObject, repo_root: Path) -> Path:
    raw_cwd = _require_string(server, "cwd")
    relative = Path(raw_cwd)
    if relative.is_absolute():
        raise PluginInstallVerificationError("MCP cwd must be relative to the plugin root")
    resolved = (plugin_root / relative).resolve()
    if resolved != repo_root:
        raise PluginInstallVerificationError("MCP cwd must resolve to the repository root")
    return resolved


def _mcp_lifecycle_payload() -> str:
    messages = [
        {
            "jsonrpc": "2.0",
            "id": "install-init",
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "clean-plugin-smoke", "version": "1.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": "tools-list", "method": "tools/list"},
    ]
    return "\n".join(json.dumps(message, sort_keys=True) for message in messages) + "\n"


def _parse_json_lines(output: str) -> list[JsonObject]:
    responses = []
    for line in output.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PluginInstallVerificationError("MCP stdio emitted non-JSON output") from exc
        if not isinstance(payload, dict):
            raise PluginInstallVerificationError("MCP stdio response must be a JSON object")
        responses.append(payload)
    return responses


def _require_string(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PluginInstallVerificationError(f"{key} must be a nonblank string")
    return value


def _require_string_list(payload: JsonObject, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise PluginInstallVerificationError(f"{key} must be a list")
    strings = tuple(item for item in value if isinstance(item, str) and item.strip())
    if len(strings) != len(value):
        raise PluginInstallVerificationError(f"{key} entries must be nonblank strings")
    return strings


if __name__ == "__main__":
    raise SystemExit(main())
