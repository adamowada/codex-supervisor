from __future__ import annotations

import pytest

from codex_supervisor.insights import (
    INSIGHT_CONFIDENCE_LABELS,
    InsightContractError,
    validate_insight_record_payload,
)


def test_validate_insight_record_payload_accepts_reusable_insight_shape() -> None:
    record = validate_insight_record_payload(_insight_payload())

    assert record.claim == "Repeated workflow lessons should become durable queue tasks."
    assert record.confidence == "confirmed"
    assert record.confidence in INSIGHT_CONFIDENCE_LABELS
    assert record.evidence == (
        "plans/planning.sqlite3:progress-stage9a-task-shaped-20260524",
        "insights/README.md:Reusable Insight Shape",
    )
    assert record.scope == "codex-supervisor planning and skill learning"
    assert record.supersedes == ("chat-only follow-up notes",)
    assert record.next_action == "Add a focused Stage 9 validation slice."


def test_validate_insight_record_payload_accepts_markdown_next_action_label() -> None:
    payload = _insight_payload()
    payload["next action"] = payload.pop("next_action")

    record = validate_insight_record_payload(payload)

    assert record.next_action == "Add a focused Stage 9 validation slice."


@pytest.mark.parametrize("confidence", ["", "done", "CONFIRMED", True])
def test_validate_insight_record_payload_rejects_invalid_confidence(confidence: object) -> None:
    payload = _insight_payload()
    payload["confidence"] = confidence

    with pytest.raises(InsightContractError, match="confidence"):
        validate_insight_record_payload(payload)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "expected"),
    [
        ("claim", "", "claim must be nonblank"),
        ("evidence", [], "evidence must be nonempty"),
        ("evidence", ["ok", ""], "evidence entries must be nonblank strings"),
        ("scope", "   ", "scope must be nonblank"),
        ("next_action", "", "next_action must be nonblank"),
        ("supersedes", ["old", ""], "supersedes entries must be nonblank strings"),
    ],
)
def test_validate_insight_record_payload_rejects_blank_required_values(
    field_name: str,
    bad_value: object,
    expected: str,
) -> None:
    payload = _insight_payload()
    payload[field_name] = bad_value

    with pytest.raises(InsightContractError, match=expected):
        validate_insight_record_payload(payload)


def test_validate_insight_record_payload_rejects_missing_required_fields() -> None:
    payload = _insight_payload()
    del payload["evidence"]

    with pytest.raises(InsightContractError, match="evidence must be present"):
        validate_insight_record_payload(payload)


def test_validate_insight_record_payload_does_not_require_supersedes() -> None:
    payload = _insight_payload()
    del payload["supersedes"]

    record = validate_insight_record_payload(payload)

    assert record.supersedes == ()


def _insight_payload() -> dict[str, object]:
    return {
        "claim": "Repeated workflow lessons should become durable queue tasks.",
        "confidence": "confirmed",
        "evidence": [
            "plans/planning.sqlite3:progress-stage9a-task-shaped-20260524",
            "insights/README.md:Reusable Insight Shape",
        ],
        "scope": "codex-supervisor planning and skill learning",
        "supersedes": ["chat-only follow-up notes"],
        "next_action": "Add a focused Stage 9 validation slice.",
    }
