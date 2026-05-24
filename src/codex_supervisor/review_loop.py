"""Typed review loop contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

REVIEW_MODES = (
    "everything",
    "code_quality",
    "architecture",
    "source_of_truth_drift",
)
FINDING_SEVERITIES = ("P0", "P1", "P2", "P3")
FINDING_STATUSES = ("accepted", "waived", "needs_hitl")


class ReviewContractError(ValueError):
    """Raised when a review finding or repair draft violates the contract."""


@dataclass(frozen=True)
class ReviewLocation:
    """Location or scope that grounds a review finding."""

    path: str | None = None
    line: int | None = None
    scope: str | None = None

    def __post_init__(self) -> None:
        if _is_blank(self.path) and _is_blank(self.scope):
            msg = "review location requires path or scope"
            raise ReviewContractError(msg)
        if self.line is not None and self.line < 1:
            msg = "review location line must be positive"
            raise ReviewContractError(msg)
        if self.line is not None and _is_blank(self.path):
            msg = "review location line requires a path"
            raise ReviewContractError(msg)


@dataclass(frozen=True)
class ReviewFinding:
    """One classified review finding with waiver or repair-routing status."""

    finding_id: str
    mode: str
    severity: str
    status: str
    title: str
    evidence: str
    location: ReviewLocation
    recommendation: str
    waiver_rationale: str | None = None
    allowed_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank("finding_id", self.finding_id)
        _require_vocab("mode", self.mode, REVIEW_MODES)
        _require_vocab("severity", self.severity, FINDING_SEVERITIES)
        _require_vocab("status", self.status, FINDING_STATUSES)
        _require_nonblank("title", self.title)
        _require_nonblank("evidence", self.evidence)
        _require_nonblank("recommendation", self.recommendation)
        for allowed_path in self.allowed_paths:
            _require_nonblank("allowed_paths entry", allowed_path)
        if self.status == "waived":
            _require_nonblank("waiver_rationale", self.waiver_rationale)


@dataclass(frozen=True)
class RepairTaskDraft:
    """Focused repair work derived from one accepted review finding."""

    source_finding_id: str
    review_mode: str
    severity: str
    title: str
    goal: str
    allowed_paths: tuple[str, ...]


@dataclass(frozen=True)
class ReviewVerificationEvidence:
    """One verification command result attached to a review result."""

    command: str
    exit_code: int
    summary: str

    def __post_init__(self) -> None:
        _require_nonblank("verification command", self.command)
        if not isinstance(self.exit_code, int) or isinstance(self.exit_code, bool):
            msg = "verification exit_code must be an integer"
            raise ReviewContractError(msg)
        _require_nonblank("verification summary", self.summary)


@dataclass(frozen=True)
class ReviewResult:
    """Validated structured output from a review lane."""

    review_id: str
    mode: str
    target: str
    findings: tuple[ReviewFinding, ...]
    verification_evidence: tuple[ReviewVerificationEvidence, ...]

    def __post_init__(self) -> None:
        _require_nonblank("review_id", self.review_id)
        _require_vocab("mode", self.mode, REVIEW_MODES)
        _require_nonblank("target", self.target)
        if not self.verification_evidence:
            msg = "verification_evidence must be nonempty"
            raise ReviewContractError(msg)

    @property
    def accepted_findings(self) -> tuple[ReviewFinding, ...]:
        """Return findings accepted for repair."""

        return tuple(finding for finding in self.findings if finding.status == "accepted")

    @property
    def waived_findings(self) -> tuple[ReviewFinding, ...]:
        """Return findings waived with rationale."""

        return tuple(finding for finding in self.findings if finding.status == "waived")

    @property
    def repair_task_drafts(self) -> tuple[RepairTaskDraft, ...]:
        """Return repair task drafts for all accepted findings."""

        return tuple(repair_task_draft_from_finding(finding) for finding in self.accepted_findings)


def repair_task_draft_from_finding(finding: ReviewFinding) -> RepairTaskDraft:
    """Convert an accepted finding into a focused repair task draft."""

    if finding.status != "accepted":
        msg = f"only accepted findings can become repair task drafts: {finding.finding_id}"
        raise ReviewContractError(msg)
    allowed_paths = finding.allowed_paths or _location_allowed_paths(finding.location)
    return RepairTaskDraft(
        source_finding_id=finding.finding_id,
        review_mode=finding.mode,
        severity=finding.severity,
        title=f"Fix {finding.severity} review finding: {finding.title}",
        goal=(
            f"Fix accepted {finding.severity} review finding {finding.finding_id}: "
            f"{_sentence_fragment(finding.title)}. "
            f"Evidence: {_sentence_fragment(finding.evidence)}. "
            f"Recommendation: {_sentence_fragment(finding.recommendation)}."
        ),
        allowed_paths=allowed_paths,
    )


def validate_review_result_payload(payload: object) -> ReviewResult:
    """Validate a JSON-object review result payload into typed review evidence."""

    if not isinstance(payload, dict):
        msg = "review result payload must be a JSON object"
        raise ReviewContractError(msg)
    findings_value = payload.get("findings")
    if not isinstance(findings_value, list):
        msg = "findings must be a list"
        raise ReviewContractError(msg)
    verification_value = payload.get("verification_evidence")
    if not isinstance(verification_value, list):
        msg = "verification_evidence must be a list"
        raise ReviewContractError(msg)
    return ReviewResult(
        review_id=_required_string(payload, "review_id"),
        mode=_required_string(payload, "mode"),
        target=_required_string(payload, "target"),
        findings=tuple(_finding_from_payload(item) for item in findings_value),
        verification_evidence=tuple(
            _verification_from_payload(item) for item in verification_value
        ),
    )


def _finding_from_payload(payload: object) -> ReviewFinding:
    if not isinstance(payload, dict):
        msg = "finding entries must be objects"
        raise ReviewContractError(msg)
    return ReviewFinding(
        finding_id=_required_string(payload, "finding_id"),
        mode=_required_string(payload, "mode"),
        severity=_required_string(payload, "severity"),
        status=_required_string(payload, "status"),
        title=_required_string(payload, "title"),
        evidence=_required_string(payload, "evidence"),
        location=_location_from_payload(payload.get("location")),
        recommendation=_required_string(payload, "recommendation"),
        waiver_rationale=_optional_string(payload, "waiver_rationale"),
        allowed_paths=_optional_string_tuple(payload, "allowed_paths"),
    )


def _location_from_payload(payload: object) -> ReviewLocation:
    if not isinstance(payload, dict):
        msg = "finding location must be an object"
        raise ReviewContractError(msg)
    line = payload.get("line")
    if line is not None and (not isinstance(line, int) or isinstance(line, bool)):
        msg = "finding location line must be an integer"
        raise ReviewContractError(msg)
    return ReviewLocation(
        path=_optional_string(payload, "path"),
        line=line,
        scope=_optional_string(payload, "scope"),
    )


def _verification_from_payload(payload: object) -> ReviewVerificationEvidence:
    if not isinstance(payload, dict):
        msg = "verification_evidence entries must be objects"
        raise ReviewContractError(msg)
    exit_code = payload.get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        msg = "verification exit_code must be an integer"
        raise ReviewContractError(msg)
    return ReviewVerificationEvidence(
        command=_required_string(payload, "command"),
        exit_code=exit_code,
        summary=_required_string(payload, "summary"),
    )


def _required_string(payload: dict[Any, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or _is_blank(value):
        msg = f"{field_name} must be nonblank"
        raise ReviewContractError(msg)
    return value


def _optional_string(payload: dict[Any, Any], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"{field_name} must be a string"
        raise ReviewContractError(msg)
    return value


def _optional_string_tuple(payload: dict[Any, Any], field_name: str) -> tuple[str, ...]:
    value = payload.get(field_name, ())
    if value in (None, ()):
        return ()
    if not isinstance(value, list):
        msg = f"{field_name} must be a list"
        raise ReviewContractError(msg)
    values = tuple(item for item in value if isinstance(item, str) and item.strip())
    if len(values) != len(value):
        msg = f"{field_name} entries must be nonblank strings"
        raise ReviewContractError(msg)
    return values


def _location_allowed_paths(location: ReviewLocation) -> tuple[str, ...]:
    if not _is_blank(location.path):
        return (str(location.path),)
    return ()


def _require_vocab(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        msg = f"{field_name} must be one of: {', '.join(allowed)}"
        raise ReviewContractError(msg)


def _require_nonblank(field_name: str, value: str | None) -> None:
    if _is_blank(value):
        msg = f"{field_name} must be nonblank"
        raise ReviewContractError(msg)


def _is_blank(value: str | None) -> bool:
    return value is None or value.strip() == ""


def _sentence_fragment(value: str) -> str:
    return value.strip().rstrip(".")
