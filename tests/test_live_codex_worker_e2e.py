from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from codex_supervisor.acp_gate import check_target_workspace_acp_gate

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "codex-supervisor"


@dataclass(frozen=True)
class LiveSmokeScenario:
    slug: str
    title: str
    intent: str
    prompt: str
    verifier_source: str
    product_artifacts: tuple[str, ...]
    seed_files: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class LiveSmokeResult:
    slug: str
    worker_exit_code: int
    verifier_exit_code: int | None
    accepted: bool
    task_status: str
    acp_ok: bool
    failures: tuple[str, ...]


@pytest.mark.skipif(
    os.environ.get("CODEX_SUPERVISOR_RUN_LIVE_CODEX_E2E") != "1",
    reason="set CODEX_SUPERVISOR_RUN_LIVE_CODEX_E2E=1 to run the live Codex worker e2e",
)
def test_live_codex_worker_smoke_ladder_scores_a_plus(tmp_path: Path) -> None:
    codex_executable = _resolve_codex_executable()
    results: list[LiveSmokeResult] = []

    for scenario in _live_smoke_scenarios():
        results.append(_run_live_smoke_scenario(tmp_path, scenario, codex_executable))

    grade = _grade_live_smoke_results(tuple(results))
    assert grade["letter"] == "A+", json.dumps(grade, indent=2, sort_keys=True)


def _run_live_smoke_scenario(
    tmp_path: Path,
    scenario: LiveSmokeScenario,
    codex_executable: Path,
) -> LiveSmokeResult:
    workspace = tmp_path / scenario.slug
    _prepare_git_workspace(workspace, scenario.seed_files)
    db_path = workspace / ".codex-supervisor" / "planning.sqlite3"
    verifier_file = workspace / ".codex-supervisor" / "verify.py"
    prompt_file = workspace / ".codex-supervisor" / "worker_prompt.txt"
    product_artifacts = tuple(str(workspace / artifact) for artifact in scenario.product_artifacts)
    acceptance = "Live worker verifier passed for the scenario"

    _run_cli("plan-init", "--path", str(db_path), "--json")
    _run_cli(
        "task-create",
        "--path",
        str(db_path),
        "--plan-id",
        f"plan-{scenario.slug}",
        "--plan-title",
        scenario.title,
        "--plan-goal",
        "Run one live Codex worker smoke scenario through durable attempt evidence.",
        "--task-id",
        f"task-{scenario.slug}",
        "--title",
        scenario.title,
        "--intent",
        scenario.intent,
        "--assurance",
        "high",
        "--acceptance",
        acceptance,
        "--json",
    )
    _write_verifier(verifier_file, scenario.verifier_source)
    _write_worker_prompt(prompt_file, scenario.prompt)

    completed = _run_cli(
        "attempt-run",
        "--path",
        str(db_path),
        "--task-id",
        f"task-{scenario.slug}",
        "--attempt-id",
        f"attempt-{scenario.slug}",
        "--executor",
        "codex-worker-launcher",
        "--workspace",
        str(workspace),
        "--timeout-seconds",
        "300",
        "--summary",
        f"Assign {scenario.slug} to a real Codex worker process.",
        "--check",
        f"Live Codex worker completed the {scenario.slug} scenario.",
        *tuple(item for artifact in product_artifacts for item in ("--artifact", artifact)),
        "--verify-command",
        _shell_command((sys.executable, "-B", str(verifier_file))),
        "--acceptance-result",
        "pass",
        "--risk",
        "Live Codex worker behavior depends on the installed Codex CLI.",
        "--gap",
        "No known gap.",
        "--next-action",
        "No next action.",
        "--review-evidence",
        "Verifier and ACP gate results were inspected by the live smoke harness.",
        "--json",
        "--",
        *_codex_worker_launcher_command(codex_executable, workspace, prompt_file),
    )
    payload = json.loads(completed.stdout)
    acp = check_target_workspace_acp_gate(workspace, database_path=db_path)
    failures = _scenario_failures(
        scenario,
        payload=payload,
        acp_failures=acp.failures,
    )
    return LiveSmokeResult(
        slug=scenario.slug,
        worker_exit_code=payload["exit_code"],
        verifier_exit_code=payload["verifier_exit_code"],
        accepted=payload["transition"]["acceptance"]["accepted"] is True,
        task_status=payload["transition"]["task_status"],
        acp_ok=acp.ok,
        failures=failures,
    )


