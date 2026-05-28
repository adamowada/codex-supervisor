# Cross-Platform CI Assumptions

## Windows-Local Success Does Not Prove Linux CI Safety

- `claim`: Platform-specific assumptions that pass on the developer's Windows machine can still
  fail Linux CI at type-check, path-resolution, process, shell, or evidence-validation boundaries.
  Treat every Windows-only API or path behavior as an explicit adapter contract, not as ordinary
  portable Python.
- `confidence`: confirmed.
- `evidence`: GitHub Actions `Verify` run `26552849566` failed Linux mypy on commit
  `6fb05018e9f48f8e3adb4712b8c1412f7ad19395` because
  `src/codex_supervisor/story_loop.py` accessed `ctypes.windll` directly. The repair commit
  `9aed4a031b04634fdcb5711403cac24113176ca0` changed the Windows process probe to resolve
  `windll` dynamically before touching `kernel32`, and follow-up run `26553235403` passed. Earlier
  CI lessons in `insights/workflow-patterns.md` record the same class of drift for Windows-style
  relative path separators and clean-checkout Linux evidence semantics.
- `scope`: Python code paths that touch OS-specific APIs, subprocesses, path parsing, shell
  commands, filesystem evidence, terminal encoding, and type-checkable platform stubs.
- `supersedes`: none.
- `next action`: when adding or reviewing code that mentions Windows-only names, POSIX-only names,
  shell-specific syntax, path separators, or platform-gated stdlib attributes, require one of:
  a typed adapter boundary, a `sys.platform`/feature probe, `getattr`-guarded optional access,
  cross-platform fixtures, or an explicit CI-only regression test. Do not treat a Windows
  publication-ready local pass as proof that Linux CI mypy and path semantics are covered.

## Review Checklist

- Search changed Python for platform-sensitive APIs: `ctypes.windll`, `msvcrt`, `winreg`,
  `os.name`, `sys.platform`, `subprocess`, `shell=True`, `PureWindowsPath`, `PurePosixPath`,
  manual separators, and terminal encoding assumptions.
- For optional platform attributes, prefer feature detection at the boundary and return a
  structured unavailable state on other platforms.
- For path inputs, normalize human-authored Windows separators before resolving and keep absolute
  drive/root rejection explicit.
- For CI-only failures, first ask whether local state, OS, checkout depth, ignored runtime roots, or
  shell encoding differs from the runner before weakening the failing guard.
