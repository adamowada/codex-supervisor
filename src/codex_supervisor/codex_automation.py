"""Non-mutating Codex automation bridge proposal helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SUPPORTED_AUTOMATION_KINDS = frozenset({"cron", "heartbeat"})
SUPPORTED_CRON_FREQUENCIES = frozenset({"HOURLY", "WEEKLY"})
SUPPORTED_HEARTBEAT_FREQUENCIES = frozenset({"MINUTELY", "DAILY", "WEEKLY"})
SUPPORTED_STATUSES = frozenset({"ACTIVE", "PAUSED"})
SUPPORTED_EXECUTION_ENVIRONMENTS = frozenset({"local", "worktree"})


@dataclass(frozen=True)
class CodexAutomationBridgeSpec:
    """One desired official Codex automation proposal."""

    name: str
    purpose: str
    rrule: str
    prompt: str
    kind: str = "cron"
    destination: str = ""
    execution_environment: str = "local"
    status: str = "ACTIVE"
    model: str = ""
    reasoning_effort: str = ""


@dataclass(frozen=True)
class CodexAutomationBridgeProposal:
    """Reviewable proposal for an official Codex automation tool call."""

    proposal_id: str
    action_type: str
    action_status: str
    name: str
    purpose: str
    kind: str
    destination: str
    rrule: str
    prompt: str
    execution_environment: str
    cwds: tuple[str, ...]
    status: str
    model: str
    reasoning_effort: str
    source_kind: str
    source_id: str
    source_plan_id: str
    source_task_id: str
    observed_at: str
    confidence: str
    official_payload: dict[str, object]
    summary: str


@dataclass(frozen=True)
class CodexAutomationBridgeFinding:
    """Nonfatal dry-run validation finding."""

    finding_type: str
    source_id: str
    observed_at: str
    failure_class: str
    summary: str


@dataclass(frozen=True)
class CodexAutomationBridgeDryRunReport:
    """Dry-run result for proposed official Codex automations."""

    workspace_root: str
    observed_at: str
    source_plan_id: str
    source_task_id: str
    proposals: tuple[CodexAutomationBridgeProposal, ...]
    findings: tuple[CodexAutomationBridgeFinding, ...]


def default_codex_automation_bridge_specs(
    *,
    queue_reconciliation_rrule: str,
    health_check_rrule: str,
    model: str = "",
    reasoning_effort: str = "",
    status: str = "ACTIVE",
    execution_environment: str = "local",
) -> tuple[CodexAutomationBridgeSpec, ...]:
    """Return the default Stage 10 automation bridge proposal set."""

    return (
        CodexAutomationBridgeSpec(
            name="Codex Supervisor Queue Reconciliation",
            purpose="queue_reconciliation",
            rrule=queue_reconciliation_rrule,
            prompt=(
                "Inspect the codex-supervisor planning queue with story-loop-status and "
                "plan-summary, reconcile stale running or blocked state into planning SQLite "
                "only through supervisor CLI/helpers, and report the next AFK or HITL action. "
                "Do not write Codex internal SQLite databases."
            ),
            model=model,
            reasoning_effort=reasoning_effort,
            status=status,
            execution_environment=execution_environment,
        ),
        CodexAutomationBridgeSpec(
            name="Codex Supervisor Project Health Check",
            purpose="project_health_check",
            rrule=health_check_rrule,
            prompt=(
                "Run codex-supervisor health checks for planning integrity, source locks, public "
                "hygiene, file justification, skill inventory, and source inventory. Summarize "
                "failures as supervisor follow-up recommendations. Do not push, merge, or release."
            ),
            model=model,
            reasoning_effort=reasoning_effort,
            status=status,
            execution_environment=execution_environment,
        ),
    )


def build_codex_automation_bridge_dry_run(
    *,
    workspace_root: Path,
    specs: tuple[CodexAutomationBridgeSpec, ...],
    source_plan_id: str = "",
    source_task_id: str = "",
    observed_at: str | None = None,
) -> CodexAutomationBridgeDryRunReport:
    """Build non-mutating proposals for official Codex automation tooling."""

    timestamp = observed_at or _utc_timestamp()
    workspace = workspace_root.resolve()
    findings: list[CodexAutomationBridgeFinding] = []
    proposals: list[CodexAutomationBridgeProposal] = []
    seen_names: set[str] = set()

    workspace_available = workspace.exists() and workspace.is_dir()
    if not workspace_available:
        findings.append(
            _finding(
                finding_type="missing_workspace_root",
                source_id=workspace.as_posix(),
                observed_at=timestamp,
                summary=f"Workspace root does not exist or is not a directory: {workspace}.",
            )
        )

    for spec in specs:
        spec_findings = _validate_spec(
            spec,
            observed_at=timestamp,
            seen_names=seen_names,
        )
        if spec_findings:
            findings.extend(spec_findings)
            continue
        seen_names.add(spec.name.casefold())
        if not workspace_available:
            continue
        proposals.append(
            _proposal_for_spec(
                spec,
                workspace=workspace,
                observed_at=timestamp,
                source_plan_id=source_plan_id,
                source_task_id=source_task_id,
            )
        )

    return CodexAutomationBridgeDryRunReport(
        workspace_root=workspace.as_posix(),
        observed_at=timestamp,
        source_plan_id=source_plan_id,
        source_task_id=source_task_id,
        proposals=tuple(
            sorted(proposals, key=lambda proposal: (proposal.name, proposal.proposal_id))
        ),
        findings=tuple(
            sorted(
                findings,
                key=lambda finding: (
                    finding.source_id,
                    finding.finding_type,
                    finding.failure_class,
                ),
            )
        ),
    )


def _validate_spec(
    spec: CodexAutomationBridgeSpec,
    *,
    observed_at: str,
    seen_names: set[str],
) -> tuple[CodexAutomationBridgeFinding, ...]:
    findings: list[CodexAutomationBridgeFinding] = []
    source_id = spec.name or "<unnamed>"
    if not spec.name.strip():
        findings.append(
            _finding(
                finding_type="missing_proposal_name",
                source_id=source_id,
                observed_at=observed_at,
                summary="Automation proposal name must be nonblank.",
            )
        )
    elif spec.name.casefold() in seen_names:
        findings.append(
            _finding(
                finding_type="duplicate_proposal_name",
                source_id=spec.name,
                observed_at=observed_at,
                summary=f"Automation proposal name is duplicated: {spec.name}.",
            )
        )
    if spec.kind not in SUPPORTED_AUTOMATION_KINDS:
        findings.append(
            _finding(
                finding_type="unsupported_automation_kind",
                source_id=source_id,
                observed_at=observed_at,
                summary=f"Unsupported Codex automation kind: {spec.kind}.",
            )
        )
    if spec.status not in SUPPORTED_STATUSES:
        findings.append(
            _finding(
                finding_type="unsupported_status",
                source_id=source_id,
                observed_at=observed_at,
                summary=f"Unsupported Codex automation status: {spec.status}.",
            )
        )
    if spec.execution_environment not in SUPPORTED_EXECUTION_ENVIRONMENTS:
        findings.append(
            _finding(
                finding_type="unsupported_execution_environment",
                source_id=source_id,
                observed_at=observed_at,
                summary=(
                    f"Unsupported Codex automation execution environment: "
                    f"{spec.execution_environment}."
                ),
            )
        )
    rrule_reason = _invalid_rrule_reason(spec.rrule, kind=spec.kind)
    if rrule_reason:
        findings.append(
            _finding(
                finding_type="invalid_rrule",
                source_id=source_id,
                observed_at=observed_at,
                summary=rrule_reason,
            )
        )
    destination_reason = _invalid_destination_reason(spec.kind, spec.destination)
    if destination_reason:
        findings.append(
            _finding(
                finding_type="unsupported_destination",
                source_id=source_id,
                observed_at=observed_at,
                summary=destination_reason,
            )
        )
    if not spec.prompt.strip():
        findings.append(
            _finding(
                finding_type="missing_prompt",
                source_id=source_id,
                observed_at=observed_at,
                summary="Automation proposal prompt must be nonblank.",
            )
        )
    return tuple(findings)


def _invalid_rrule_reason(rrule: str, *, kind: str) -> str:
    if not rrule.strip():
        return "Automation schedule RRULE must be nonblank."
    parts = _rrule_parts(rrule)
    frequency = parts.get("FREQ", "")
    if not frequency:
        return f"Automation schedule RRULE must include FREQ: {rrule}."
    allowed = SUPPORTED_HEARTBEAT_FREQUENCIES if kind == "heartbeat" else SUPPORTED_CRON_FREQUENCIES
    if frequency not in allowed:
        return f"Unsupported {kind} automation RRULE frequency: {frequency}."
    return ""


def _rrule_parts(rrule: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for raw_part in rrule.split(";"):
        if "=" not in raw_part:
            continue
        key, value = raw_part.split("=", 1)
        parts[key.strip().upper()] = value.strip().upper()
    return parts


def _invalid_destination_reason(kind: str, destination: str) -> str:
    if kind == "cron" and destination:
        return "Cron automation proposals must not set a thread destination."
    if kind == "heartbeat" and destination not in {"thread"}:
        return "Heartbeat automation proposals must use destination=thread."
    return ""


def _proposal_for_spec(
    spec: CodexAutomationBridgeSpec,
    *,
    workspace: Path,
    observed_at: str,
    source_plan_id: str,
    source_task_id: str,
) -> CodexAutomationBridgeProposal:
    cwds = (workspace.as_posix(),)
    payload = _official_payload(spec, cwds=cwds)
    proposal_id = _proposal_id(
        {
            "action_type": "official-automation-suggested-create",
            "cwds": cwds,
            "destination": spec.destination,
            "kind": spec.kind,
            "name": spec.name,
            "purpose": spec.purpose,
            "rrule": spec.rrule,
            "source_plan_id": source_plan_id,
            "source_task_id": source_task_id,
        }
    )
    summary = f"Propose official Codex {spec.kind} automation {spec.name!r} for {spec.purpose}."
    return CodexAutomationBridgeProposal(
        proposal_id=proposal_id,
        action_type="official-automation-suggested-create",
        action_status="proposed",
        name=spec.name,
        purpose=spec.purpose,
        kind=spec.kind,
        destination=spec.destination,
        rrule=spec.rrule,
        prompt=spec.prompt,
        execution_environment=spec.execution_environment,
        cwds=cwds,
        status=spec.status,
        model=spec.model,
        reasoning_effort=spec.reasoning_effort,
        source_kind="planning_task",
        source_id=source_task_id or source_plan_id or "codex-supervisor",
        source_plan_id=source_plan_id,
        source_task_id=source_task_id,
        observed_at=observed_at,
        confidence="inferred",
        official_payload=payload,
        summary=summary,
    )


def _official_payload(
    spec: CodexAutomationBridgeSpec,
    *,
    cwds: tuple[str, ...],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": spec.kind,
        "name": spec.name,
        "prompt": spec.prompt,
        "rrule": spec.rrule,
        "status": spec.status,
    }
    if spec.kind == "cron":
        payload["executionEnvironment"] = spec.execution_environment
        payload["cwds"] = list(cwds)
        if spec.model:
            payload["model"] = spec.model
        if spec.reasoning_effort:
            payload["reasoningEffort"] = spec.reasoning_effort
    if spec.kind == "heartbeat":
        payload["destination"] = spec.destination
    return payload


def _proposal_id(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return f"codex-automation-{digest[:24]}"


def _finding(
    *,
    finding_type: str,
    source_id: str,
    observed_at: str,
    summary: str,
) -> CodexAutomationBridgeFinding:
    return CodexAutomationBridgeFinding(
        finding_type=finding_type,
        source_id=source_id,
        observed_at=observed_at,
        failure_class=finding_type,
        summary=summary,
    )


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
