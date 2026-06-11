"""Launch a Codex worker process from the packaged plugin.

The supervisor calls this script through attempt-run. The script keeps the
Windows PowerShell/codex.ps1 invocation in one tested place and feeds the
worker prompt through stdin so prompt text is never split into argv.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_CODEX_EXEC_ARGS = (
    "exec",
    "--skip-git-repo-check",
    "--dangerously-bypass-approvals-and-sandbox",
)
DEFAULT_REASONING_EFFORT = "xhigh"
REASONING_EFFORTS = ("low", "medium", "high", "xhigh")
REASONING_EFFORT_CONFIG_KEY = "model_reasoning_effort"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    workspace = args.workspace.resolve()
    prompt_file = args.prompt_file.resolve()
    codex_executable = resolve_codex_executable(args.codex_executable)
    prompt = prompt_file.read_text(encoding="utf-8")
    command = build_codex_exec_command(
        codex_executable,
        workspace,
        reasoning_effort=args.reasoning_effort,
    )
    completed = subprocess.run(
        command,
        cwd=workspace,
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return completed.returncode


def resolve_codex_executable(configured: str | None = None) -> Path:
    candidate = configured or os.environ.get("CODEX_SUPERVISOR_CODEX_EXECUTABLE")
    if candidate:
        resolved = shutil.which(candidate)
        path = Path(resolved) if resolved is not None else Path(candidate)
        if path.exists():
            return path.resolve()
        raise SystemExit(f"Codex executable not found: {candidate}")

    candidate_names = ("codex.ps1", "codex.cmd", "codex.exe", "codex") if os.name == "nt" else (
        "codex",
    )
    for name in candidate_names:
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved).resolve()
    raise SystemExit(
        "Codex executable not found. Set CODEX_SUPERVISOR_CODEX_EXECUTABLE to codex or codex.ps1."
    )


def build_codex_exec_command(
    codex_executable: Path,
    workspace: Path,
    *,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    platform_name: str | None = None,
) -> tuple[str, ...]:
    if reasoning_effort not in REASONING_EFFORTS:
        raise ValueError(
            "reasoning_effort must be one of: " + ", ".join(REASONING_EFFORTS)
        )
    reasoning_config = (
        "-c",
        f'{REASONING_EFFORT_CONFIG_KEY}="{reasoning_effort}"',
    )
    platform = platform_name or os.name
    if platform == "nt" and codex_executable.suffix.casefold() == ".ps1":
        return (
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(codex_executable),
            *DEFAULT_CODEX_EXEC_ARGS,
            *reasoning_config,
            "-C",
            str(workspace),
        )
    return (
        str(codex_executable),
        *DEFAULT_CODEX_EXEC_ARGS,
        *reasoning_config,
        "-C",
        str(workspace),
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch a Codex worker process.")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--codex-executable")
    parser.add_argument(
        "--reasoning-effort",
        choices=REASONING_EFFORTS,
        default=DEFAULT_REASONING_EFFORT,
        help="Codex reasoning effort for the worker; defaults to xhigh.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
