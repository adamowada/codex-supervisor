from __future__ import annotations

import ast
from pathlib import Path

from codex_supervisor import mcp_server
from codex_supervisor.operation_registry import (
    FULL_AFK_MCP_SURFACE,
    PLUGIN_INSTALL_MCP_SURFACE,
    cli_command_names,
    mcp_tool_names,
    operation_by_mcp_tool,
    required_mcp_tool_names,
)
from codex_supervisor.runtime_preflight import REQUIRED_SUPERVISOR_MCP_TOOLS
from scripts.verify_codex_plugin_install import REQUIRED_MCP_TOOLS

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_operation_registry_covers_cli_commands_and_mcp_tools() -> None:
    assert _cli_commands_from_parser_source() == cli_command_names()
    assert set(mcp_server.TOOL_DEFINITIONS) == mcp_tool_names()


def test_operation_registry_matches_mcp_read_only_annotations() -> None:
    for tool_name, definition in mcp_server.TOOL_DEFINITIONS.items():
        assert operation_by_mcp_tool(tool_name).read_only is definition.read_only


def test_operation_registry_owns_required_mcp_surfaces() -> None:
    assert required_mcp_tool_names(FULL_AFK_MCP_SURFACE) == REQUIRED_SUPERVISOR_MCP_TOOLS
    assert required_mcp_tool_names(PLUGIN_INSTALL_MCP_SURFACE) == REQUIRED_MCP_TOOLS


def test_operation_registry_names_intentional_mcp_only_tools() -> None:
    mcp_only_tools = {
        tool_name
        for tool_name in mcp_tool_names()
        if operation_by_mcp_tool(tool_name).cli_command is None
    }

    assert mcp_only_tools == set()


def _cli_commands_from_parser_source() -> frozenset[str]:
    source = (REPO_ROOT / "src/codex_supervisor/cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    commands: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_parser"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            commands.add(node.args[0].value)
    return frozenset(commands)
