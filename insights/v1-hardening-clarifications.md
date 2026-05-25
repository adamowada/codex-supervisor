# V1 Hardening Clarifications

- `claim`: The v1 hardening run is authorized to proceed as mainline, verified, live Codex work, but
  only one writer slice should run at a time until integration conflict policy is implemented.
- `confidence`: confirmed
- `evidence`: `plans/planning.sqlite3` plan `plan-v1-hardening-clarifications`,
  `DECISIONS.md` D-0013 through D-0018, and the 2026-05-25 Codex CLI smoke showing npm
  `codex-cli 0.133.0` with `codex exec --help` available.
- `scope`: v1 hardening, live Codex workers and reviewers, MCP mutation defaults, project
  scaffolding, project adapters, ACP cadence, release boundary, and skill promotion.
- `supersedes`: `insights/open-questions.md`
- `next action`: Implement v1 hardening as sequential vertical slices. Each slice should record
  planning progress, update insights only for durable lessons, run focused and publication-ready
  verification, then ACP to `main` after confirming remote `main` has not moved.

## Durable Answers

- Default live Codex launches use the user's normal Codex home. Expose `--codex-home` when an
  operator needs explicit isolation or alternate credentials.
- Mutating MCP tools are enabled by default. A user-facing flag may disable mutation when a
  read-only surface is desired.
- Live review is a production capability and should launch real Codex subagents or `codex exec`
  reviewer runs with structured evidence capture.
- Project scaffolding is real production behavior: it writes new project files and initializes
  planning SQLite, git checks, source locks, and first task contracts.
- The implementation remains Python-first. External projects can inform patterns, but they do not
  become a second orchestration core.
- Adapter work may rely on locally available repositories through ignored local configuration or
  runtime inputs. Tracked docs and planning rows must not store local absolute roots.
- Skill promotion needs a source-linked insight, a skill edit, a golden eval or focused test, and
  passing verification before ACP.
- Remote `main` moving before push is a HITL blocker, not an automatic rebase or merge prompt.
- Explicit live smoke verification must include real Codex or API work for capabilities that promise
  live Codex behavior; default CI can keep mocked subprocess coverage for reproducibility.
