from __future__ import annotations

from codex_supervisor.adapter_contracts import (
    ADAPTER_OPERATION_CONTRACTS,
    active_adapter_contracts,
    validate_adapter_contracts,
)
from codex_supervisor.operation_registry import operation_by_name
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
    assert contract.active is True


def test_active_adapter_contract_has_registered_mcp_operation() -> None:
    active = {contract.operation_name for contract in active_adapter_contracts()}
    operation = operation_by_name("queue_next")

    assert "queue_next" in active
    assert operation.mcp_tool == "codex_supervisor.queue_next"
    assert operation.read_only is True
