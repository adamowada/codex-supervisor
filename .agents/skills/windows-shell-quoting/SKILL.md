---
name: windows-shell-quoting
description: Handle Windows PowerShell command construction, quoting, here-strings, regexes, paths, and safe cleanup. Use when shell commands contain nested quotes, JSON, regex, paths with spaces, inline Python, git/rg queries, or file deletion/move on Windows.
---

# Windows Shell Quoting

Prefer simple native PowerShell commands. Use here-strings for complex inline code.

If the current user turn is read-only, review-only, audit-only, no-edits, or no-mutation, do not run
destructive cleanup, move, or rewrite commands. Return the exact safe command shape and validation
steps instead.

## Patterns

- Use `-LiteralPath` for exact filesystem paths.
- Use single quotes for regex strings unless interpolation is needed.
- Use PowerShell here-strings for inline Python or JSON-heavy snippets.
- When passing JSON as an argument to a native executable such as `python`, build the JSON with
  `ConvertTo-Json -Compress` and double embedded quotes before invocation:
  `$jsonArg = ($json -replace '"','""')`. Validate with a tiny `python -c
  "import sys; print(repr(sys.argv[1]))" $jsonArg` probe before using it for repo mutations.
  Prefer stdin, a temp file, or an inline Python script when JSON quoting grows complex.
- Avoid noisy command separators; run parallel reads as separate tool calls when possible.
- For recursive delete or move, resolve the target and verify it stays inside the intended workspace.
- Do not enumerate paths in PowerShell and pipe them to `cmd /c` for destructive actions.
- Use structured parsers for JSON, TOML, SQLite, and lockfiles when practical.

If PowerShell parsing fights the task, move complex data processing into a short inline Python script.