def _live_smoke_scenarios() -> tuple[LiveSmokeScenario, ...]:
    return (
        LiveSmokeScenario(
            slug="single-file",
            title="Single file creation",
            intent="Create one exact README file through a live Codex worker.",
            prompt=(
                "Read CODEX_SUPERVISOR_TASK_JSON for task context. In CODEX_SUPERVISOR_WORKSPACE, "
                "create README.md. The complete file content is exactly the text between "
                "BEGIN_README and END_README. Do not include the markers, blank lines after the "
                "heading, or any instruction text.\n"
                "BEGIN_README\n"
                "# Live Codex Worker\n"
                "END_README\n"
                "After writing, README.md must contain one heading line and one trailing newline. "
                "Do not edit files under .codex-supervisor."
            ),
            verifier_source=(
                "from pathlib import Path\n"
                "content = Path('README.md').read_text(encoding='utf-8')\n"
                "if content != '# Live Codex Worker\\n':\n"
                "    raise SystemExit('README.md content mismatch')\n"
                "print('single-file smoke verified')\n"
            ),
            product_artifacts=("README.md",),
        ),
        LiveSmokeScenario(
            slug="code-repair",
            title="Code repair and test creation",
            intent=(
                "Repair a tiny Python function and add a focused pytest test through a live "
                "Codex worker."
            ),
            prompt=(
                "Read CODEX_SUPERVISOR_TASK_JSON for task context. In CODEX_SUPERVISOR_WORKSPACE, "
                "update app/math_tools.py so add(left, right) returns the numeric sum. Create "
                "tests/test_math_tools.py with pytest coverage for add(2, 3) == 5 and "
                "add(-2, 5) == 3. Do not edit files under .codex-supervisor."
            ),
            verifier_source=(
                "import importlib.util\n"
                "from pathlib import Path\n"
                "module_path = Path('app/math_tools.py')\n"
                "spec = importlib.util.spec_from_file_location('math_tools', module_path)\n"
                "if spec is None or spec.loader is None:\n"
                "    raise SystemExit('could not load app/math_tools.py')\n"
                "module = importlib.util.module_from_spec(spec)\n"
                "spec.loader.exec_module(module)\n"
                "if module.add(2, 3) != 5 or module.add(-2, 5) != 3:\n"
                "    raise SystemExit('add() behavior mismatch')\n"
                "test_file = Path('tests/test_math_tools.py')\n"
                "if not test_file.is_file():\n"
                "    raise SystemExit('missing pytest coverage file')\n"
                "print('code-repair smoke verified')\n"
            ),
            product_artifacts=("app/math_tools.py", "tests/test_math_tools.py"),
            seed_files=(
                (
                    "app/math_tools.py",
                    "def add(left: int, right: int) -> int:\n    return 0\n",
                ),
            ),
        ),
        LiveSmokeScenario(
            slug="data-summary",
            title="Data summary with preserved inputs",
            intent=(
                "Read existing data, create a derived JSON summary, and update notes through a "
                "live Codex worker."
            ),
            prompt=(
                "Read CODEX_SUPERVISOR_TASK_JSON for task context. In CODEX_SUPERVISOR_WORKSPACE, "
                "read data/items.csv and create reports/inventory.json as JSON with keys "
                "total_items, total_quantity, and labels. There are three data rows, "
                "total_quantity must be 7, and labels must stay in CSV order. Set NOTES.md to "
                "exactly the text "
                "between BEGIN_NOTES and END_NOTES. Do not include the markers, punctuation after "
                "synchronized, or any other lines.\n"
                "BEGIN_NOTES\n"
                "Inventory notes\n"
                "Status: synchronized\n"
                "END_NOTES\n"
                "Do not edit data/items.csv or files under .codex-supervisor."
            ),
            verifier_source=(
                "import json\n"
                "from pathlib import Path\n"
                "if Path('data/items.csv').read_text(encoding='utf-8') != "
                "'label,quantity\\nalpha,2\\nbeta,4\\ngamma,1\\n':\n"
                "    raise SystemExit('input CSV changed')\n"
                "payload = json.loads(Path('reports/inventory.json').read_text(encoding='utf-8'))\n"
                "if payload != {'total_items': 3, 'total_quantity': 7, "
                "'labels': ['alpha', 'beta', 'gamma']}:\n"
                "    raise SystemExit(f'inventory summary mismatch: {payload!r}')\n"
                "notes = Path('NOTES.md').read_text(encoding='utf-8')\n"
                "if notes != 'Inventory notes\\nStatus: synchronized\\n':\n"
                "    raise SystemExit('NOTES.md content mismatch')\n"
                "print('data-summary smoke verified')\n"
            ),
            product_artifacts=("reports/inventory.json", "NOTES.md"),
            seed_files=(
                ("data/items.csv", "label,quantity\nalpha,2\nbeta,4\ngamma,1\n"),
                ("NOTES.md", "Inventory notes\n"),
            ),
        ),
    )


