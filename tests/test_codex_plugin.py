from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

from scripts.verify_codex_plugin_install import (
    verify_codex_plugin_desktop_profile,
    verify_codex_plugin_install,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-supervisor"
PLUGIN_VERSION = "0.1.3"
MANIFEST_PATH = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
MCP_PATH = PLUGIN_ROOT / ".mcp.json"
README_PATH = PLUGIN_ROOT / "README.md"
LAUNCHER_PATH = PLUGIN_ROOT / "scripts" / "mcp_launcher.py"
SKILL_PATH = PLUGIN_ROOT / "skills" / "codex-supervisor" / "SKILL.md"


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _load_launcher_module():
    spec = importlib.util.spec_from_file_location("codex_supervisor_plugin_launcher", LAUNCHER_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_plugin_manifest_describes_stage12_desktop_surface() -> None:
    manifest = _load_json(MANIFEST_PATH)

    assert manifest["name"] == "codex-supervisor"
    assert manifest["version"] == PLUGIN_VERSION
    assert manifest["mcpServers"] == "./.mcp.json"
    assert manifest["skills"] == "./skills/"
    assert "apps" not in manifest
    assert manifest["repository"] == "https://github.com/adamowada/codex-supervisor"

    interface = manifest["interface"]
    assert isinstance(interface, dict)
    assert interface["displayName"] == "Codex Supervisor"
    assert interface["category"] == "Developer Tools"
    assert interface["capabilities"] == ["Interactive", "Read", "Write"]
    assert interface["websiteURL"] == "https://github.com/adamowada/codex-supervisor"
    assert interface["brandColor"] == "#2563EB"

    prompts = interface["defaultPrompt"]
    assert isinstance(prompts, list)
    assert 1 <= len(prompts) <= 3
    assert all(isinstance(prompt, str) and 0 < len(prompt) <= 128 for prompt in prompts)


def test_mcp_config_launches_repo_stdio_server_without_live_worker() -> None:
    mcp = _load_json(MCP_PATH)
    servers = mcp["mcpServers"]
    assert isinstance(servers, dict)
    assert set(servers) == {"codex-supervisor"}

    server = servers["codex-supervisor"]
    assert isinstance(server, dict)
    assert server["command"] == "python"
    assert server["args"] == [
        "-B",
        "scripts/mcp_launcher.py",
    ]
    assert server["cwd"] == "."
    assert (PLUGIN_ROOT / str(server["cwd"])).resolve() == PLUGIN_ROOT.resolve()

    serialized = json.dumps(server, sort_keys=True)
    assert "codex exec" not in serialized
    assert "worker" not in serialized.lower()
    assert "--disable-mutations" not in serialized


def test_plugin_docs_name_desktop_roles_and_queue_authority() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    required_phrases = [
        "codex_supervisor.mcp_stdio",
        "scripts/mcp_launcher.py",
        "uv run --no-sync python -B -m codex_supervisor.mcp_stdio",
        "uv run --no-sync python -B scripts/verify_codex_plugin_install.py",
        "--desktop-profile",
        "skills/codex-supervisor/SKILL.md",
        "plans/planning.sqlite3",
        "HANDOFF.md",
        ".agents/skills/",
        "Project bootstrap",
        "Queue inspection",
        "Worker launch",
        "Review",
        "ACP",
        "Handoff",
        "does not publish a marketplace entry",
        "mutating MCP tools are enabled by default",
        "--disable-mutations",
    ]
    for phrase in required_phrases:
        assert phrase in readme


def test_plugin_skill_is_valid_and_maps_desktop_workflows() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert skill.startswith("---\n")
    frontmatter_end = skill.find("\n---", 4)
    assert frontmatter_end > 0
    frontmatter = skill[4:frontmatter_end]
    assert "name: codex-supervisor" in frontmatter
    assert "description:" in frontmatter

    required_phrases = [
        "plans/planning.sqlite3",
        "MCP tools for inspection and guarded mutation",
        "uv run --no-sync python -B -m codex_supervisor.cli",
        ".agents/skills/skill-router/SKILL.md",
        "spawned-project-bootstrap",
        "setup-agent-docs",
        "story-loop-status --json",
        "goal-contract-render --task-id",
        "task-claim",
        "Runtime canary",
        "canonical dotted MCP tool names",
        "Treat `tool_search` as discovery, not inventory",
        "search for `canary`",
        "name-only queries such as",
        "Do not pass `tool_search` results as authoritative `mcp_tools`",
        "`mcp_startup_diagnostic` merely because",
        "must not approve plugin full-AFK readiness",
        "fresh-thread-code-reviewer",
        "review-result-ingest",
        "acp-publisher",
        "context-compaction-handoff",
        "thread-resume-brief",
    ]
    for phrase in required_phrases:
        assert phrase in skill


def test_plugin_files_do_not_contain_placeholders_or_absolute_local_paths() -> None:
    plugin_files = [
        MANIFEST_PATH,
        MCP_PATH,
        README_PATH,
        LAUNCHER_PATH,
        SKILL_PATH,
    ]
    for path in plugin_files:
        text = path.read_text(encoding="utf-8")
        assert "[TODO:" not in text
        for forbidden in ("C:" + "\\Users", "/" + "Users" + "/"):
            assert forbidden not in text


def test_clean_plugin_install_verifier_discovers_skill_and_mcp_lifecycle() -> None:
    captured: dict[str, object] = {}

    def fake_runner(
        command: tuple[str, ...],
        cwd: Path,
        payload: str,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["cwd"] = cwd
        captured["payload"] = payload
        captured["timeout_seconds"] = timeout_seconds
        stdout = "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": "install-init", "result": {}}),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "tools-list",
                        "result": {
                            "tools": [
                                {"name": "codex_supervisor.artifact_link_add"},
                                {"name": "codex_supervisor.progress_add"},
                                {"name": "codex_supervisor.runtime_preflight"},
                                {"name": "codex_supervisor.story_loop_status"},
                                {"name": "codex_supervisor.story_loop_run_once"},
                                {"name": "codex_supervisor.task_claim"},
                                {"name": "codex_supervisor.task_show"},
                                {"name": "codex_supervisor.task_upsert"},
                                {"name": "codex_supervisor.review_result_ingest"},
                            ]
                        },
                    }
                ),
            ]
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    summary = verify_codex_plugin_install(repo_root=REPO_ROOT, runner=fake_runner)

    assert summary["ok"] is True
    assert summary["plugin"] == "codex-supervisor"
    assert summary["plugin_source"] == "plugins/codex-supervisor"
    assert summary["clean_profile_isolated"] is True
    assert summary["real_codex_home_mutated"] is False
    assert summary["skills"] == ["codex-supervisor"]
    assert "codex_supervisor.story_loop_status" in summary["mcp_tools"]
    assert captured["command"] == (
        "python",
        "-B",
        "scripts/mcp_launcher.py",
    )
    assert captured["cwd"] == PLUGIN_ROOT
    payload = str(captured["payload"])
    assert '"method": "initialize"' in payload
    assert '"method": "tools/list"' in payload


