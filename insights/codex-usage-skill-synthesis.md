# Codex Usage Skill Synthesis

Confidence: `confirmed`

This note summarizes the privacy-safe `.codex` audit used to seed repo-local skills on
2026-05-23. It intentionally records aggregate behavior, not private transcript content.

## Evidence

- `~/.codex` contained about 7,656 files and 2,577 directories.
- `sessions/` held about 1,674 JSONL session files and `archived_sessions/` held 10 more.
- `state_5.sqlite` tracked 1,683 threads, 1,228 spawn edges, and 747 dynamic tool rows.
- `logs_2.sqlite` contained about 396k log rows and about 23.9k shell completions.
- `ambient-suggestions/` contained 112 suggestions, nearly all pending.
- `goals_1.sqlite`, `agent_jobs`, and app automation tables were present but effectively unused.

## Patterns

- First prompts are usually dense specs; follow-ups are shorter steering, correction, or verification
  requests.
- Manual rails recur: read-only audits, do-not-leak-private-content reminders, source-of-truth
  language, and explicit ACP instructions.
- Work frequently moves through inspect, patch, narrow verification, broad verification, commit, and
  push.
- Subagent fanout is common, especially explorer/worker split patterns and temp worktrees.
- Context compaction is common enough that handoff artifacts should be treated as a first-class
  workflow object.

## Skills Seeded

- `acp-publisher`
- `afk-issue-shaper`
- `ambient-suggestion-triager`
- `codex-state-readonly-audit`
- `context-compaction-handoff`
- `failure-loop-triage`
- `git-pr-ci-operator`
- `skill-golden-eval-loop`
- `source-evidence-attributor`
- `subagent-run-digest`
- `thread-resume-brief`
- `verification-command-picker`
- `windows-shell-quoting`
- `worktree-sandbox-guard`
