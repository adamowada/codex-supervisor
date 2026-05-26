"""Verify the repo-local Codex Desktop plugin from a clean local profile."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import tomllib
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
        "codex_supervisor.artifact_link_add",
        "codex_supervisor.progress_add",
        "codex_supervisor.runtime_preflight",
        "codex_supervisor.story_loop_status",
        "codex_supervisor.story_loop_run_once",
        "codex_supervisor.task_claim",
        "codex_supervisor.task_show",
        "codex_supervisor.task_upsert",
        "codex_supervisor.review_result_ingest",
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


def verify_codex_plugin_desktop_profile(
    *,
    codex_home: Path,
    runner: Runner | None = None,
    timeout_seconds: int = 30,
) -> JsonObject:
    """Verify the plugin as installed in a real Codex Desktop profile cache."""

    profile = codex_home.resolve()
    plugin_root = _discover_desktop_profile_plugin_root(profile)
    manifest = _load_json_object(plugin_root / MANIFEST_RELATIVE_PATH)
    mcp_path = _manifest_relative_path(plugin_root, manifest, "mcpServers")
    skills_root = _manifest_relative_path(plugin_root, manifest, "skills")
    skill_names = _discover_skills(skills_root)
    mcp_tools = _verify_mcp_stdio(
        plugin_root,
        mcp_path,
        None,
        runner or _default_runner,
        timeout_seconds,
    )
    return {
        "ok": True,
        "plugin": _require_string(manifest, "name"),
        "plugin_source": _profile_relative(profile, plugin_root),
        "desktop_profile_smoke": True,
        "real_codex_home_mutated": False,
        "skills": sorted(skill_names),
        "mcp_tools": sorted(mcp_tools),
    }


def main() -> int:
    """Run the clean plugin install verifier."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--desktop-profile", action="store_true", default=False)
    parser.add_argument("--codex-home", type=Path, default=None)
    args = parser.parse_args()
    try:
        if args.desktop_profile:
            if args.codex_home is None:
                raise PluginInstallVerificationError("--desktop-profile requires --codex-home")
            summary = verify_codex_plugin_desktop_profile(codex_home=args.codex_home)
        else:
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
    repo_root: Path | None,
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

    if _command_uses_plugin_launcher(command, args):
        _raise_if_launcher_is_not_runnable(args, cwd)
    else:
        _raise_if_source_cwd_is_not_runnable(command, args, cwd)
    try:
        completed = runner((command, *args), cwd, payload, timeout_seconds)
    except FileNotFoundError as exc:
        raise PluginInstallVerificationError(
            f"MCP startup failed: program not found: {command}"
        ) from exc
    except OSError as exc:
        raise PluginInstallVerificationError(f"MCP startup failed: {exc}") from exc
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


def _resolve_mcp_cwd(plugin_root: Path, server: JsonObject, repo_root: Path | None) -> Path:
    raw_cwd = _require_string(server, "cwd")
    relative = Path(raw_cwd)
    if relative.is_absolute():
        raise PluginInstallVerificationError("MCP cwd must be relative to the plugin root")
    resolved = (plugin_root / relative).resolve()
    command = _require_string(server, "command")
    args = _require_string_list(server, "args")
    if (
        repo_root is not None
        and resolved != repo_root
        and not _command_uses_plugin_launcher(command, args)
    ):
        raise PluginInstallVerificationError("MCP cwd must resolve to the repository root")
    return resolved


def _raise_if_source_cwd_is_not_runnable(command: str, args: tuple[str, ...], cwd: Path) -> None:
    if not _command_requires_codex_supervisor_source(command, args):
        return
    if (cwd / "pyproject.toml").exists() and (cwd / "src" / "codex_supervisor").is_dir():
        return
    raise PluginInstallVerificationError(
        f"MCP startup failed: cwd does not contain the codex_supervisor source package: {cwd}"
    )


def _raise_if_launcher_is_not_runnable(args: tuple[str, ...], cwd: Path) -> None:
    launcher_path = _launcher_argument(args)
    if launcher_path is None:
        raise PluginInstallVerificationError(
            "MCP launcher command must name scripts/mcp_launcher.py"
        )
    if not (cwd / launcher_path).is_file():
        raise PluginInstallVerificationError(f"MCP launcher script is missing: {launcher_path}")


def _command_requires_codex_supervisor_source(command: str, args: tuple[str, ...]) -> bool:
    return (
        command == "uv" and "run" in args and "-m" in args and "codex_supervisor.mcp_stdio" in args
    )


def _command_uses_plugin_launcher(command: str, args: tuple[str, ...]) -> bool:
    return command == "python" and _launcher_argument(args) is not None


def _launcher_argument(args: tuple[str, ...]) -> Path | None:
    for item in args:
        normalized = item.replace("\\", "/")
        if normalized == "scripts/mcp_launcher.py":
            return Path(item)
    return None


def _discover_desktop_profile_plugin_root(codex_home: Path) -> Path:
    if not codex_home.exists():
        raise PluginInstallVerificationError(f"Codex home does not exist: {codex_home}")
    marketplace_names = _enabled_marketplace_names(codex_home / "config.toml")
    cache_root = codex_home / "plugins" / "cache"
    candidates: list[Path] = []
    for marketplace in marketplace_names:
        candidates.extend(sorted((cache_root / marketplace / "codex-supervisor").glob("*")))
    if not candidates:
        candidates.extend(sorted(cache_root.glob("*/codex-supervisor/*")))
    plugin_roots = tuple(
        candidate for candidate in candidates if (candidate / MANIFEST_RELATIVE_PATH).exists()
    )
    if not plugin_roots:
        raise PluginInstallVerificationError(
            f"No installed codex-supervisor plugin cache found under {cache_root}"
        )
    return plugin_roots[-1].resolve()


def _enabled_marketplace_names(config_path: Path) -> tuple[str, ...]:
    if not config_path.exists():
        return ()
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise PluginInstallVerificationError(f"invalid Codex config TOML: {exc}") from exc
    plugins = payload.get("plugins")
    if not isinstance(plugins, dict):
        return ()
    marketplaces = []
    for key, value in plugins.items():
        if (
            isinstance(key, str)
            and key.startswith("codex-supervisor@")
            and isinstance(value, dict)
            and value.get("enabled") is True
        ):
            marketplaces.append(key.split("@", 1)[1])
    return tuple(marketplaces)


def _profile_relative(profile: Path, path: Path) -> str:
    try:
        return path.relative_to(profile).as_posix()
    except ValueError:
        return "<outside-codex-home>"


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
