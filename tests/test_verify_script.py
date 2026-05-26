from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def test_verification_scripts_compile():
    scripts_root = Path(__file__).resolve().parents[1] / "scripts"
    script_paths = sorted(scripts_root.glob("check_*.py"))
    script_paths.append(scripts_root / "verify.py")
    script_paths.append(scripts_root / "verify_codex_plugin_install.py")

    for script_path in script_paths:
        compile(script_path.read_text(encoding="utf-8"), str(script_path), "exec")


def _load_verify_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "verify.py"
    spec = importlib.util.spec_from_file_location("codex_supervisor_verify_script", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verify_commands_can_enable_publication_ready_gate():
    verify = _load_verify_module()

    default_commands = verify.build_commands()
    publication_commands = verify.build_commands(publication_ready=True)
    python = sys.executable

    assert default_commands == (
        (python, "-m", "pytest", "-p", "no:cacheprovider"),
        (python, "-m", "ruff", "check", ".", "--no-cache"),
        (python, "-m", "ruff", "format", "--check", ".", "--no-cache"),
        (python, "-m", "mypy", "--no-incremental", "src", "scripts"),
        (python, "-m", "codex_supervisor.cli", "--help"),
        ("uv", "run", "--no-sync", "codex-supervisor", "--help"),
        (python, "scripts/check_file_justification.py"),
        (python, "scripts/check_public_repo_hygiene.py"),
        (python, "scripts/check_planning_integrity.py"),
        (python, "scripts/check_skill_inventory.py"),
        (python, "scripts/check_source_inventory.py"),
        (python, "scripts/check_protected_files.py"),
        ("uv", "lock", "--check"),
    )

    assert any(
        command[-1] == "scripts/check_public_repo_hygiene.py" for command in default_commands
    )
    assert not any("--publication-ready" in command for command in default_commands)
    assert any(
        command[-2:] == ("scripts/check_public_repo_hygiene.py", "--publication-ready")
        for command in publication_commands
    )
    assert (python, "scripts/verify_codex_plugin_install.py") in publication_commands
    assert ("uv", "build", "--wheel", "--sdist") in publication_commands
    assert (python, "scripts/verify_codex_plugin_install.py") not in default_commands


def test_verify_main_stops_at_first_failed_command(monkeypatch, tmp_path):
    verify = _load_verify_module()
    calls: list[tuple[str, ...]] = []

    def fake_run(command, *, check, cwd, env):
        calls.append(tuple(command))
        assert check is False
        assert cwd == tmp_path
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(verify, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(verify.subprocess, "run", fake_run)

    assert verify.main([]) == 7
    assert calls == [verify.build_commands()[0]]
