from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.verify_codex_plugin_install import verify_codex_plugin_install

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-supervisor"
MANIFEST_PATH = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
MCP_PATH = PLUGIN_ROOT / ".mcp.json"
README_PATH = PLUGIN_ROOT / "README.md"
SKILL_PATH = PLUGIN_ROOT / "skills" / "codex-supervisor" / "SKILL.md"


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_plugin_manifest_describes_stage12_desktop_surface() -> None:
    manifest = _load_json(MANIFEST_PATH)

    assert manifest["name"] == "codex-supervisor"
    assert manifest["version"] == "0.1.0"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert manifest["skills"] == "./skills/"
    assert "apps" not in manifest
    assert manifest["repository"] == "https://github.com/adamowada/codex-supervisor"

    interface = manifest["interface"]
    assert isinstance(interface, dict)
    assert interface["displayName"] == "Codex Supervisor"
    assert interface["category"] == "Developer Tools"
    assert interface["capabilities"] == ["Interactive", "Read"]
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
    assert server["command"] == "uv"
    assert server["args"] == [
        "run",
        "--no-sync",
        "python",
        "-B",
        "-m",
        "codex_supervisor.mcp_stdio",
    ]
    assert server["cwd"] == "../.."
    assert (PLUGIN_ROOT / str(server["cwd"])).resolve() == REPO_ROOT.resolve()

    serialized = json.dumps(server, sort_keys=True)
    assert "codex exec" not in serialized
    assert "worker" not in serialized.lower()
    assert "write" not in serialized.lower()


def test_plugin_docs_name_desktop_roles_and_queue_authority() -> None:
    readme = README_PATH.read_text(encoding="utf-8")

    required_phrases = [
        "codex_supervisor.mcp_stdio",
        "uv run --no-sync python -B -m codex_supervisor.mcp_stdio",
        "uv run --no-sync python -B scripts/verify_codex_plugin_install.py",
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
        "add mutating MCP tools",
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
        "MCP tools for read-only inspection",
        "uv run --no-sync python -B -m codex_supervisor.cli",
        ".agents/skills/skill-router/SKILL.md",
        "spawned-project-bootstrap",
        "setup-agent-docs",
        "story-loop-status --json",
        "goal-contract-render --task-id",
        "task-claim",
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
                                {"name": "codex_supervisor.story_loop_status"},
                                {"name": "codex_supervisor.task_show"},
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
        "uv",
        "run",
        "--no-sync",
        "python",
        "-B",
        "-m",
        "codex_supervisor.mcp_stdio",
    )
    assert captured["cwd"] == REPO_ROOT
    payload = str(captured["payload"])
    assert '"method": "initialize"' in payload
    assert '"method": "tools/list"' in payload
