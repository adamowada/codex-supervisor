"""Launch the codex-supervisor CLI from a plugin install."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from mcp_launcher import SOURCE_ENV_VAR, find_repo_root

WORKSPACE_DATABASE_COMMANDS = {
    "plan-init",
    "task-create",
    "queue-next",
    "attempt-transition",
    "attempt-run",
}


def main(argv: list[str] | None = None) -> int:
    """Resolve the source repo and forward arguments to the compact CLI."""

    invocation_cwd = Path.cwd().resolve()
    plugin_root = Path(__file__).resolve().parents[1]
    repo_root = find_repo_root(plugin_root, os.environ)
    if repo_root is None:
        print(
            "Could not locate codex-supervisor source repo. "
            f"Set {SOURCE_ENV_VAR} to the repo root before running the plugin CLI launcher.",
            file=sys.stderr,
        )
        return 1

    cli_args = _with_workspace_database_default(
        argv if argv is not None else sys.argv[1:],
        invocation_cwd=invocation_cwd,
    )
    command = (
        sys.executable,
        "-B",
        "-m",
        "codex_supervisor.cli",
        *cli_args,
    )
    completed = subprocess.run(
        command,
        cwd=repo_root,
        env=_pythonpath_env(repo_root, os.environ),
        check=False,
    )
    return completed.returncode


def _with_workspace_database_default(
    argv: list[str],
    *,
    invocation_cwd: Path,
) -> tuple[str, ...]:
    """Bind supervisor paths before the launcher switches to the source repo cwd."""

    if not argv:
        return ()
    command = argv[0]
    supervisor_args, worker_args = _split_worker_args(argv)
    if (
        command not in WORKSPACE_DATABASE_COMMANDS
        or _has_supervisor_option(supervisor_args, "-h")
        or _has_supervisor_option(supervisor_args, "--help")
    ):
        return tuple(argv)
    bound_args = list(supervisor_args)
    if not _has_supervisor_option(bound_args, "--path"):
        database_path = invocation_cwd / ".codex-supervisor" / "planning.sqlite3"
        bound_args[1:1] = ("--path", str(database_path))
    return (
        *_resolve_supervisor_path_options(
            bound_args,
            invocation_cwd=invocation_cwd,
        ),
        *worker_args,
    )


def _split_worker_args(argv: list[str]) -> tuple[list[str], tuple[str, ...]]:
    try:
        separator_index = argv.index("--")
    except ValueError:
        return list(argv), ()
    return list(argv[:separator_index]), tuple(argv[separator_index:])


def _resolve_supervisor_path_options(
    argv: list[str],
    *,
    invocation_cwd: Path,
) -> tuple[str, ...]:
    if not argv:
        return ()
    command = argv[0]
    path_options = {"--path"}
    if command == "attempt-run":
        path_options.update({"--workspace", "--launch-packet", "--verifier-intent"})
    resolved = list(argv)
    index = 1
    while index < len(resolved):
        item = resolved[index]
        if item in path_options and index + 1 < len(resolved):
            resolved[index + 1] = _resolve_invocation_path(
                resolved[index + 1],
                invocation_cwd=invocation_cwd,
            )
            index += 2
            continue
        matched = next(
            (
                option
                for option in path_options
                if item.startswith(f"{option}=")
            ),
            None,
        )
        if matched is not None:
            raw_value = item.split("=", 1)[1]
            resolved[index] = (
                f"{matched}="
                + _resolve_invocation_path(raw_value, invocation_cwd=invocation_cwd)
            )
        index += 1
    return tuple(resolved)


def _resolve_invocation_path(value: str, *, invocation_cwd: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((invocation_cwd / path).resolve())


def _has_supervisor_option(argv: list[str], option: str) -> bool:
    """Return whether a supervisor CLI option appears before worker argv begins."""

    for item in argv[1:]:
        if item == option:
            return True
        if option == "--path" and item.startswith("--path="):
            return True
    return False


def _pythonpath_env(repo_root: Path, environ: dict[str, str]) -> dict[str, str]:
    env = dict(environ)
    src_path = str(repo_root / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not existing else src_path + os.pathsep + existing
    return env


if __name__ == "__main__":
    raise SystemExit(main())
