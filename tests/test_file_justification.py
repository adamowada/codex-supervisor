from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType


def test_file_justification_accepts_known_bootstrap_categories(tmp_path):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    _write(tmp_path / "README.md", "repo")
    _write(tmp_path / "src" / "codex_supervisor" / "cli.py", "def main():\n    return 0\n")
    _write(tmp_path / ".agents" / "skills" / "demo" / "SKILL.md", "---\nname: demo\n---\n")

    failures = module.check_file_justification(tmp_path)

    assert failures == ()


def test_file_justification_rejects_unknown_public_files(tmp_path):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    _write(tmp_path / "scratch.md", "temporary")

    failures = module.check_file_justification(tmp_path)

    assert failures[0].relative_path == "scratch.md"
    assert "purpose category" in failures[0].reason


def test_file_justification_rejects_known_pattern_without_file_purpose(tmp_path):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    _write(tmp_path / "scripts" / "extra.py", "print('temporary')\n")

    failures = module.check_file_justification(tmp_path)

    assert failures[0].relative_path == "scripts/extra.py"
    assert failures[0].reason == "does not have a file-level purpose entry"


def test_file_justification_rejects_python_files_missing_required_marker(tmp_path):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    _write(tmp_path / "src" / "codex_supervisor" / "cli.py", "print('temporary')\n")

    failures = module.check_file_justification(tmp_path)

    assert failures[0].relative_path == "src/codex_supervisor/cli.py"
    assert "missing required purpose marker" in failures[0].reason


def test_file_justification_rejects_unknown_skill_support_files(tmp_path):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    _write(tmp_path / ".agents" / "skills" / "demo" / "REFERENCE.md", "temporary\n")

    failures = module.check_file_justification(tmp_path)

    assert failures[0].relative_path == ".agents/skills/demo/REFERENCE.md"
    assert failures[0].reason == "does not have a file-level purpose entry"


def test_file_justification_rejects_unknown_file_purpose_verifiers(tmp_path, monkeypatch):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    _write(tmp_path / "README.md", "repo\n")
    monkeypatch.setitem(
        module.FILE_PURPOSES,
        "README.md",
        module.FilePurpose("repo readme", "not-a-real-gate"),
    )

    failures = module.check_file_justification(tmp_path)

    assert failures[0].relative_path == "README.md"
    assert "not an allowed gate" in failures[0].reason


def test_file_justification_allows_manual_review_only_for_handoff(tmp_path, monkeypatch):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    _write(tmp_path / "README.md", "repo\n")
    monkeypatch.setitem(
        module.FILE_PURPOSES,
        "README.md",
        module.FilePurpose("repo readme", "manual review"),
    )

    failures = module.check_file_justification(tmp_path)

    assert failures[0].relative_path == "README.md"
    assert "not an allowed gate" in failures[0].reason


def test_file_justification_rejects_stale_manifest_entries_for_real_repo(tmp_path, monkeypatch):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    _write(tmp_path / "README.md", "repo\n")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setitem(
        module.FILE_PURPOSES,
        "missing.md",
        module.FilePurpose("stale purpose", "pytest"),
    )

    failures = module.check_file_justification(tmp_path)

    assert any(
        failure.relative_path == "missing.md"
        and "file-level purpose entry is stale" in failure.reason
        for failure in failures
    )


def test_file_justification_rejects_unknown_public_folders(tmp_path):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    _write(tmp_path / "scratch" / "README.md", "temporary")

    failures = module.check_file_justification(tmp_path)

    assert failures[0].relative_path == "scratch"
    assert "public-folder purpose category" in failures[0].reason


def test_file_justification_rejects_deleted_tracked_files(tmp_path):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    path = tmp_path / "docs" / "README.md"
    _write(path, "temporary\n")
    _git(tmp_path, "add", "docs/README.md")
    path.unlink()

    failures = module.check_file_justification(tmp_path)

    assert any(
        failure.relative_path == "docs/README.md"
        and "tracked file is deleted in the working tree" in failure.reason
        for failure in failures
    )


def test_file_justification_rejects_empty_public_text_files(tmp_path):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    _write(tmp_path / "README.md", "")

    failures = module.check_file_justification(tmp_path)

    assert failures[0].relative_path == "README.md"
    assert failures[0].reason == "public text file is empty"


def test_file_justification_rejects_invalid_utf8_public_text_files(tmp_path):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    path = tmp_path / "README.md"
    path.write_bytes(b"\xff\xfe")

    failures = module.check_file_justification(tmp_path)

    assert any(
        failure.relative_path == "README.md"
        and failure.reason == "public text file is not valid UTF-8"
        for failure in failures
    )


def test_file_justification_rejects_empty_json_and_suffixless_text_files(tmp_path):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    _write(tmp_path / "worker-results" / "bootstrap-landmine-worker-result.json", "")
    _write(tmp_path / "LICENSE", "")

    failures = module.check_file_justification(tmp_path)
    failures_by_path = {failure.relative_path: failure.reason for failure in failures}

    assert failures_by_path["worker-results/bootstrap-landmine-worker-result.json"] == (
        "public text file is empty"
    )
    assert failures_by_path["LICENSE"] == "public text file is empty"


def test_file_justification_rejects_non_markdown_insights_files(tmp_path):
    module = _load_file_justification_module()
    _git(tmp_path, "init")
    _write(tmp_path / "insights" / "worker-result.json", "{}")

    failures = module.check_file_justification(tmp_path)

    assert any(
        failure.relative_path == "insights/worker-result.json"
        and failure.reason == "insights/ is reserved for synthesized durable learning markdown"
        for failure in failures
    )


def _load_file_justification_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_file_justification.py"
    spec = importlib.util.spec_from_file_location("check_file_justification", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(("git", *args), cwd=repo, check=True, capture_output=True)
