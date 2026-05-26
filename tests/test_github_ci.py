from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "verify.yml"


def test_verify_workflow_runs_on_main_pushes_and_pull_requests() -> None:
    text = _workflow_text()
    lines = _meaningful_lines(text)

    assert "on:" in lines
    assert "  push:" in lines
    assert "  pull_request:" in lines
    assert lines.count("      - main") == 2
    assert "pull_request_target" not in text


def test_verify_workflow_uses_read_only_permissions_and_no_secrets() -> None:
    text = _workflow_text()

    assert "permissions:\n  contents: read\n" in text
    assert "contents: write" not in text
    assert "write-all" not in text
    assert "secrets." not in text


def test_verify_workflow_runs_repo_owned_publication_gate() -> None:
    text = _workflow_text()

    assert "uses: actions/checkout@" in text
    assert "fetch-depth: 0" in text
    assert "uses: astral-sh/setup-uv@" in text
    assert "uses: actions/setup-python@" in text
    assert 'python-version: "3.14"' in text
    assert "run: uv sync --dev --locked" in text
    assert "run: uv run python -B scripts/verify.py --publication-ready" in text


def test_verify_workflow_pins_external_actions_to_full_commit_shas() -> None:
    text = _workflow_text()
    uses_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("uses: ")]

    assert uses_lines
    assert "Supply-chain policy:" in text
    assert all(
        re.fullmatch(r"uses: [A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}", line)
        for line in uses_lines
    )
    assert not any(re.search(r"@(v\d+|main|master)$", line) for line in uses_lines)


def test_verify_workflow_pins_setup_uv_to_peeled_commit_not_tag_object() -> None:
    text = _workflow_text()

    assert "peeled reviewed release tags" in text
    assert "astral-sh/setup-uv@d4b2f3b6ecc6e67c4457f6d3e41ec42d3d0fcb86" in text
    assert "astral-sh/setup-uv@e58605a9b6da7c637471fab8847a5e5a6b8df081" not in text


def test_verify_workflow_fetches_history_for_planning_commit_links() -> None:
    text = _workflow_text()
    lines = _meaningful_lines(text)

    checkout_index = next(
        index
        for index, line in enumerate(lines)
        if line.strip().startswith("uses: actions/checkout@")
    )
    assert lines[checkout_index + 1].strip() == "with:"
    assert lines[checkout_index + 2].strip() == "fetch-depth: 0"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _meaningful_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if line.strip()]