def test_desktop_profile_smoke_discovers_installed_cache_and_tools(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    plugin_root = (
        codex_home
        / "plugins"
        / "cache"
        / "codex-supervisor-local"
        / "codex-supervisor"
        / PLUGIN_VERSION
    )
    repo_root = tmp_path / "source-repo"
    plugin_root.mkdir(parents=True)
    repo_root.mkdir()
    (repo_root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (repo_root / "src" / "codex_supervisor").mkdir(parents=True)
    (repo_root / "src" / "codex_supervisor" / "__init__.py").write_text("", encoding="utf-8")
    (codex_home / "config.toml").write_text(
        '[plugins."codex-supervisor@codex-supervisor-local"]\nenabled = true\n',
        encoding="utf-8",
    )
    (plugin_root / ".codex-plugin").mkdir()
    (plugin_root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "codex-supervisor",
                "mcpServers": "./.mcp.json",
                "skills": "./skills/",
            }
        ),
        encoding="utf-8",
    )
    launcher_dir = plugin_root / "scripts"
    launcher_dir.mkdir()
    (launcher_dir / "mcp_launcher.py").write_text("# launcher fixture\n", encoding="utf-8")
    (plugin_root / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "codex-supervisor": {
                        "command": "python",
                        "args": [
                            "-B",
                            "scripts/mcp_launcher.py",
                        ],
                        "cwd": ".",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    skill_dir = plugin_root / "skills" / "codex-supervisor"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: codex-supervisor\ndescription: Desktop supervisor.\n---\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_runner(
        command: tuple[str, ...],
        cwd: Path,
        payload: str,
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        captured["cwd"] = cwd
        stdout = "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": "install-init", "result": {}}),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "tools-list",
                        "result": {
                            "tools": [
                                {"name": "codex_supervisor.artifact_link_add"},
                                {"name": "codex_supervisor.progress_add"},
                                {"name": "codex_supervisor.runtime_preflight"},
                                {"name": "codex_supervisor.story_loop_status"},
                                {"name": "codex_supervisor.story_loop_run_once"},
                                {"name": "codex_supervisor.task_claim"},
                                {"name": "codex_supervisor.task_show"},
                                {"name": "codex_supervisor.task_upsert"},
                                {"name": "codex_supervisor.review_result_ingest"},
                            ]
                        },
                    }
                ),
            ]
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    summary = verify_codex_plugin_desktop_profile(codex_home=codex_home, runner=fake_runner)

    assert summary["ok"] is True
    assert summary["desktop_profile_smoke"] is True
    assert summary["plugin_source"].startswith("plugins/cache/codex-supervisor-local")
    assert "codex_supervisor.runtime_preflight" in summary["mcp_tools"]
    assert captured["cwd"] == plugin_root.resolve()


