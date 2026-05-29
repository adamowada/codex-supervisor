"""Declaration-first adapter operation contracts."""

from __future__ import annotations

from dataclasses import dataclass

from codex_supervisor.policy import AssuranceLevel


@dataclass(frozen=True)
class AdapterOperationContract:
    """One adapter operation mapped onto the compact control-plane model."""

    name: str
    surface: str
    operation_name: str
    task_intent: str
    attempt_behavior: str
    evidence_behavior: str
    assurance_levels: tuple[AssuranceLevel, ...]
    acceptance_behavior: str
    state_flow: str
    operator_value: str
    active: bool


ADAPTER_OPERATION_CONTRACTS: tuple[AdapterOperationContract, ...] = (
    AdapterOperationContract(
        name="mcp_queue_next",
        surface="mcp",
        operation_name="queue_next",
        task_intent="Inspect the next compact queue task without mutating state.",
        attempt_behavior="Reads the active attempt for the selected task when one exists.",
        evidence_behavior="Reads the latest evidence bundle for the selected task when one exists.",
        assurance_levels=(
            AssuranceLevel.LOW,
            AssuranceLevel.MEDIUM,
            AssuranceLevel.HIGH,
        ),
        acceptance_behavior=(
            "Reports the current acceptance evaluation when task, attempt, "
            "and evidence are present."
        ),
        state_flow="Reads planning SQLite through the compact queue interface.",
        operator_value=(
            "Lets an MCP client answer the next-work question through the same compact "
            "inspection path as the CLI."
        ),
        active=True,
    ),
)


def active_adapter_contracts() -> tuple[AdapterOperationContract, ...]:
    """Return active adapter operation declarations."""

    return tuple(contract for contract in ADAPTER_OPERATION_CONTRACTS if contract.active)


def validate_adapter_contracts(
    contracts: tuple[AdapterOperationContract, ...] = ADAPTER_OPERATION_CONTRACTS,
) -> tuple[str, ...]:
    """Validate that every adapter declaration maps to the compact model."""

    failures: list[str] = []
    seen_names: set[str] = set()
    for contract in contracts:
        if contract.name in seen_names:
            failures.append(f"duplicate adapter contract name: {contract.name}")
        seen_names.add(contract.name)
        for field_name in (
            "surface",
            "operation_name",
            "task_intent",
            "attempt_behavior",
            "evidence_behavior",
            "acceptance_behavior",
            "state_flow",
            "operator_value",
        ):
            if not getattr(contract, field_name).strip():
                failures.append(f"{contract.name}.{field_name} is required")
        if not contract.assurance_levels:
            failures.append(f"{contract.name}.assurance_levels is required")
    return tuple(failures)
