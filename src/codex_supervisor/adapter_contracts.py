"""Declaration-first adapter operation contracts."""

from __future__ import annotations

from dataclasses import dataclass

from codex_supervisor.policy import AssuranceLevel


@dataclass(frozen=True)
class AdapterOperationContract:
    """One adapter operation mapped onto the compact substrate model."""

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


ADAPTER_OPERATION_CONTRACTS: tuple[AdapterOperationContract, ...] = (
    AdapterOperationContract(
        name="cli_plan_init",
        surface="cli",
        operation_name="plan-init",
        task_intent="Bootstraps the compact planning ledger before task intent is recorded.",
        attempt_behavior="Creates no run attempt.",
        evidence_behavior=(
            "Initializes planning SQLite schema metadata and ensures the workspace "
            ".codex-supervisor/ gitignore guard."
        ),
        assurance_levels=(
            AssuranceLevel.LOW,
            AssuranceLevel.MEDIUM,
            AssuranceLevel.HIGH,
        ),
        acceptance_behavior="Creates no acceptance decision.",
        state_flow="Creates or migrates the compact planning SQLite schema.",
        operator_value="Gives Goal Mode a durable ledger before any supervised work begins.",
    ),
    AdapterOperationContract(
        name="cli_task_create",
        surface="cli",
        operation_name="task-create",
        task_intent="Records Goal Mode's next work unit as durable task intent.",
        attempt_behavior="Creates no run attempt; it prepares the task for a later attempt.",
        evidence_behavior="Records acceptance criteria but no evidence bundle.",
        assurance_levels=(
            AssuranceLevel.LOW,
            AssuranceLevel.MEDIUM,
            AssuranceLevel.HIGH,
        ),
        acceptance_behavior="Creates no acceptance decision.",
        state_flow="Writes one task intent into planning SQLite through the compact store.",
        operator_value="Gives Goal Mode a small, generic way to declare work before execution.",
    ),
    AdapterOperationContract(
        name="cli_attempt_transition",
        surface="cli",
        operation_name="attempt-transition",
        task_intent="Moves an existing task attempt through the compact lifecycle.",
        attempt_behavior="Creates, starts, or terminalizes one run attempt.",
        evidence_behavior="Attaches evidence only on terminal attempt transitions.",
        assurance_levels=(
            AssuranceLevel.LOW,
            AssuranceLevel.MEDIUM,
            AssuranceLevel.HIGH,
        ),
        acceptance_behavior="Evaluates acceptance when terminal evidence is written.",
        state_flow="Writes attempt, evidence, acceptance, and task status rows in planning SQLite.",
        operator_value="Supports manual/admin state repair without adding semantic job types.",
    ),
    AdapterOperationContract(
        name="cli_attempt_run",
        surface="cli",
        operation_name="attempt-run",
        task_intent="Runs one worker process for an existing task intent.",
        attempt_behavior="Starts and terminalizes one process-backed run attempt.",
        evidence_behavior=(
            "Records command metadata, assignment metadata, stdout/stderr summaries, "
            "artifacts, verifier output, and product provenance."
        ),
        assurance_levels=(
            AssuranceLevel.LOW,
            AssuranceLevel.MEDIUM,
            AssuranceLevel.HIGH,
        ),
        acceptance_behavior="Evaluates acceptance after worker and optional verifier evidence.",
        state_flow="Writes through the same task, attempt, evidence, and acceptance model.",
        operator_value="Makes product mutation attributable to one supervised worker attempt.",
    ),
    AdapterOperationContract(
        name="cli_queue_next",
        surface="cli",
        operation_name="queue-next",
        task_intent="Inspects the next compact queue task without mutating state.",
        attempt_behavior="Reads active attempt state when present.",
        evidence_behavior="Reads latest evidence and digest state when present.",
        assurance_levels=(
            AssuranceLevel.LOW,
            AssuranceLevel.MEDIUM,
            AssuranceLevel.HIGH,
        ),
        acceptance_behavior="Reports latest acceptance without replaying policy.",
        state_flow="Reads planning SQLite through the compact queue interface.",
        operator_value="Lets Goal Mode recover current work state through a local CLI.",
    ),
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
            "Reports durable task, attempt, and evidence state without replaying acceptance policy."
        ),
        state_flow="Reads planning SQLite through the compact queue interface.",
        operator_value=(
            "Lets an MCP client answer the next-work question through the same compact "
            "inspection path as the CLI."
        ),
    ),
    AdapterOperationContract(
        name="plugin_cli_forwarder",
        surface="plugin",
        operation_name="codex-supervisor",
        task_intent="Forwards Desktop CLI calls to the source CLI without adding work semantics.",
        attempt_behavior="Preserves the forwarded CLI command's attempt behavior.",
        evidence_behavior="Preserves the forwarded CLI command's evidence behavior.",
        assurance_levels=(
            AssuranceLevel.LOW,
            AssuranceLevel.MEDIUM,
            AssuranceLevel.HIGH,
        ),
        acceptance_behavior="Preserves the forwarded CLI command's acceptance behavior.",
        state_flow="Delegates to the source CLI and planning SQLite selected by the caller.",
        operator_value="Keeps the Desktop plugin a packaging wrapper instead of a workflow engine.",
    ),
    AdapterOperationContract(
        name="plugin_mcp_stdio",
        surface="plugin",
        operation_name="codex-supervisor-mcp",
        task_intent="Forwards Desktop MCP queue inspection to the source MCP stdio server.",
        attempt_behavior="Reads active attempt state through the MCP queue operation.",
        evidence_behavior="Reads latest evidence through the MCP queue operation.",
        assurance_levels=(
            AssuranceLevel.LOW,
            AssuranceLevel.MEDIUM,
            AssuranceLevel.HIGH,
        ),
        acceptance_behavior="Reports latest acceptance through the MCP queue operation.",
        state_flow=(
            "Delegates to the source MCP stdio server with an explicit planning SQLite path."
        ),
        operator_value="Exposes read-only recovery state to Codex Desktop without mutating work.",
    ),
    AdapterOperationContract(
        name="worker_launcher",
        surface="worker",
        operation_name="codex_worker_launcher",
        task_intent="Launches one ephemeral Codex worker from a supervisor assignment.",
        attempt_behavior=(
            "Runs under an attempt-run process attempt; it does not own lifecycle state."
        ),
        evidence_behavior="Emits stdout/stderr for attempt-run capture.",
        assurance_levels=(
            AssuranceLevel.LOW,
            AssuranceLevel.MEDIUM,
            AssuranceLevel.HIGH,
        ),
        acceptance_behavior="Does not accept work; attempt-run and policy own acceptance.",
        state_flow="Receives task assignment through environment and returns process output.",
        operator_value="Keeps worker execution generic while Goal Mode provides launch context.",
    ),
)


def validate_adapter_contracts(
    contracts: tuple[AdapterOperationContract, ...] = ADAPTER_OPERATION_CONTRACTS,
) -> tuple[str, ...]:
    """Validate that every adapter declaration maps to the substrate model."""

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
