# Codex Usage Skill Synthesis

Confidence: `confirmed`

This note summarizes the privacy-safe `.codex` audit used to seed repo-local skills on
2026-05-23. It intentionally records aggregate behavior, not private transcript content.

## Evidence

- `~/.codex` contained roughly 7.7k files and 2.6k directories.
- `sessions/` held roughly 1.7k JSONL session files plus a small archived-session set.
- `state_5.sqlite` tracked roughly 1.7k threads, 1.2k spawn edges, and 700+ dynamic tool rows.
- `logs_2.sqlite` contained roughly 400k log rows and 24k shell completions.
- `ambient-suggestions/` contained 100+ suggestions, nearly all pending.
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
- `fresh-thread-code-reviewer`
- `git-pr-ci-operator`
- `review-finding-fixer`
- `skill-golden-eval-loop`
- `source-evidence-attributor`
- `subagent-run-digest`
- `thread-resume-brief`
- `verification-command-picker`
- `windows-shell-quoting`
- `worktree-sandbox-guard`
- `skill-router` (added during integration cleanup)
- `codex-supervisor` (thin top-level orchestrator)
- `goal-contract-drafter` (added after Codex Goals research)
- `story-loop-runner` (added after Ralph research)

## Matt Pocock Skills Integrated

Confidence: `confirmed`

On 2026-05-23, `codex-supervisor` integrated the most relevant MIT-licensed
`mattpocock/skills` engineering skills as repo-local skills:

- `improve-codebase-architecture`
- `grill-with-docs`
- `setup-agent-docs` (adapted)
- `to-issues`
- `triage`
- `diagnose`
- `tdd`
- `prototype`
- `zoom-out`

The existing `fresh-thread-code-reviewer` skill was updated with Matt's Standards-vs-Spec review
axis instead of importing the in-progress `review` skill verbatim.

## Integration Cleanup

Confidence: `confirmed`

The integrated skills were normalized for Codex-supervisor on 2026-05-23:

- Upstream slash-command and agent-tool assumptions were replaced with Codex-native skill names and
  read-only explorer subagent language.
- Triage and issue publishing now prefer planning SQLite plus configured GitHub connector workflows.
- Architecture reports now target ignored local artifacts first and avoid external CDN dependencies
  unless explicitly useful.
- Glossary and ADR updates now respect the repo's configured source-of-truth and locking process.
- A top-level `codex-supervisor` skill now defines the operating loop, routes to smaller skills, and
  enforces global invariants without absorbing child-skill procedures.

## Goal And Story Loop Synthesis

Confidence: `confirmed`

Codex Goals and Ralph-informed one-story loops add a missing middle layer between planning SQLite and worker
execution:

- Goal Contracts define the thread/worker finish line.
- Story Loop policy constrains autonomous work to one ready vertical slice per iteration.
- planning SQLite remains the canonical queue; native Codex Goal state and one-story loop progress are
  reconciled as evidence.
