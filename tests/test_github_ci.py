from __future__ import annotations

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

    assert "uses: actions/checkout@v4" in text
    assert "uses: astral-sh/setup-uv@v5" in text
    assert "uses: actions/setup-python@v5" in text
    assert 'python-version: "3.14"' in text
    assert "run: uv sync --dev --locked" in text
    assert "run: uv run python -B scripts/verify.py --publication-ready" in text


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _meaningful_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if line.strip()]
