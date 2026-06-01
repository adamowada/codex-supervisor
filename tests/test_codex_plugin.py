from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from planning_db_factory import make_planning_db

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
    assert "full AFK" in content
    assert "`--assurance high`" in content
    assert "MUST use the plugin CLI launcher" in content
    assert "MUST default to the current workspace ledger" in content
    assert "MUST NOT run `queue-next` before `plan-init`" in content
    assert "MUST** follow [WINDOWS.md](WINDOWS.md)" in content
    assert ".codex-supervisor/verify.py" in content
    assert "CODEX_SUPERVISOR_TASK_JSON" in content
    assert "MUST NOT mutate product files directly" in content
    assert "Verifier checks **MUST** prove behavior or structural contract" in content
    assert "MUST NOT** depend on local implementation names" in content
    assert "Literal string checks **MUST** only be used" in content


def test_plugin_contains_windows_platform_guidance() -> None:
    guidance = PLUGIN_ROOT / "skills" / "codex-supervisor" / "WINDOWS.md"
    content = guidance.read_text(encoding="utf-8")

    assert "powershell.exe -NoProfile -ExecutionPolicy Bypass -File <codex.ps1> exec" in content
    assert "MUST NOT** put complex PowerShell logic inline in `--verify-command`" in content
    assert "MUST** prefer a workspace Python verifier" in content
    assert "python -B .codex-supervisor\\verify.py" in content
    assert "MUST** retry the same task" in content


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


def test_plugin_mcp_queue_requires_explicit_planning_path() -> None:
    responses = _run_plugin_launcher(
        (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "codex_supervisor.queue_next",
                    "arguments": {},
                },
            },
        )
    )

    tool_result = responses[1]["result"]
    structured = tool_result["structuredContent"]
    assert tool_result["isError"] is True
    assert structured["ok"] is False
    assert structured["error"]["code"] == "planning_path_required"


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


def test_installed_cache_mcp_launcher_dispatches_workspace_queue(
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
    workspace_db = make_planning_db(tmp_path / "workspace")
    source_db = REPO_ROOT / "plans" / "planning.sqlite3"
    source_before = source_db.read_bytes()
    shutil.copytree(PLUGIN_ROOT, cached_plugin)
    _write_codex_config(codex_home)

    responses = _run_plugin_launcher_from(
        cached_plugin,
        (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "codex_supervisor.queue_next",
                    "arguments": {},
                },
            },
        ),
        codex_home=codex_home,
        include_source_env=False,
        planning_path=workspace_db,
    )

    structured = responses[1]["result"]["structuredContent"]
    assert structured["ok"] is True
    assert structured["data"]["task"]["task_id"] == "task-1"
    assert source_db.read_bytes() == source_before


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

    initialized = _run_plugin_cli_launcher_from(
        cached_plugin,
        ("plan-init", "--path", str(db_path), "--json"),
        codex_home=codex_home,
        include_source_env=False,
    )
    init_payload = json.loads(initialized.stdout)
    assert init_payload == {
        "initialized": True,
        "path": str(db_path),
        "schema_name": "fresh_simplified_planning",
        "schema_version": "1",
    }
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

    initialized = _run_plugin_cli_launcher_from(
        cached_plugin,
        ("plan-init", "--json"),
        codex_home=codex_home,
        include_source_env=False,
        invocation_cwd=workspace,
    )
    init_payload = json.loads(initialized.stdout)
    assert init_payload == {
        "initialized": True,
        "path": str(workspace_db),
        "schema_name": "fresh_simplified_planning",
        "schema_version": "1",
    }
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