def test_plugin_launcher_resolves_source_repo_from_source_layout() -> None:
    launcher = _load_launcher_module()
    repo_root, diagnostic = launcher.find_repo_root(PLUGIN_ROOT, {})

    assert diagnostic == ""
    assert repo_root == REPO_ROOT.resolve()


def test_plugin_launcher_resolves_source_repo_from_desktop_cache(tmp_path: Path) -> None:
    launcher = _load_launcher_module()
    codex_home = tmp_path / "codex-home"
    plugin_root = (
        codex_home
        / "plugins"
        / "cache"
        / "codex-supervisor-local"
        / "codex-supervisor"
        / PLUGIN_VERSION
    )
    repo_root = tmp_path / "source-repo"
    (repo_root / "src" / "codex_supervisor").mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    plugin_root.mkdir(parents=True)
    (codex_home / "config.toml").write_text(
        f"[marketplaces.codex-supervisor-local]\nsource = '{repo_root.as_posix()}'\n",
        encoding="utf-8",
    )

    resolved_root, diagnostic = launcher.find_repo_root(
        plugin_root,
        {"CODEX_HOME": str(codex_home)},
    )

    assert diagnostic == ""
    assert resolved_root == repo_root.resolve()


def test_plugin_launcher_diagnostic_fallback_exposes_runtime_preflight() -> None:
    launcher = _load_launcher_module()
    server = launcher._DiagnosticServer(diagnostic="MCP startup failed: no source")

    initialize = server.handle_line(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "init",
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25"},
            }
        )
    )
    assert initialize is not None
    assert "diagnostic" in initialize["result"]["serverInfo"]["version"]

    assert (
        server.handle_line(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        is None
    )
    tools = server.handle_line(
        json.dumps({"jsonrpc": "2.0", "id": "tools", "method": "tools/list"})
    )
    assert tools is not None
    assert tools["result"]["tools"][0]["name"] == "codex_supervisor.runtime_preflight"

    result = server.handle_line(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "call",
                "method": "tools/call",
                "params": {"name": "codex_supervisor.runtime_preflight", "arguments": {}},
            }
        )
    )
    assert result is not None
    payload = result["result"]["structuredContent"]
    assert payload["ok"] is False
    assert payload["data"]["status"] == "blocked"
    assert payload["data"]["ledger"]["required_surface"] == "live_mcp"
    assert payload["data"]["ledger"]["decision_source"] == "diagnostic_mcp_fallback"
    assert payload["data"]["issues"][0]["code"] == "mcp_startup_failed"
    assert result["result"]["isError"] is True
