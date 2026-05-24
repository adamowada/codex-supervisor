# Source Index

Generated during repository bootstrap. `sources/README.md` is the authority for source URLs, clone
paths, pinned commits, observed license posture, license evidence, and source use posture.
`ATTRIBUTIONS.md` is the authority for reuse rules and copied/adapted material actually present in
this repository. This file is only the knowledge-graph index of why each source matters.

## Cloned Sources

The table below records observed relevance, not adoption. Treat each row together with the
`Synthesis State` table before using a source as implementation evidence.

| Source | Useful for | Use posture |
| --- | --- | --- |
| `sources/openai-codex` | Codex CLI, `codex exec`, MCP experiments, config and automation behavior. | Study and adapter inspiration under Apache-2.0/NOTICE requirements. |
| `sources/harnesslab-claw-code-agent` | Python agent runtime patterns, background sessions, task/plan runtime, compaction, GUI. | Reference-only until upstream license posture is clarified. |
| `sources/openclaw-openclaw` | Always-on local control plane, channels, tools, sessions, skills, cron, sandboxing. | MIT-licensed inspiration for local control-plane design. |
| `sources/mattpocock-skills` | Small composable skills: grilling, TDD, handoff, issue slicing, architecture review. | MIT-licensed selected skill material is copied/adapted with attribution. |
| `sources/mattpocock-sandcastle` | Sandboxed agent orchestration, worktrees, branch strategies, implement/review factory. | MIT-licensed inspiration for worker/worktree orchestration. |
| `sources/mattpocock-evalite` | Skill/prompt/worker eval harness inspiration. | MIT-licensed inspiration for eval loops. |
| `sources/mattpocock-agent-rules-books` | Mini/nano rule packs and guidance for skills vs always-on instructions. | MIT-licensed inspiration; preserve upstream attribution before copying. |
| `sources/mattpocock-agent-browser` | JSON browser automation and snapshot/ref workflow for agents. | Apache-2.0 inspiration for browser tooling patterns. |
| `sources/mattpocock-node-DeepResearch` | Bounded search/read/reason loop for research workers. | Apache-2.0 inspiration for bounded research loops. |
| `sources/snarktank-ralph` | Fresh-context autonomous coding loop, PRD-to-story execution, progress logs, checks, and stop conditions. | MIT-licensed conceptual inspiration for one-story loops. |

## Documentation Sources

| Source | Useful for | Last verified |
| --- | --- | --- |
| `https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex` | Official Codex Goals concepts: durable objective, validation loop, lifecycle commands, stop conditions, and requirement for a Goals-capable Codex build. | 2026-05-24 |
| `https://developers.openai.com/codex/use-cases/follow-goals` | Official Codex Goal workflow, `/goal` lifecycle, strong-goal setup loop, and `features.goals` config fallback. | 2026-05-24 |

## Use Policy

Use these sources as inspiration unless a later decision explicitly approves direct integration or
code reuse. License-unclear sources require extra review before any copying.

## Synthesis State

| Source | Current synthesis state | Next action |
| --- | --- | --- |
| `sources/mattpocock-skills` | Adopted selectively into repo-local skills with MIT attribution and decision coverage. | Keep tightening skills through golden evals and Adam-specific review. |
| `sources/snarktank-ralph` | Synthesized into Story Loop doctrine and Goal Contract workflow. | Revisit during Stage 6 backend implementation. |
| `sources/openai-codex` | Inventoried and used for Codex CLI/config inspiration; not yet deeply synthesized into backend contracts. | Re-scan before implementing Stage 6 Codex Exec backend. |
| `sources/openclaw-openclaw` | Inventoried as local control-plane inspiration; no adopted implementation claims yet. | Create Stage 6/7 insight cards before copying patterns. |
| `sources/harnesslab-claw-code-agent` | Reference-only until license posture is clarified; no copied material. | Keep as study material only unless license/permission changes. |
| `sources/mattpocock-sandcastle` | Inventoried for worktree/worker orchestration; not yet converted into concrete implementation contracts. | Re-scan during worktree/backend design. |
| `sources/mattpocock-evalite` | Inventoried for eval-loop inspiration; not yet converted into skill eval fixtures. | Re-scan during Stage 8 skill-learning work. |
| `sources/mattpocock-agent-rules-books` | Inventoried for rule-pack doctrine; not yet copied. | Use as comparison material before adding new always-on rules. |
| `sources/mattpocock-agent-browser` | Inventoried for browser automation patterns; not yet adopted. | Re-scan only when browser-worker tooling enters scope. |
| `sources/mattpocock-node-DeepResearch` | Inventoried for bounded research loops; not yet adopted. | Re-scan when research-worker contracts enter scope. |
