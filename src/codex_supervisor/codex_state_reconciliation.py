"""Apply reviewed Codex local-state reconciliation proposals to planning evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from codex_supervisor.codex_state import (
    CodexStateReconciliationDryRunReport,
    CodexStateReconciliationFinding,
    CodexStateReconciliationProposal,
)
from codex_supervisor.planning import (
    PlanArtifactLinkRecord,
    PlanningSQLiteStore,
    PlanProgressRecord,
)

CODEX_STATE_SNAPSHOT_RELATIONSHIP = "codex-state-snapshot"
CODEX_STATE_APPLIED_EVENT = "codex_state_reconciliation_applied"
CODEX_STATE_FINDING_EVENT = "codex_state_reconciliation_finding"


class CodexStateReconciliationApplyError(ValueError):
    """Raised when a reviewed reconciliation report payload is malformed."""


@dataclass(frozen=True)
class CodexStateAppliedProposal:
    """One proposal applied to append-only planning evidence."""

    proposal_id: str
    action_type: str
    action_status: str
    progress_id: str
    artifact_id: str
    source_kind: str
    source_database: str
    source_table: str
    source_id: str
    observed_at: str
    confidence: str
    linked_plan_id: str
    linked_task_id: str
    raw_snapshot_hash: str
    summary: str


@dataclass(frozen=True)
class CodexStateSkippedProposal:
    """One proposal that was not applied and why."""

    proposal_id: str
    action_type: str
    action_status: str
    skip_reason: str
    source_kind: str
    source_database: str
    source_table: str
    source_id: str
    observed_at: str
    confidence: str
    linked_plan_id: str
    linked_task_id: str
    raw_snapshot_hash: str
    summary: str


@dataclass(frozen=True)
class CodexStateReconciliationApplyReport:
    """Result of applying reviewed Codex-state reconciliation proposals."""

    codex_home: str
    observed_at: str
    approved_proposal_ids: tuple[str, ...]
    applied: tuple[CodexStateAppliedProposal, ...]
    skipped: tuple[CodexStateSkippedProposal, ...]
    findings: tuple[CodexStateReconciliationFinding, ...]


def codex_state_reconciliation_report_from_payload(
    payload: object,
) -> CodexStateReconciliationDryRunReport:
    """Parse normalized dry-run JSON into dataclasses for reviewed apply."""

    if not isinstance(payload, dict):
        raise CodexStateReconciliationApplyError("dry-run report payload must be an object")
    return CodexStateReconciliationDryRunReport(
        codex_home=_required_string(payload, "codex_home"),
        observed_at=_required_string(payload, "observed_at"),
        linked_plan_id=_optional_string(payload, "linked_plan_id"),
        linked_task_id=_optional_string(payload, "linked_task_id"),
        observations=(),
        proposals=tuple(
            _proposal_from_payload(item) for item in _required_list(payload, "proposals")
        ),
        findings=tuple(_finding_from_payload(item) for item in _required_list(payload, "findings")),
    )


def apply_codex_state_reconciliation_report(
    store: PlanningSQLiteStore,
    report: CodexStateReconciliationDryRunReport,
    *,
    approved_proposal_ids: tuple[str, ...],
) -> CodexStateReconciliationApplyReport:
    """Apply reviewed proposals as append-only planning evidence."""

    approved = frozenset(approved_proposal_ids)
    known_plan_ids = {plan.plan_id for plan in store.list_plans()}
    known_task_ids = {task.task_id for task in store.list_supervisor_tasks()}
    existing_progress_ids = {progress.progress_id for progress in store.list_plan_progress()}
    existing_artifact_links = {
        (link.plan_id, link.artifact_id, link.relationship)
        for link in store.list_plan_artifact_links()
    }
    findings = list(report.findings)
    applied: list[CodexStateAppliedProposal] = []
    skipped: list[CodexStateSkippedProposal] = []
    proposal_ids = {proposal.proposal_id for proposal in report.proposals}
    for unknown_proposal_id in sorted(approved - proposal_ids):
        findings.append(
            _unknown_approved_proposal_finding(
                proposal_id=unknown_proposal_id,
                observed_at=report.observed_at,
            )
        )

    for proposal in _sorted_proposals(report.proposals):
        target_findings = _proposal_apply_findings(
            proposal,
            known_plan_ids=known_plan_ids,
            known_task_ids=known_task_ids,
        )
        if proposal.proposal_id not in approved:
            skipped.append(_skipped(proposal, "not_approved"))
            continue
        if target_findings:
            findings.extend(target_findings)
            skipped.append(_skipped(proposal, "target_conflict"))
            continue
        if proposal.action_type not in _SUPPORTED_ACTION_TYPES:
            findings.append(_proposal_finding(proposal, "unsupported_action_type"))
            skipped.append(_skipped(proposal, "unsupported_action_type"))
            continue
        progress_id = _progress_id(proposal)
        artifact_id = _artifact_id(proposal)
        artifact_key = (proposal.linked_plan_id, artifact_id, CODEX_STATE_SNAPSHOT_RELATIONSHIP)
        if progress_id in existing_progress_ids or (
            proposal.action_type == "artifact-link" and artifact_key in existing_artifact_links
        ):
            skipped.append(_skipped(proposal, "duplicate_already_applied"))
            continue
        artifact_link = PlanArtifactLinkRecord(
            plan_id=proposal.linked_plan_id,
            artifact_id=artifact_id,
            relationship=CODEX_STATE_SNAPSHOT_RELATIONSHIP,
        )
        progress = PlanProgressRecord(
            progress_id=progress_id,
            plan_id=proposal.linked_plan_id,
            event_type=_event_type(proposal),
            summary=_progress_summary(proposal),
            details=json.dumps(_progress_details(proposal), sort_keys=True),
            linked_artifact_id=artifact_id,
        )
        store.add_plan_progress_with_artifact_links(progress, (artifact_link,))
        existing_progress_ids.add(progress_id)
        existing_artifact_links.add(artifact_key)
        applied.append(_applied(proposal, progress_id=progress_id, artifact_id=artifact_id))

    return CodexStateReconciliationApplyReport(
        codex_home=report.codex_home,
        observed_at=report.observed_at,
        approved_proposal_ids=tuple(sorted(approved)),
        applied=tuple(applied),
        skipped=tuple(skipped),
        findings=tuple(
            sorted(
                findings,
                key=lambda finding: (
                    finding.source_database,
                    finding.source_table,
                    finding.source_id,
                    finding.finding_type,
                    finding.failure_class,
                ),
            )
        ),
    )


_SUPPORTED_ACTION_TYPES = frozenset({"artifact-link", "progress-event", "follow-up-finding"})


def _sorted_proposals(
    proposals: tuple[CodexStateReconciliationProposal, ...],
) -> tuple[CodexStateReconciliationProposal, ...]:
    return tuple(
        sorted(
            proposals,
            key=lambda proposal: (
                proposal.source_database,
                proposal.source_table,
                proposal.source_kind,
                proposal.source_id,
                proposal.action_type,
                proposal.proposal_id,
            ),
        )
    )


def _proposal_apply_findings(
    proposal: CodexStateReconciliationProposal,
    *,
    known_plan_ids: set[str],
    known_task_ids: set[str],
) -> tuple[CodexStateReconciliationFinding, ...]:
    findings: list[CodexStateReconciliationFinding] = []
    if not proposal.linked_plan_id or proposal.linked_plan_id not in known_plan_ids:
        findings.append(_proposal_finding(proposal, "missing_linked_plan"))
    if proposal.linked_task_id and proposal.linked_task_id not in known_task_ids:
        findings.append(_proposal_finding(proposal, "missing_linked_task"))
    if proposal.action_status != "proposed":
        findings.append(_proposal_finding(proposal, "unsupported_action_status"))
    return tuple(findings)


def _proposal_finding(
    proposal: CodexStateReconciliationProposal,
    finding_type: str,
) -> CodexStateReconciliationFinding:
    return CodexStateReconciliationFinding(
        finding_type=finding_type,
        source_database=proposal.source_database,
        source_table=proposal.source_table,
        source_id=proposal.source_id,
        observed_at=proposal.observed_at,
        failure_class=finding_type,
        summary=(
            f"Proposal {proposal.proposal_id} ({proposal.action_type}) could not be applied: "
            f"{finding_type}."
        ),
    )


def _unknown_approved_proposal_finding(
    *,
    proposal_id: str,
    observed_at: str,
) -> CodexStateReconciliationFinding:
    return CodexStateReconciliationFinding(
        finding_type="unknown_approved_proposal",
        source_database="",
        source_table="",
        source_id=proposal_id,
        observed_at=observed_at,
        failure_class="unknown_approved_proposal",
        summary=f"Approved proposal {proposal_id} was not present in the reviewed dry-run report.",
    )


def _progress_id(proposal: CodexStateReconciliationProposal) -> str:
    prefix = {
        "artifact-link": "codex-state-artifact",
        "progress-event": "codex-state-progress",
        "follow-up-finding": "codex-state-finding",
    }.get(proposal.action_type, "codex-state-unsupported")
    return f"{prefix}-{proposal.proposal_id.removeprefix('codex-state-')}"


def _artifact_id(proposal: CodexStateReconciliationProposal) -> str:
    return f"codex-state-snapshots/{proposal.raw_snapshot_hash}.json"


def _event_type(proposal: CodexStateReconciliationProposal) -> str:
    if proposal.action_type == "follow-up-finding":
        return CODEX_STATE_FINDING_EVENT
    return CODEX_STATE_APPLIED_EVENT


def _progress_summary(proposal: CodexStateReconciliationProposal) -> str:
    if proposal.action_type == "artifact-link":
        return f"Applied Codex state artifact-link proposal {proposal.proposal_id}."
    if proposal.action_type == "progress-event":
        return f"Applied Codex state progress-event proposal {proposal.proposal_id}."
    if proposal.action_type == "follow-up-finding":
        return f"Applied Codex state follow-up-finding proposal {proposal.proposal_id}."
    return f"Skipped unsupported Codex state proposal {proposal.proposal_id}."


def _progress_details(proposal: CodexStateReconciliationProposal) -> dict[str, str]:
    return {
        "proposal_id": proposal.proposal_id,
        "action_type": proposal.action_type,
        "action_status": "applied",
        "source_kind": proposal.source_kind,
        "source_database": proposal.source_database,
        "source_table": proposal.source_table,
        "source_id": proposal.source_id,
        "observed_at": proposal.observed_at,
        "confidence": proposal.confidence,
        "linked_plan_id": proposal.linked_plan_id,
        "linked_task_id": proposal.linked_task_id,
        "raw_snapshot_hash": proposal.raw_snapshot_hash,
        "summary": proposal.summary,
    }


def _applied(
    proposal: CodexStateReconciliationProposal,
    *,
    progress_id: str,
    artifact_id: str,
) -> CodexStateAppliedProposal:
    return CodexStateAppliedProposal(
        proposal_id=proposal.proposal_id,
        action_type=proposal.action_type,
        action_status="applied",
        progress_id=progress_id,
        artifact_id=artifact_id,
        source_kind=proposal.source_kind,
        source_database=proposal.source_database,
        source_table=proposal.source_table,
        source_id=proposal.source_id,
        observed_at=proposal.observed_at,
        confidence=proposal.confidence,
        linked_plan_id=proposal.linked_plan_id,
        linked_task_id=proposal.linked_task_id,
        raw_snapshot_hash=proposal.raw_snapshot_hash,
        summary=_progress_summary(proposal),
    )


def _skipped(
    proposal: CodexStateReconciliationProposal,
    skip_reason: str,
) -> CodexStateSkippedProposal:
    return CodexStateSkippedProposal(
        proposal_id=proposal.proposal_id,
        action_type=proposal.action_type,
        action_status="skipped",
        skip_reason=skip_reason,
        source_kind=proposal.source_kind,
        source_database=proposal.source_database,
        source_table=proposal.source_table,
        source_id=proposal.source_id,
        observed_at=proposal.observed_at,
        confidence=proposal.confidence,
        linked_plan_id=proposal.linked_plan_id,
        linked_task_id=proposal.linked_task_id,
        raw_snapshot_hash=proposal.raw_snapshot_hash,
        summary=f"Skipped Codex state proposal {proposal.proposal_id}: {skip_reason}.",
    )


def _proposal_from_payload(payload: object) -> CodexStateReconciliationProposal:
    if not isinstance(payload, dict):
        raise CodexStateReconciliationApplyError("proposal entries must be objects")
    return CodexStateReconciliationProposal(
        proposal_id=_required_string(payload, "proposal_id"),
        action_type=_required_string(payload, "action_type"),
        action_status=_required_string(payload, "action_status"),
        source_kind=_required_string(payload, "source_kind"),
        source_database=_required_string(payload, "source_database"),
        source_table=_required_string(payload, "source_table"),
        source_id=_required_string(payload, "source_id"),
        observed_at=_required_string(payload, "observed_at"),
        confidence=_required_string(payload, "confidence"),
        linked_plan_id=_optional_string(payload, "linked_plan_id"),
        linked_task_id=_optional_string(payload, "linked_task_id"),
        raw_snapshot_hash=_required_string(payload, "raw_snapshot_hash"),
        summary=_required_string(payload, "summary"),
    )


def _finding_from_payload(payload: object) -> CodexStateReconciliationFinding:
    if not isinstance(payload, dict):
        raise CodexStateReconciliationApplyError("finding entries must be objects")
    return CodexStateReconciliationFinding(
        finding_type=_required_string(payload, "finding_type"),
        source_database=_optional_string(payload, "source_database"),
        source_table=_optional_string(payload, "source_table"),
        source_id=_required_string(payload, "source_id"),
        observed_at=_required_string(payload, "observed_at"),
        failure_class=_required_string(payload, "failure_class"),
        summary=_required_string(payload, "summary"),
    )


def _required_list(payload: dict[Any, Any], field_name: str) -> list[object]:
    value = payload.get(field_name)
    if not isinstance(value, list):
        raise CodexStateReconciliationApplyError(f"{field_name} must be a list")
    return value


def _required_string(payload: dict[Any, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise CodexStateReconciliationApplyError(f"{field_name} must be a nonblank string")
    return value


def _optional_string(payload: dict[Any, Any], field_name: str) -> str:
    value = payload.get(field_name, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CodexStateReconciliationApplyError(f"{field_name} must be a string")
    return value
