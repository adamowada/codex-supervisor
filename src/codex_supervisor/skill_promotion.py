"""Skill promotion proposal contracts and golden-eval evidence validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

GOLDEN_EVAL_STATUSES = ("passed", "failed")


class SkillPromotionContractError(ValueError):
    """Raised when a skill promotion proposal violates its contract."""


@dataclass(frozen=True)
class GoldenEvalEvidence:
    """Evidence from one golden task comparing baseline and candidate skill behavior."""

    task_id: str
    task_name: str
    baseline_summary: str
    candidate_summary: str
    status: str
    reviewer: str = ""
    automated_verdict_rationale: str = ""

    def __post_init__(self) -> None:
        _require_nonblank("task_id", self.task_id)
        _require_nonblank("task_name", self.task_name)
        _require_nonblank("baseline_summary", self.baseline_summary)
        _require_nonblank("candidate_summary", self.candidate_summary)
        _require_vocab("status", self.status, GOLDEN_EVAL_STATUSES)
        _require_optional_string("reviewer", self.reviewer)
        _require_optional_string("automated_verdict_rationale", self.automated_verdict_rationale)
        if _is_blank(self.reviewer) and _is_blank(self.automated_verdict_rationale):
            msg = "golden eval evidence must include reviewer or automated_verdict_rationale"
            raise SkillPromotionContractError(msg)


@dataclass(frozen=True)
class SkillPromotionProposal:
    """A proposed repo-local skill promotion backed by provenance and eval evidence."""

    skill_name: str
    motivation: str
    provenance: tuple[str, ...]
    rollback_plan: str
    changed_paths: tuple[str, ...]
    golden_evals: tuple[GoldenEvalEvidence, ...]

    def __post_init__(self) -> None:
        _require_nonblank("skill_name", self.skill_name)
        _require_nonblank("motivation", self.motivation)
        _require_nonempty_string_tuple("provenance", self.provenance)
        _require_nonblank("rollback_plan", self.rollback_plan)
        _require_nonempty_string_tuple("changed_paths", self.changed_paths)
        for changed_path in self.changed_paths:
            _require_repo_relative_path("changed_paths entry", changed_path)
        if not self.golden_evals:
            msg = "golden_evals must be nonempty"
            raise SkillPromotionContractError(msg)
        for evidence in self.golden_evals:
            if not isinstance(evidence, GoldenEvalEvidence):
                msg = "golden_evals entries must be GoldenEvalEvidence"
                raise SkillPromotionContractError(msg)


def validate_skill_promotion_payload(payload: object) -> SkillPromotionProposal:
    """Validate a JSON-like skill promotion payload into a typed proposal."""

    if not isinstance(payload, dict):
        msg = "skill promotion payload must be a JSON object"
        raise SkillPromotionContractError(msg)
    return SkillPromotionProposal(
        skill_name=_required_string(payload, "skill_name"),
        motivation=_required_string(payload, "motivation"),
        provenance=_required_string_tuple(payload, "provenance"),
        rollback_plan=_required_string(payload, "rollback_plan"),
        changed_paths=_required_repo_path_tuple(payload, "changed_paths"),
        golden_evals=_golden_eval_evidence_tuple(payload),
    )


def _golden_eval_evidence_tuple(payload: dict[Any, Any]) -> tuple[GoldenEvalEvidence, ...]:
    if "golden_evals" in payload:
        value = payload["golden_evals"]
    elif "golden_eval_evidence" in payload:
        value = payload["golden_eval_evidence"]
    else:
        msg = "golden_evals must be present"
        raise SkillPromotionContractError(msg)
    if not isinstance(value, list):
        msg = "golden_evals must be a list"
        raise SkillPromotionContractError(msg)
    if not value:
        msg = "golden_evals must be nonempty"
        raise SkillPromotionContractError(msg)
    return tuple(_golden_eval_evidence(item) for item in value)


def _golden_eval_evidence(value: object) -> GoldenEvalEvidence:
    if not isinstance(value, dict):
        msg = "golden_evals entries must be JSON objects"
        raise SkillPromotionContractError(msg)
    return GoldenEvalEvidence(
        task_id=_required_string(value, "task_id"),
        task_name=_required_string(value, "task_name"),
        baseline_summary=_required_string(value, "baseline_summary"),
        candidate_summary=_required_string(value, "candidate_summary"),
        status=_required_string(value, "status"),
        reviewer=_optional_string(value, "reviewer"),
        automated_verdict_rationale=_optional_string(
            value,
            "automated_verdict_rationale",
        ),
    )


def _required_string(payload: dict[Any, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or _is_blank(value):
        msg = f"{field_name} must be nonblank"
        raise SkillPromotionContractError(msg)
    return value


def _optional_string(payload: dict[Any, Any], field_name: str) -> str:
    value = payload.get(field_name, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        msg = f"{field_name} must be a string"
        raise SkillPromotionContractError(msg)
    return value


def _required_string_tuple(payload: dict[Any, Any], field_name: str) -> tuple[str, ...]:
    if field_name not in payload:
        msg = f"{field_name} must be present"
        raise SkillPromotionContractError(msg)
    value = payload[field_name]
    if not isinstance(value, list):
        msg = f"{field_name} must be a list"
        raise SkillPromotionContractError(msg)
    values = tuple(item for item in value if isinstance(item, str) and item.strip())
    if len(values) != len(value):
        msg = f"{field_name} entries must be nonblank strings"
        raise SkillPromotionContractError(msg)
    _require_nonempty_string_tuple(field_name, values)
    return values


def _required_repo_path_tuple(payload: dict[Any, Any], field_name: str) -> tuple[str, ...]:
    return tuple(
        _normalize_repo_relative_path(path, field_name)
        for path in _required_string_tuple(payload, field_name)
    )


def _normalize_repo_relative_path(path: str, field_name: str) -> str:
    value = path.strip()
    _require_repo_relative_path(f"{field_name} entry", value)
    return value


def _require_repo_relative_path(field_name: str, value: str) -> None:
    if "\\" in value:
        msg = f"{field_name} must use / separators"
        raise SkillPromotionContractError(msg)
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        msg = f"{field_name} must be repo-relative"
        raise SkillPromotionContractError(msg)
    parts = tuple(part for part in value.split("/") if part)
    if not parts or len(parts) != len(value.split("/")):
        msg = f"{field_name} must be a normalized repo-relative path"
        raise SkillPromotionContractError(msg)
    if any(part in (".", "..") for part in parts):
        msg = f"{field_name} must not contain traversal segments"
        raise SkillPromotionContractError(msg)


def _require_nonempty_string_tuple(field_name: str, value: tuple[str, ...]) -> None:
    if not value:
        msg = f"{field_name} must be nonempty"
        raise SkillPromotionContractError(msg)
    for item in value:
        _require_nonblank(f"{field_name} entry", item)


def _require_vocab(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        msg = f"{field_name} must be one of: {', '.join(allowed)}"
        raise SkillPromotionContractError(msg)


def _require_optional_string(field_name: str, value: str) -> None:
    if not isinstance(value, str):
        msg = f"{field_name} must be a string"
        raise SkillPromotionContractError(msg)


def _require_nonblank(field_name: str, value: str | None) -> None:
    if _is_blank(value):
        msg = f"{field_name} must be nonblank"
        raise SkillPromotionContractError(msg)


def _is_blank(value: str | None) -> bool:
    return value is None or value.strip() == ""
