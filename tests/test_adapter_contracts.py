from __future__ import annotations

from codex_supervisor.adapter_contracts import (
    ADAPTER_OPERATION_CONTRACTS,
    validate_adapter_contracts,
)
from codex_supervisor.mcp_server import list_mcp_tools
from codex_supervisor.policy import AssuranceLevel


def test_adapter_contracts_are_complete() -> None:
    assert validate_adapter_contracts() == ()


def test_mcp_queue_next_contract_maps_to_compact_model() -> None:
    contract = next(
        contract
        for contract in ADAPTER_OPERATION_CONTRACTS
        if contract.name == "mcp_queue_next"
    )

    assert contract.surface == "mcp"
    assert contract.operation_name == "queue_next"
    assert AssuranceLevel.HIGH in contract.assurance_levels
    assert "attempt" in contract.attempt_behavior.casefold()
    assert "evidence" in contract.evidence_behavior.casefold()
    assert "acceptance" in contract.acceptance_behavior.casefold()
    assert "planning SQLite" in contract.state_flow


def test_mcp_surface_contains_declared_queue_operation() -> None:
    tool_names = {tool["name"] for tool in list_mcp_tools()}

    assert tool_names == {"codex_supervisor.queue_next"}


def test_declared_adapter_surfaces_match_active_contract() -> None:
    contracts = {contract.name: contract for contract in ADAPTER_OPERATION_CONTRACTS}

    assert set(contracts) == {
        "cli_task_create",
        "cli_attempt_transition",
        "cli_attempt_run",
        "cli_queue_next",
        "mcp_queue_next",
        "plugin_cli_forwarder",
        "plugin_mcp_stdio",
        "worker_launcher",
    }
    assert {contract.surface for contract in contracts.values()} == {
        "cli",
        "mcp",
        "plugin",
        "worker",
    }
    assert (
        "workflow engine"
        in contracts["plugin_cli_forwarder"].operator_value.casefold()
    )
    assert "attempt-run" in contracts["worker_launcher"].attempt_behavior