def _scenario_failures(
    scenario: LiveSmokeScenario,
    *,
    payload: dict[str, object],
    acp_failures: tuple[str, ...],
) -> tuple[str, ...]:
    failures: list[str] = []
    if payload["exit_code"] != 0:
        failures.append(f"{scenario.slug}: worker exit code {payload['exit_code']}")
    if payload["verifier_exit_code"] != 0:
        failures.append(f"{scenario.slug}: verifier exit code {payload['verifier_exit_code']}")
    transition = payload["transition"]
    if not isinstance(transition, dict):
        return (*failures, f"{scenario.slug}: missing transition payload")
    acceptance = transition.get("acceptance")
    if not isinstance(acceptance, dict) or acceptance.get("accepted") is not True:
        failures.append(f"{scenario.slug}: acceptance was not recorded as accepted")
    if transition.get("task_status") != "done":
        failures.append(f"{scenario.slug}: task status is {transition.get('task_status')!r}")
    for failure in acp_failures:
        failures.append(f"{scenario.slug}: ACP gate failed: {failure}")
    return tuple(failures)


def _grade_live_smoke_results(results: tuple[LiveSmokeResult, ...]) -> dict[str, object]:
    checks: list[tuple[str, bool]] = []
    checks.append(("at least three scenarios ran", len(results) >= 3))
    for result in results:
        checks.extend(
            (
                (f"{result.slug} worker exited 0", result.worker_exit_code == 0),
                (f"{result.slug} verifier exited 0", result.verifier_exit_code == 0),
                (f"{result.slug} task accepted", result.accepted),
                (f"{result.slug} task done", result.task_status == "done"),
                (f"{result.slug} ACP gate passed", result.acp_ok),
            )
        )
    passed = sum(1 for _, ok in checks if ok)
    score = round(100 * passed / len(checks))
    failures = tuple(failure for result in results for failure in result.failures)
    letter = "A+" if score == 100 and not failures else _letter_for_score(score)
    return {
        "letter": letter,
        "score": score,
        "passed_checks": passed,
        "total_checks": len(checks),
        "failures": failures,
    }


def _letter_for_score(score: int) -> str:
    if score >= 97:
        return "A"
    if score >= 90:
        return "A-"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    return "F"


def _prepare_git_workspace(
    workspace: Path,
    seed_files: tuple[tuple[str, str], ...],
) -> None:
    workspace.mkdir(parents=True)
    _write_file(
        workspace / ".gitignore",
        ".codex-supervisor/\n.pytest_cache/\n__pycache__/\n*.pyc\n",
    )
    for relative_path, content in seed_files:
        _write_file(workspace / relative_path, content)
    _git(workspace, "init")
    _git(workspace, "add", ".")
    _git(
        workspace,
        "-c",
        "user.email=smoke@example.invalid",
        "-c",
        "user.name=Live Smoke",
        "commit",
        "-m",
        "baseline",
    )


def _resolve_codex_executable() -> Path:
    configured = os.environ.get("CODEX_SUPERVISOR_CODEX_EXECUTABLE")
    if configured:
        return Path(configured)
    candidate_names = (
        ("codex.ps1", "codex.cmd", "codex.exe", "codex") if os.name == "nt" else ("codex",)
    )
    for name in candidate_names:
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved)
    pytest.skip(
        "set CODEX_SUPERVISOR_CODEX_EXECUTABLE to the codex, codex.exe, codex.cmd, or "
        "codex.ps1 executable"
    )


def _codex_worker_launcher_command(
    codex_executable: Path,
    workspace: Path,
    prompt_file: Path,
) -> tuple[str, ...]:
    return (
        sys.executable,
        "-B",
        str(PLUGIN_ROOT / "scripts" / "codex_worker_launcher.py"),
        "--workspace",
        str(workspace),
        "--prompt-file",
        str(prompt_file),
        "--codex-executable",
        str(codex_executable),
    )


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (sys.executable, "-B", "-m", "codex_supervisor.cli", *args),
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=360,
        env=_cli_env(),
        check=True,
    )


def _cli_env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = (
        src_path if not env.get("PYTHONPATH") else src_path + os.pathsep + env["PYTHONPATH"]
    )
    return env


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_verifier(path: Path, source: str) -> None:
    _write_file(path, source)


def _write_worker_prompt(path: Path, prompt: str) -> None:
    _write_file(path, prompt)


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(workspace), *args),
        check=True,
        text=True,
        capture_output=True,
    )


def _shell_command(args: tuple[str, ...]) -> str:
    return subprocess.list2cmdline(args)
