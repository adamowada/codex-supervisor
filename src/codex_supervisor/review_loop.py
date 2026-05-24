"""Typed review loop contracts."""

from __future__ import annotations

from dataclasses import dataclass

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
