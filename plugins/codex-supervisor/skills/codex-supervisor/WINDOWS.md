# Windows Rules

Use these rules when operating `codex-supervisor` from Windows or PowerShell.

## Worker Launch

- You **MUST** use the plugin CLI launcher for supervisor mutation commands:
  `python -B scripts/cli_launcher.py <command> ...`
- You **MUST** run full AFK work through `attempt-run`.
- When launching Codex as the worker, you **MUST** invoke the resolved `codex.ps1` script through
  PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File <codex.ps1> exec ...
```

- Do not assume `codex exec ...` is directly executable by Python process launch on Windows.

## Verifiers

- You **MUST NOT** put complex PowerShell logic inline in `--verify-command`.
- You **MUST** prefer a workspace Python verifier at `.codex-supervisor/verify.py`.
- Invoke Python verifiers with:

```powershell
python -B .codex-supervisor\verify.py
```

- If a PowerShell verifier is unavoidable, write it to `.codex-supervisor\verify.ps1` and invoke it
  with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .codex-supervisor\verify.ps1
```

- PowerShell verifier scripts **MUST** start with `$ErrorActionPreference = "Stop"`.

## Retry

- When the task intent is unchanged, you **MUST** retry the same task instead of creating a new plan
  or task only to recover from Windows launch or quoting failures.
