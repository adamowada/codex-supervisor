from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-supervisor"


def test_plugin_manifest_declares_compact_mcp_wrapper() -> None:
    manifest = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text())
    mcp_config = json.loads((PLUGIN_ROOT / ".mcp.json").read_text())

    assert manifest["name"] == "codex-supervisor"
    assert manifest["version"].startswith("0.2.0")
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert manifest["interface"]["capabilities"] == ["Interactive", "Read"]
    server = mcp_config["mcpServers"]["codex-supervisor"]
    assert server == {
        "command": "python",
        "args": ["-B", "scripts/mcp_launcher.py"],
        "cwd": ".",
    }


def test_plugin_contains_desktop_skill_entrypoint() -> None:
    skill = PLUGIN_ROOT / "skills" / "codex-supervisor" / "SKILL.md"
    content = skill.read_text(encoding="utf-8")

    assert "name: codex-supervisor" in content
    assert "TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision" in content
    assert "MUST create durable task intent" in content
    assert "MUST record a run attempt" in content
    assert "plan-init" in content
    assert "attempt-run" in content
    assert "MUST use `attempt-run`" in content
    assert "MUST use the plugin CLI launcher" in content
    assert "MUST default to the current workspace ledger" in content
    assert "MUST NOT run `queue-next` before `plan-init`" in content
    assert "CODEX_SUPERVISOR_TASK_JSON" in content


def test_repo_marketplace_points_at_plugin_wrapper() -> None:
    marketplace = json.loads((REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text())

    assert marketplace["name"] == "codex-supervisor-local"
    assert marketplace["plugins"] == [
        {
            "name": "codex-supervisor",
            "source": {
                "source": "local",
                "path": "./plugins/codex-supervisor",
            },
            "policy": {
                "installation": "AVAILABLE",
                "authentication": "ON_INSTALL",
            },
            "category": "Developer Tools",
        }
    ]


def test_plugin_launcher_starts_compact_mcp_server() -> None:
    responses = _run_plugin_launcher(
        (
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25"},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
    )

    assert responses[0]["result"]["serverInfo"]["name"] == "codex-supervisor"
    assert responses[1]["result"]["tools"][0]["name"] == "codex_supervisor.queue_next"


def test_installed_cache_launcher_uses_configured_marketplace_without_env(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    cached_plugin = (
        codex_home
        / "plugins"
        / "cache"
        / "codex-supervisor-local"
        / "codex-supervisor"
        / "0.2.0+codex.test"
    )
    shutil.copytree(PLUGIN_ROOT, cached_plugin)
    _write_codex_config(codex_home)

    responses = _run_plugin_launcher_from(
        cached_plugin,
        (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ),
        codex_home=codex_home,
        include_source_env=False,
    )

    assert responses[0]["result"]["serverInfo"]["name"] == "codex-supervisor"
    assert responses[1]["result"]["tools"][0]["name"] == "codex_supervisor.queue_next"


def test_installed_cache_cli_launcher_runs_source_cli_without_path(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    cached_plugin = (
        codex_home
        / "plugins"
        / "cache"
        / "codex-supervisor-local"
        / "codex-supervisor"
        / "0.2.0+codex.test"
    )
    db_path = tmp_path / "empty-workspace" / ".codex-supervisor" / "planning.sqlite3"
    shutil.copytree(PLUGIN_ROOT, cached_plugin)
    _write_codex_config(codex_home)

    _run_plugin_cli_launcher_from(
        cached_plugin,
        ("plan-init", "--path", str(db_path)),
        codex_home=codex_home,
        include_source_env=False,
    )
    completed = _run_plugin_cli_launcher_from(
        cached_plugin,
        ("queue-next", "--path", str(db_path), "--json"),
        codex_home=codex_home,
        include_source_env=False,
    )

    payload = json.loads(completed.stdout)
    assert payload["task"] is None
    assert payload["next_transition"] == "none"


def test_installed_cache_cli_launcher_defaults_to_invocation_workspace(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    workspace = tmp_path / "fresh-workspace"
    workspace.mkdir()
    workspace_db = workspace / ".codex-supervisor" / "planning.sqlite3"
    source_db = REPO_ROOT / "plans" / "planning.sqlite3"
    source_before = source_db.read_bytes()
    cached_plugin = (
        codex_home
        / "plugins"
        / "cache"
        / "codex-supervisor-local"
        / "codex-supervisor"
        / "0.2.0+codex.test"
    )
    shutil.copytree(PLUGIN_ROOT, cached_plugin)
    _write_codex_config(codex_home)

    _run_plugin_cli_launcher_from(
        cached_plugin,
        ("plan-init",),
        codex_home=codex_home,
        include_source_env=False,
        invocation_cwd=workspace,
    )
    completed = _run_plugin_cli_launcher_from(
        cached_plugin,
        ("queue-next", "--json"),
        codex_home=codex_home,
        include_source_env=False,
        invocation_cwd=workspace,
    )

    payload = json.loads(completed.stdout)
    assert workspace_db.is_file()
    assert payload["task"] is None
    assert payload["next_transition"] == "none"
    assert source_db.read_bytes() == source_before


def _run_plugin_launcher(messages: tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    return _run_plugin_launcher_from(
        PLUGIN_ROOT,
        messages,
        codex_home=Path.home() / ".codex",
        include_source_env=True,
    )


def _run_plugin_launcher_from(
    plugin_root: Path,
    messages: tuple[dict[str, object], ...],
    *,
    codex_home: Path,
    include_source_env: bool,
) -> list[dict[str, object]]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    if include_source_env:
        env["CODEX_SUPERVISOR_REPO_ROOT"] = str(REPO_ROOT)
    else:
        env.pop("CODEX_SUPERVISOR_REPO_ROOT", None)
    completed = subprocess.run(
        (sys.executable, "-B", "scripts/mcp_launcher.py"),
        cwd=plugin_root,
        input="".join(json.dumps(message) + "\n" for message in messages),
        text=True,
        capture_output=True,
        timeout=15,
        env=env,
        check=True,
    )
    return [json.loads(line) for line in completed.stdout.splitlines()]


def _run_plugin_cli_launcher_from(
    plugin_root: Path,
    args: tuple[str, ...],
    *,
    codex_home: Path,
    include_source_env: bool,
    invocation_cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    env["PATH"] = os.pathsep.join(
        part for part in env.get("PATH", "").split(os.pathsep) if "codex-supervisor" not in part
    )
    if include_source_env:
        env["CODEX_SUPERVISOR_REPO_ROOT"] = str(REPO_ROOT)
    else:
        env.pop("CODEX_SUPERVISOR_REPO_ROOT", None)
    launcher = plugin_root / "scripts" / "cli_launcher.py"
    return subprocess.run(
        (sys.executable, "-B", str(launcher), *args),
        cwd=invocation_cwd or plugin_root,
        text=True,
        capture_output=True,
        timeout=15,
        env=env,
        check=True,
    )


def _write_codex_config(codex_home: Path) -> None:
    codex_home.mkdir(parents=True, exist_ok=True)
    repo_root = str(REPO_ROOT).replace("'", "''")
    (codex_home / "config.toml").write_text(
        "\n".join(
            (
                "[marketplaces.codex-supervisor-local]",
                'source_type = "local"',
                f"source = '{repo_root}'",
                "",
            )
        ),
        encoding="utf-8",
    )
