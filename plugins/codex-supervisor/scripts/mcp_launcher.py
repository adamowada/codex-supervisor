"""Launch the compact codex-supervisor MCP server from a plugin install."""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path

PLUGIN_NAME = "codex-supervisor"
SOURCE_ENV_VAR = "CODEX_SUPERVISOR_REPO_ROOT"


def main() -> int:
    plugin_root = Path(__file__).resolve().parents[1]
    repo_root = find_repo_root(plugin_root, os.environ)
    if repo_root is None:
        print(
            "Could not locate codex-supervisor source repo. "
            f"Set {SOURCE_ENV_VAR} to the repo root before starting the plugin.",
            file=sys.stderr,
        )
        return 1
    command = (
        "uv",
        "run",
        "--no-sync",
        "python",
        "-B",
        "-m",
        "codex_supervisor.mcp_stdio",
    )
    try:
        completed = subprocess.run(command, cwd=repo_root, check=False)
    except FileNotFoundError:
        print("Could not start codex-supervisor MCP: uv is not on PATH.", file=sys.stderr)
        return 1
    return completed.returncode


def find_repo_root(plugin_root: Path, environ: Mapping[str, str]) -> Path | None:
    """Find the source repo for source-layout and env-configured plugin runs."""

    for candidate in _repo_root_candidates(plugin_root, environ):
        if _is_repo_root(candidate):
            return candidate.resolve()
    return None


def _repo_root_candidates(plugin_root: Path, environ: Mapping[str, str]) -> Iterable[Path]:
    env_root = environ.get(SOURCE_ENV_VAR)
    if env_root:
        yield Path(_strip_windows_extended_prefix(env_root))
    yield plugin_root.parents[1]
    yield Path.cwd()
    yield from Path.cwd().parents

    cache_info = _cache_info(plugin_root, environ)
    if cache_info is None:
        return
    codex_home, marketplace_name = cache_info
    source = _marketplace_source(codex_home / "config.toml", marketplace_name)
    if source is None:
        return
    yield source
    yield source / "plugins" / PLUGIN_NAME


def _is_repo_root(candidate: Path) -> bool:
    return (
        (candidate / "pyproject.toml").is_file()
        and (candidate / "src" / "codex_supervisor").is_dir()
        and (candidate / "plans" / "planning.sqlite3").is_file()
    )


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
        codex_home = Path(
            _strip_windows_extended_prefix(
                environ.get("CODEX_HOME", str(cache_root.parent.parent))
            )
        )
        return codex_home, relative.parts[0]
    return None


def _marketplace_source(config_path: Path, marketplace_name: str) -> Path | None:
    if not config_path.is_file():
        return None
    with config_path.open("rb") as handle:
        config = tomllib.load(handle)
    marketplace = config.get("marketplaces", {}).get(marketplace_name, {})
    source = marketplace.get("source")
    if not isinstance(source, str) or not source.strip():
        return None
    return Path(_strip_windows_extended_prefix(source.strip()))


def _strip_windows_extended_prefix(value: str) -> str:
    if value.startswith("\\\\?\\"):
        return value[4:]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
