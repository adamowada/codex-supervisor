"""Codex automation bridge proposal and official apply helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SUPPORTED_AUTOMATION_KINDS = frozenset({"cron", "heartbeat"})
SUPPORTED_CRON_FREQUENCIES = frozenset({"HOURLY", "WEEKLY"})
SUPPORTED_HEARTBEAT_FREQUENCIES = frozenset({"MINUTELY", "DAILY", "WEEKLY"})
SUPPORTED_STATUSES = frozenset({"ACTIVE", "PAUSED"})
SUPPORTED_EXECUTION_ENVIRONMENTS = frozenset({"local", "worktree"})
JsonObject = dict[str, object]
OfficialAutomationRunner = Callable[[JsonObject], Mapping[str, object] | None]


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


@dataclass(frozen=True)
class CodexAutomationBridgeApplyRecord:
    """One applied official Codex automation call."""

    proposal_id: str
    action_type: str
    action_status: str
    name: str
    purpose: str
    kind: str
    observed_at: str
    official_payload: dict[str, object]
    official_result: dict[str, object]
    summary: str


@dataclass(frozen=True)
class CodexAutomationBridgeApplyReport:
    """Result of applying approved official Codex automation proposals."""

    workspace_root: str
    observed_at: str
    source_plan_id: str
    source_task_id: str
    approved_proposal_ids: tuple[str, ...]
    applied: tuple[CodexAutomationBridgeApplyRecord, ...]
    skipped_proposal_ids: tuple[str, ...]
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


def apply_codex_automation_bridge_report(
    report: CodexAutomationBridgeDryRunReport,
    *,
    approved_proposal_ids: tuple[str, ...],
    official_runner: OfficialAutomationRunner,
    observed_at: str | None = None,
) -> CodexAutomationBridgeApplyReport:
    """Apply approved proposals through the official Codex automation runner boundary."""

    timestamp = observed_at or _utc_timestamp()
    approved = tuple(
        dict.fromkeys(proposal_id for proposal_id in approved_proposal_ids if proposal_id)
    )
    approved_set = set(approved)
    proposals_by_id = {proposal.proposal_id: proposal for proposal in report.proposals}
    findings: list[CodexAutomationBridgeFinding] = []
    applied: list[CodexAutomationBridgeApplyRecord] = []

    if not approved:
        findings.append(
            _finding(
                finding_type="missing_automation_approval",
                source_id="codex-automation-apply",
                observed_at=timestamp,
                summary="At least one proposal_id must be explicitly approved before apply.",
            )
        )
    for proposal_id in approved:
        if proposal_id not in proposals_by_id:
            findings.append(
                _finding(
                    finding_type="unknown_automation_proposal",
                    source_id=proposal_id,
                    observed_at=timestamp,
                    summary=(
                        f"Approved proposal_id does not exist in the dry-run report: {proposal_id}."
                    ),
                )
            )

    for proposal in report.proposals:
        if proposal.proposal_id not in approved_set:
            continue
        if proposal.action_status != "proposed":
            findings.append(
                _finding(
                    finding_type="automation_proposal_not_applicable",
                    source_id=proposal.proposal_id,
                    observed_at=timestamp,
                    summary=(
                        f"Proposal {proposal.proposal_id} has action_status="
                        f"{proposal.action_status!r}, not 'proposed'."
                    ),
                )
            )
            continue
        try:
            official_result = official_runner(dict(proposal.official_payload))
        except Exception as exc:
            findings.append(
                _finding(
                    finding_type="official_automation_apply_failed",
                    source_id=proposal.proposal_id,
                    observed_at=timestamp,
                    summary=f"Official automation apply failed for {proposal.name!r}: {exc}.",
                )
            )
            continue
        applied.append(
            CodexAutomationBridgeApplyRecord(
                proposal_id=proposal.proposal_id,
                action_type="official-automation-create",
                action_status="applied",
                name=proposal.name,
                purpose=proposal.purpose,
                kind=proposal.kind,
                observed_at=timestamp,
                official_payload=dict(proposal.official_payload),
                official_result=dict(official_result or {}),
                summary=(
                    f"Applied official Codex {proposal.kind} automation {proposal.name!r} "
                    f"for {proposal.purpose}."
                ),
            )
        )

    return CodexAutomationBridgeApplyReport(
        workspace_root=report.workspace_root,
        observed_at=timestamp,
        source_plan_id=report.source_plan_id,
        source_task_id=report.source_task_id,
        approved_proposal_ids=approved,
        applied=tuple(applied),
        skipped_proposal_ids=tuple(
            proposal.proposal_id
            for proposal in report.proposals
            if proposal.proposal_id not in approved_set
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


def codex_automation_bridge_dry_run_report_from_payload(
    payload: Mapping[str, object],
) -> CodexAutomationBridgeDryRunReport:
    """Rehydrate a dry-run report from its JSON representation."""

    proposals = payload.get("proposals")
    findings = payload.get("findings")
    return CodexAutomationBridgeDryRunReport(
        workspace_root=_payload_string(payload, "workspace_root"),
        observed_at=_payload_string(payload, "observed_at"),
        source_plan_id=_payload_string(payload, "source_plan_id"),
        source_task_id=_payload_string(payload, "source_task_id"),
        proposals=tuple(
            _proposal_from_payload(item) for item in proposals if isinstance(item, Mapping)
        )
        if isinstance(proposals, list)
        else (),
        findings=tuple(
            _finding_from_payload(item) for item in findings if isinstance(item, Mapping)
        )
        if isinstance(findings, list)
        else (),
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


def _proposal_from_payload(payload: Mapping[str, object]) -> CodexAutomationBridgeProposal:
    return CodexAutomationBridgeProposal(
        proposal_id=_payload_string(payload, "proposal_id"),
        action_type=_payload_string(payload, "action_type"),
        action_status=_payload_string(payload, "action_status"),
        name=_payload_string(payload, "name"),
        purpose=_payload_string(payload, "purpose"),
        kind=_payload_string(payload, "kind"),
        destination=_payload_string(payload, "destination"),
        rrule=_payload_string(payload, "rrule"),
        prompt=_payload_string(payload, "prompt"),
        execution_environment=_payload_string(payload, "execution_environment"),
        cwds=_payload_string_tuple(payload.get("cwds")),
        status=_payload_string(payload, "status"),
        model=_payload_string(payload, "model"),
        reasoning_effort=_payload_string(payload, "reasoning_effort"),
        source_kind=_payload_string(payload, "source_kind"),
        source_id=_payload_string(payload, "source_id"),
        source_plan_id=_payload_string(payload, "source_plan_id"),
        source_task_id=_payload_string(payload, "source_task_id"),
        observed_at=_payload_string(payload, "observed_at"),
        confidence=_payload_string(payload, "confidence"),
        official_payload=_payload_object(payload.get("official_payload")),
        summary=_payload_string(payload, "summary"),
    )


def _finding_from_payload(payload: Mapping[str, object]) -> CodexAutomationBridgeFinding:
    return CodexAutomationBridgeFinding(
        finding_type=_payload_string(payload, "finding_type"),
        source_id=_payload_string(payload, "source_id"),
        observed_at=_payload_string(payload, "observed_at"),
        failure_class=_payload_string(payload, "failure_class"),
        summary=_payload_string(payload, "summary"),
    )


def _payload_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    return ""


def _payload_string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    strings = tuple(item for item in value if isinstance(item, str))
    if len(strings) != len(value):
        return ()
    return strings


def _payload_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return dict(value)


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
