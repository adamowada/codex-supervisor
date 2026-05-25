from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_supervisor.cli import main
from codex_supervisor.insight_updates import (
    apply_insight_update,
    render_insight_markdown_update,
)
from codex_supervisor.insights import validate_insight_record_payload


def test_render_insight_markdown_update_includes_durable_fields() -> None:
    record = validate_insight_record_payload(_insight_payload())

    update = render_insight_markdown_update(
        record,
        promotion_criteria=("Promote after two repeated reviewed uses.",),
        provenance=("worker-run-stage9c",),
    )

    assert update.anchor.startswith("insight-")
    assert "<!-- codex-supervisor:insight " in update.markdown
    assert "### Repeated workflow lessons should become durable insight records." in update.markdown
    assert "- Confidence: `confirmed`" in update.markdown
    assert "- Scope: codex-supervisor insight learning loop" in update.markdown
    assert "#### Evidence" in update.markdown
    assert "- insights/README.md:Reusable Insight Shape" in update.markdown
    assert "#### Supersedes" in update.markdown
    assert "- chat-only lesson notes" in update.markdown
    assert "#### Next Action" in update.markdown
    assert "Validate insight payloads before writing durable memory." in update.markdown
    assert "#### Promotion Criteria" in update.markdown
    assert "- Promote after two repeated reviewed uses." in update.markdown
    assert "#### Provenance" in update.markdown
    assert "- worker-run-stage9c" in update.markdown


def test_apply_insight_update_is_idempotent_for_stable_anchor(tmp_path: Path) -> None:
    record = validate_insight_record_payload(_insight_payload())
    target_path = tmp_path / "graph.md"
    target_path.write_text("# Graph\n\nExisting notes.\n", encoding="utf-8")

    first = apply_insight_update(
        target_path,
        record,
        promotion_criteria=("Promote after two repeated reviewed uses.",),
        provenance=("worker-run-stage9c",),
    )
    second = apply_insight_update(
        target_path,
        record,
        promotion_criteria=("Promote after two repeated reviewed uses.",),
        provenance=("worker-run-stage9c",),
    )

    text = target_path.read_text(encoding="utf-8")

    assert first.changed is True
    assert second.changed is False
    assert first.anchor == second.anchor
    assert text.count(f"<!-- codex-supervisor:insight {first.anchor} -->") == 1
    assert text.count("Repeated workflow lessons should become durable insight records.") == 1


def test_insight_update_cli_rejects_invalid_payload_without_state_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    plans_path = tmp_path / "plans" / "planning.sqlite3"
    target_path = tmp_path / "insights" / "graph.md"
    plans_path.parent.mkdir()
    target_path.parent.mkdir()
    plans_bytes = b"planning db placeholder"
    target_text = "# Graph\n"
    plans_path.write_bytes(plans_bytes)
    target_path.write_text(target_text, encoding="utf-8")
    insight_path = _write_insight_payload(
        tmp_path,
        {
            "claim": "Missing evidence is invalid.",
            "confidence": "confirmed",
            "scope": "codex-supervisor insight learning loop",
            "next_action": "Reject this payload.",
        },
    )
    files_before = _relative_files(tmp_path)

    exit_code = main(
        [
            "insight-update",
            "--insight-path",
            str(insight_path),
            "--target-path",
            str(target_path),
            "--promotion-criterion",
            "Promote only after review.",
            "--json",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "Could not update insight: evidence must be present" in captured.err
    assert plans_path.read_bytes() == plans_bytes
    assert target_path.read_text(encoding="utf-8") == target_text
    assert _relative_files(tmp_path) == files_before


def test_insight_update_cli_outputs_json_for_render_and_apply(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    insight_path = _write_insight_payload(tmp_path, _insight_payload())
    target_path = tmp_path / "graph.md"
    target_path.write_text("# Graph\n", encoding="utf-8")

    exit_code = main(
        [
            "insight-update",
            "--insight-path",
            str(insight_path),
            "--target-path",
            str(target_path),
            "--promotion-criterion",
            "Promote after two repeated reviewed uses.",
            "--provenance",
            "worker-run-stage9c",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload["changed"] is True
    assert payload["target_path"] == str(target_path)
    assert payload["anchor"].startswith("insight-")
    assert "Promotion Criteria" in payload["markdown"]
    assert "worker-run-stage9c" in payload["markdown"]
    assert target_path.read_text(encoding="utf-8").count(payload["anchor"]) == 2


def _write_insight_payload(tmp_path: Path, payload: dict[str, object]) -> Path:
    insight_path = tmp_path / "insight.json"
    insight_path.write_text(json.dumps(payload), encoding="utf-8")
    return insight_path


def _insight_payload() -> dict[str, object]:
    return {
        "claim": "Repeated workflow lessons should become durable insight records.",
        "confidence": "confirmed",
        "evidence": [
            "insights/README.md:Reusable Insight Shape",
            "plans/planning.sqlite3:progress-stage9a-review-completed-20260524",
        ],
        "scope": "codex-supervisor insight learning loop",
        "supersedes": ["chat-only lesson notes"],
        "next_action": "Validate insight payloads before writing durable memory.",
    }


def _relative_files(root: Path) -> tuple[str, ...]:
    return tuple(
        sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    )
