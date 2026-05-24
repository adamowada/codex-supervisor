from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_supervisor.cli import main


def test_insight_validate_cli_prints_normalized_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    insight_path = _write_insight_payload(tmp_path, _insight_payload())

    exit_code = main(["insight-validate", "--insight-path", str(insight_path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload == {
        "claim": "Repeated workflow lessons should become durable insight records.",
        "confidence": "confirmed",
        "evidence": [
            "insights/README.md:Reusable Insight Shape",
            "plans/planning.sqlite3:progress-stage9a-review-completed-20260524",
        ],
        "next_action": "Validate insight payloads before writing durable memory.",
        "scope": "codex-supervisor insight learning loop",
        "supersedes": ["chat-only lesson notes"],
    }


def test_insight_validate_cli_accepts_markdown_next_action_label(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = _insight_payload()
    payload["next action"] = payload.pop("next_action")
    insight_path = _write_insight_payload(tmp_path, payload)

    exit_code = main(["insight-validate", "--insight-path", str(insight_path), "--json"])

    captured = capsys.readouterr()
    normalized = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert normalized["next_action"] == "Validate insight payloads before writing durable memory."
    assert "next action" not in normalized


def test_insight_validate_cli_rejects_invalid_payload_without_state_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    plans_path = tmp_path / "plans" / "planning.sqlite3"
    graph_path = tmp_path / "insights" / "graph.md"
    plans_path.parent.mkdir()
    graph_path.parent.mkdir()
    plans_bytes = b"not a real db but must remain untouched"
    graph_text = "# Existing graph\n"
    plans_path.write_bytes(plans_bytes)
    graph_path.write_text(graph_text, encoding="utf-8")
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

    exit_code = main(["insight-validate", "--insight-path", str(insight_path), "--json"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "Could not validate insight: evidence must be present" in captured.err
    assert plans_path.read_bytes() == plans_bytes
    assert graph_path.read_text(encoding="utf-8") == graph_text
    assert _relative_files(tmp_path) == files_before


def test_insight_validate_cli_human_output_is_readable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    insight_path = _write_insight_payload(tmp_path, _insight_payload(supersedes=()))

    exit_code = main(["insight-validate", "--insight-path", str(insight_path)])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert "claim: Repeated workflow lessons should become durable insight records." in captured.out
    assert "supersedes:\n- none" in captured.out
    assert "next_action: Validate insight payloads before writing durable memory." in captured.out


def _write_insight_payload(tmp_path: Path, payload: dict[str, object]) -> Path:
    insight_path = tmp_path / "insight.json"
    insight_path.write_text(json.dumps(payload), encoding="utf-8")
    return insight_path


def _insight_payload(
    *, supersedes: tuple[str, ...] = ("chat-only lesson notes",)
) -> dict[str, object]:
    payload: dict[str, object] = {
        "claim": "Repeated workflow lessons should become durable insight records.",
        "confidence": "confirmed",
        "evidence": [
            "insights/README.md:Reusable Insight Shape",
            "plans/planning.sqlite3:progress-stage9a-review-completed-20260524",
        ],
        "scope": "codex-supervisor insight learning loop",
        "next_action": "Validate insight payloads before writing durable memory.",
    }
    if supersedes:
        payload["supersedes"] = list(supersedes)
    return payload


def _relative_files(root: Path) -> tuple[str, ...]:
    return tuple(
        sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    )
