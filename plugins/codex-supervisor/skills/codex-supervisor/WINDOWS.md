# Windows Rules

Use these rules when operating `codex-supervisor` from Windows or PowerShell.

## Worker Launch

- You **MUST** use the plugin CLI launcher for supervisor mutation commands:
  `python -B scripts/cli_launcher.py <command> ...`
- You **MUST** run every product file mutation through `attempt-run`.
- When launching Codex as the worker on Windows, you **MUST** use the packaged worker launcher:

```powershell
python -B <plugin-root>\scripts\codex_worker_launcher.py --workspace <workspace> --prompt-file <workspace>\.codex-supervisor\worker_prompt.txt
```

- You **MUST NOT** create ad hoc `run_worker.ps1` launch scripts for Codex workers.
- You **MUST NOT** pass the worker prompt as a command-line argument.
- The packaged worker launcher is the only Windows Codex worker launch path. It resolves
  `codex.ps1`, invokes it through PowerShell, and pipes the prompt through stdin.
- The packaged worker launcher defaults Codex workers to xhigh reasoning. Pass
  `--reasoning-effort low`, `medium`, `high`, or `xhigh` only when the user explicitly asks for a
  different reasoning level.
- Set `CODEX_SUPERVISOR_CODEX_EXECUTABLE` only when the worker must use a specific `codex` or
  `codex.ps1` executable.
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