def test_installed_cache_cli_launcher_runs_full_happy_path_in_fresh_workspace(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    workspace = tmp_path / "fresh-worker-workspace"
    workspace.mkdir()
    workspace_db = workspace / ".codex-supervisor" / "planning.sqlite3"
    project_file = workspace / "README.md"
    verifier_file = workspace / ".codex-supervisor" / "verify.py"
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
    _run_plugin_cli_launcher_from(
        cached_plugin,
        (
            "task-create",
            "--plan-id",
            "plugin-happy-plan",
            "--plan-title",
            "Plugin happy path",
            "--plan-goal",
            "Assign one tiny project through the plugin launcher.",
            "--task-id",
            "plugin-happy-task",
            "--title",
            "Create README",
            "--intent",
            "Create README.md in the fresh workspace.",
            "--assurance",
            "high",
            "--acceptance",
            "README.md exists",
            "--json",
        ),
        codex_home=codex_home,
        include_source_env=False,
        invocation_cwd=workspace,
    )
    _write_readme_verifier(verifier_file, expected="# Plugin Happy Path\n")
    completed = _run_plugin_cli_launcher_from(
        cached_plugin,
        (
            "attempt-run",
            "--task-id",
            "plugin-happy-task",
            "--attempt-id",
            "plugin-happy-attempt",
            "--executor",
            "worker-process",
            "--workspace",
            str(workspace),
            "--timeout-seconds",
            "10",
            "--summary",
            "Assign README creation to worker process.",
            "--check",
            "Worker created README.md.",
            "--artifact",
            str(project_file),
            "--verify-command",
            _shell_command((sys.executable, "-B", str(verifier_file))),
            "--acceptance-result",
            "pass",
            "--risk",
            "Worker ran inside the invocation workspace.",
            "--json",
            "--",
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "Path('README.md').write_text('# Plugin Happy Path\\n', encoding='utf-8')"
            ),
        ),
        codex_home=codex_home,
        include_source_env=False,
        invocation_cwd=workspace,
    )

    payload = json.loads(completed.stdout)
    assert workspace_db.is_file()
    assert payload["exit_code"] == 0
    assert payload["verifier_exit_code"] == 0
    assert payload["transition"]["task_status"] == "done"
    assert payload["transition"]["attempt"]["executor"] == "worker-process"
    assert "verifier exit code: 0" in payload["transition"]["evidence"]["checks"]
    assert Path(payload["assignment_path"]).is_file()
    assert project_file.read_text(encoding="utf-8") == "# Plugin Happy Path\n"
    assert source_db.read_bytes() == source_before

    with sqlite3.connect(workspace_db) as connection:
        plan_status = connection.execute(
            "select status from plans where plan_id = 'plugin-happy-plan'"
        ).fetchone()[0]
        attempts = connection.execute(
            "select attempt_id, executor, status from attempts"
        ).fetchall()
    assert plan_status == "done"
    assert attempts == [("plugin-happy-attempt", "worker-process", "succeeded")]
    assert _planning_integrity_failures(workspace_db) == ()


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
    planning_path: Path | None = None,
) -> list[dict[str, object]]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    if include_source_env:
        env["CODEX_SUPERVISOR_REPO_ROOT"] = str(REPO_ROOT)
    else:
        env.pop("CODEX_SUPERVISOR_REPO_ROOT", None)
    if planning_path is not None:
        env["CODEX_SUPERVISOR_PLANNING_PATH"] = str(planning_path)
    else:
        env.pop("CODEX_SUPERVISOR_PLANNING_PATH", None)
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


def _write_readme_verifier(path: Path, *, expected: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                "from pathlib import Path",
                "expected = " + repr(expected),
                "content = Path('README.md').read_text(encoding='utf-8')",
                "if content != expected:",
                "    raise SystemExit('README.md content mismatch')",
                "print('README.md verified')",
                "",
            )
        ),
        encoding="utf-8",
    )


def _shell_command(args: tuple[str, ...]) -> str:
    return subprocess.list2cmdline(args)


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


def _planning_integrity_failures(db_path: Path) -> tuple[str, ...]:
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.check_planning_integrity import check_planning_integrity

    return check_planning_integrity(db_path)
