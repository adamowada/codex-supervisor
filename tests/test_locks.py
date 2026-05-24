from __future__ import annotations

import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import codex_supervisor
from codex_supervisor.locks import check_protected_files, sha256_file, untracked_protected_files


def test_check_protected_files_reports_changed_file(tmp_path):
    protected = tmp_path / "README.md"
    protected.write_text("hello\n", encoding="utf-8")

    expected = sha256_file(protected)
    assert check_protected_files(tmp_path, {"README.md": expected}) == ()

    protected.write_text("changed\n", encoding="utf-8")
    failures = check_protected_files(tmp_path, {"README.md": expected})

    assert len(failures) == 1
    assert failures[0].relative_path == "README.md"
    assert failures[0].reason == "changed"


def test_check_protected_files_reports_missing_file(tmp_path):
    failures = check_protected_files(tmp_path, {"README.md": "abc"})

    assert len(failures) == 1
    assert failures[0].reason == "missing"


def test_untracked_protected_files_reports_files_missing_from_index(tmp_path):
    subprocess.run(("git", "init"), cwd=tmp_path, check=True, capture_output=True)
    protected = tmp_path / "README.md"
    protected.write_text("hello\n", encoding="utf-8")

    assert untracked_protected_files(tmp_path, ("README.md",)) == ("README.md",)

    subprocess.run(("git", "add", "README.md"), cwd=tmp_path, check=True, capture_output=True)

    assert untracked_protected_files(tmp_path, ("README.md",)) == ()


def test_check_protected_files_script_reports_manifest_drift(tmp_path, monkeypatch, capsys):
    module = _load_script_module("check_protected_files")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "PROTECTED_FILES", ("README.md",))
    monkeypatch.setattr(module, "PROTECTED_FILE_HASHES", {"AGENTS.md": "abc"})

    assert module.main() == 1

    captured = capsys.readouterr()
    assert "manifest drifted" in captured.err


def test_check_protected_files_script_reports_untracked_and_changed_files(
    tmp_path, monkeypatch, capsys
):
    module = _load_script_module("check_protected_files")
    subprocess.run(("git", "init"), cwd=tmp_path, check=True, capture_output=True)
    readme = tmp_path / "README.md"
    readme.write_text("changed\n", encoding="utf-8")
    agents = tmp_path / "AGENTS.md"
    agents.write_text("untracked\n", encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "PROTECTED_FILES", ("README.md", "AGENTS.md"))
    monkeypatch.setattr(
        module,
        "PROTECTED_FILE_HASHES",
        {"README.md": "0" * 64, "AGENTS.md": sha256_file(agents)},
    )
    subprocess.run(("git", "add", "README.md"), cwd=tmp_path, check=True, capture_output=True)

    assert module.main() == 1

    captured = capsys.readouterr()
    assert "AGENTS.md: not tracked by git" in captured.err
    assert "README.md: changed" in captured.err


def test_print_protected_hashes_script_prints_current_mapping(tmp_path, monkeypatch, capsys):
    module = _load_script_module("print_protected_hashes")
    protected = tmp_path / "README.md"
    protected.write_text("hello\n", encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "PROTECTED_FILES", ("README.md",))

    assert module.main() == 0

    captured = capsys.readouterr()
    assert "PROTECTED_FILE_HASHES = {" in captured.out
    assert f'"README.md": "{sha256_file(protected)}"' in captured.out


def test_package_version_matches_pyproject():
    pyproject = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())

    assert codex_supervisor.__version__ == pyproject["project"]["version"]


def test_python_version_tooling_contract_matches_pyproject():
    repo_root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text())
    lock_text = (repo_root / "uv.lock").read_text(encoding="utf-8")

    assert pyproject["project"]["requires-python"] == ">=3.14"
    assert pyproject["tool"]["ruff"]["target-version"] == "py314"
    assert pyproject["tool"]["mypy"]["python_version"] == "3.14"
    assert 'requires-python = ">=3.14"' in lock_text


def _load_script_module(name: str) -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
