from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_supervisor.cli import main
from codex_supervisor.skill_promotion import (
    GOLDEN_EVAL_STATUSES,
    SkillPromotionContractError,
    validate_skill_promotion_payload,
)


def test_validate_skill_promotion_payload_accepts_eval_backed_proposal() -> None:
    proposal = validate_skill_promotion_payload(_proposal_payload())

    assert proposal.skill_name == "skill-golden-eval-loop"
    assert proposal.motivation == "Promote a narrower eval checklist after repeated review drift."
    assert proposal.provenance == (
        ".agents/skills/skill-golden-eval-loop/SKILL.md:Workflow",
        "insights/skill-learning-loop.md:Loop",
    )
    assert proposal.rollback_plan == "Revert the skill file and keep the old router entry."
    assert proposal.changed_paths == (".agents/skills/skill-golden-eval-loop/SKILL.md",)
    assert proposal.golden_evals[0].task_id == "golden-skill-eval-001"
    assert proposal.golden_evals[0].status == "passed"
    assert proposal.golden_evals[0].status in GOLDEN_EVAL_STATUSES
    assert proposal.golden_evals[0].reviewer == "fresh-thread reviewer"


def test_validate_skill_promotion_payload_accepts_automated_verdict_without_reviewer() -> None:
    payload = _proposal_payload()
    eval_payload = payload["golden_evals"][0]
    assert isinstance(eval_payload, dict)
    eval_payload.pop("reviewer")
    eval_payload["automated_verdict_rationale"] = "Golden fixture score improved from 3/5 to 5/5."

    proposal = validate_skill_promotion_payload(payload)

    assert proposal.golden_evals[0].reviewer == ""
    assert (
        proposal.golden_evals[0].automated_verdict_rationale
        == "Golden fixture score improved from 3/5 to 5/5."
    )


@pytest.mark.parametrize(
    ("field_name", "bad_value", "expected"),
    [
        ("provenance", [], "provenance must be nonempty"),
        ("rollback_plan", " ", "rollback_plan must be nonblank"),
        ("changed_paths", ["C:/project/.agents/skills/demo/SKILL.md"], "repo-relative"),
        ("changed_paths", ["src\\skill.py"], "must use / separators"),
    ],
)
def test_validate_skill_promotion_payload_rejects_missing_scope_evidence(
    field_name: str,
    bad_value: object,
    expected: str,
) -> None:
    payload = _proposal_payload()
    payload[field_name] = bad_value

    with pytest.raises(SkillPromotionContractError, match=expected):
        validate_skill_promotion_payload(payload)


def test_validate_skill_promotion_payload_rejects_missing_eval_evidence() -> None:
    payload = _proposal_payload()
    del payload["golden_evals"]

    with pytest.raises(SkillPromotionContractError, match="golden_evals must be present"):
        validate_skill_promotion_payload(payload)


def test_validate_skill_promotion_payload_rejects_eval_without_verdict_source() -> None:
    payload = _proposal_payload()
    eval_payload = payload["golden_evals"][0]
    assert isinstance(eval_payload, dict)
    eval_payload["reviewer"] = " "

    with pytest.raises(
        SkillPromotionContractError,
        match="reviewer or automated_verdict_rationale",
    ):
        validate_skill_promotion_payload(payload)


def test_validate_skill_promotion_payload_rejects_invalid_eval_status() -> None:
    payload = _proposal_payload()
    eval_payload = payload["golden_evals"][0]
    assert isinstance(eval_payload, dict)
    eval_payload["status"] = "better"

    with pytest.raises(SkillPromotionContractError, match="status must be one of"):
        validate_skill_promotion_payload(payload)


def test_skill_promotion_validate_cli_prints_normalized_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proposal_path = _write_proposal_payload(tmp_path, _proposal_payload())

    exit_code = main(["skill-promotion-validate", "--proposal-path", str(proposal_path), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload["skill_name"] == "skill-golden-eval-loop"
    assert payload["changed_paths"] == [".agents/skills/skill-golden-eval-loop/SKILL.md"]
    assert payload["golden_evals"] == [
        {
            "automated_verdict_rationale": "",
            "baseline_summary": "Old skill omitted rollback evidence.",
            "candidate_summary": "Revised skill required rollback and provenance.",
            "reviewer": "fresh-thread reviewer",
            "status": "passed",
            "task_id": "golden-skill-eval-001",
            "task_name": "Validate a skill change proposal.",
        }
    ]


def test_skill_promotion_validate_cli_rejects_invalid_payload_without_state_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    plans_path = tmp_path / "plans" / "planning.sqlite3"
    skill_path = tmp_path / ".agents" / "skills" / "skill-golden-eval-loop" / "SKILL.md"
    insight_path = tmp_path / "insights" / "skill-learning-loop.md"
    plans_path.parent.mkdir()
    skill_path.parent.mkdir(parents=True)
    insight_path.parent.mkdir()
    plans_bytes = b"not a real db but must remain untouched"
    skill_text = "# Existing skill\n"
    insight_text = "# Existing insight\n"
    plans_path.write_bytes(plans_bytes)
    skill_path.write_text(skill_text, encoding="utf-8")
    insight_path.write_text(insight_text, encoding="utf-8")
    proposal_path = _write_proposal_payload(
        tmp_path,
        {
            "skill_name": "skill-golden-eval-loop",
            "motivation": "Missing rollback must fail before edits.",
            "provenance": ["insights/skill-learning-loop.md:Loop"],
            "changed_paths": [".agents/skills/skill-golden-eval-loop/SKILL.md"],
            "golden_evals": [],
        },
    )
    files_before = _relative_files(tmp_path)

    exit_code = main(["skill-promotion-validate", "--proposal-path", str(proposal_path), "--json"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "Could not validate skill promotion proposal: rollback_plan must be nonblank" in (
        captured.err
    )
    assert plans_path.read_bytes() == plans_bytes
    assert skill_path.read_text(encoding="utf-8") == skill_text
    assert insight_path.read_text(encoding="utf-8") == insight_text
    assert _relative_files(tmp_path) == files_before


def test_skill_promotion_validate_cli_human_output_is_readable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proposal_path = _write_proposal_payload(tmp_path, _proposal_payload())

    exit_code = main(["skill-promotion-validate", "--proposal-path", str(proposal_path)])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert "skill_name: skill-golden-eval-loop" in captured.out
    assert "changed_paths:\n- .agents/skills/skill-golden-eval-loop/SKILL.md" in captured.out
    assert "golden_evals:\n- golden-skill-eval-001: passed" in captured.out


def _write_proposal_payload(tmp_path: Path, payload: dict[str, object]) -> Path:
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps(payload), encoding="utf-8")
    return proposal_path


def _proposal_payload() -> dict[str, object]:
    return {
        "skill_name": "skill-golden-eval-loop",
        "motivation": "Promote a narrower eval checklist after repeated review drift.",
        "provenance": [
            ".agents/skills/skill-golden-eval-loop/SKILL.md:Workflow",
            "insights/skill-learning-loop.md:Loop",
        ],
        "rollback_plan": "Revert the skill file and keep the old router entry.",
        "changed_paths": [".agents/skills/skill-golden-eval-loop/SKILL.md"],
        "golden_evals": [
            {
                "task_id": "golden-skill-eval-001",
                "task_name": "Validate a skill change proposal.",
                "baseline_summary": "Old skill omitted rollback evidence.",
                "candidate_summary": "Revised skill required rollback and provenance.",
                "status": "passed",
                "reviewer": "fresh-thread reviewer",
            }
        ],
    }


def _relative_files(root: Path) -> tuple[str, ...]:
    return tuple(
        sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    )
