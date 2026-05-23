---
name: windows-shell-quoting
description: Handle Windows PowerShell command construction, quoting, here-strings, regexes, paths, and safe cleanup. Use when shell commands contain nested quotes, JSON, regex, paths with spaces, inline Python, git/rg queries, or file deletion/move on Windows.
---

# Windows Shell Quoting

Prefer simple native PowerShell commands. Use here-strings for complex inline code.

## Patterns

- Use `-LiteralPath` for exact filesystem paths.
- Use single quotes for regex strings unless interpolation is needed.
- Use PowerShell here-strings for inline Python or JSON-heavy snippets.
- Avoid noisy command separators; run parallel reads as separate tool calls when possible.
- For recursive delete or move, resolve the target and verify it stays inside the intended workspace.
- Do not enumerate paths in PowerShell and pipe them to `cmd /c` for destructive actions.
- Use structured parsers for JSON, TOML, SQLite, and lockfiles when practical.

If PowerShell parsing fights the task, move complex data processing into a short inline Python script.
