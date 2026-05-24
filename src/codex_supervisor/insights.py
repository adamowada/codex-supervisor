"""Reusable insight record contracts for durable learning updates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

INSIGHT_CONFIDENCE_LABELS = ("confirmed", "inferred", "needs validation")


class InsightContractError(ValueError):
    """Raised when a reusable insight record violates the insight contract."""


@dataclass(frozen=True)
class InsightRecord:
    """One reusable, provenance-backed workflow lesson."""

    claim: str
    confidence: str
    evidence: tuple[str, ...]
    scope: str
    next_action: str
    supersedes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonblank("claim", self.claim)
        _require_vocab("confidence", self.confidence, INSIGHT_CONFIDENCE_LABELS)
        _require_nonempty_string_tuple("evidence", self.evidence)
        _require_nonblank("scope", self.scope)
        _require_nonblank("next_action", self.next_action)
        _require_string_tuple("supersedes", self.supersedes)


def validate_insight_record_payload(payload: object) -> InsightRecord:
    """Validate a JSON-like insight payload into a typed insight record."""

    if not isinstance(payload, dict):
        msg = "insight payload must be a JSON object"
        raise InsightContractError(msg)
    return InsightRecord(
        claim=_required_string(payload, "claim"),
        confidence=_required_string(payload, "confidence"),
        evidence=_required_string_tuple(payload, "evidence"),
        scope=_required_string(payload, "scope"),
        supersedes=_optional_string_tuple(payload, "supersedes"),
        next_action=_next_action(payload),
    )


def _next_action(payload: dict[Any, Any]) -> str:
    if "next_action" in payload:
        return _required_string(payload, "next_action")
    return _required_string(payload, "next action")


def _required_string(payload: dict[Any, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or _is_blank(value):
        msg = f"{field_name} must be nonblank"
        raise InsightContractError(msg)
    return value


def _required_string_tuple(payload: dict[Any, Any], field_name: str) -> tuple[str, ...]:
    if field_name not in payload:
        msg = f"{field_name} must be present"
        raise InsightContractError(msg)
    value = payload[field_name]
    if not isinstance(value, list):
        msg = f"{field_name} must be a list"
        raise InsightContractError(msg)
    values = _string_tuple(value, field_name)
    _require_nonempty_string_tuple(field_name, values)
    return values


def _optional_string_tuple(payload: dict[Any, Any], field_name: str) -> tuple[str, ...]:
    value = payload.get(field_name, ())
    if value in (None, ()):
        return ()
    if not isinstance(value, list):
        msg = f"{field_name} must be a list"
        raise InsightContractError(msg)
    return _string_tuple(value, field_name)


def _string_tuple(value: list[object], field_name: str) -> tuple[str, ...]:
    values = tuple(item for item in value if isinstance(item, str) and item.strip())
    if len(values) != len(value):
        msg = f"{field_name} entries must be nonblank strings"
        raise InsightContractError(msg)
    return values


def _require_nonempty_string_tuple(field_name: str, value: tuple[str, ...]) -> None:
    if not value:
        msg = f"{field_name} must be nonempty"
        raise InsightContractError(msg)
    _require_string_tuple(field_name, value)


def _require_string_tuple(field_name: str, value: tuple[str, ...]) -> None:
    for item in value:
        _require_nonblank(f"{field_name} entry", item)


def _require_vocab(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        msg = f"{field_name} must be one of: {', '.join(allowed)}"
        raise InsightContractError(msg)


def _require_nonblank(field_name: str, value: str | None) -> None:
    if _is_blank(value):
        msg = f"{field_name} must be nonblank"
        raise InsightContractError(msg)


def _is_blank(value: str | None) -> bool:
    return value is None or value.strip() == ""
