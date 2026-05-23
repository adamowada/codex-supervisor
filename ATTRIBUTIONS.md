# Attributions

`codex-supervisor` is MIT-licensed original work. It currently uses the repositories below as
ignored local study sources and possible future integration references. Their source code is not
vendored into this repository.

## Inspiration Sources

| Source | Upstream | Observed license posture | Use posture |
| --- | --- | --- | --- |
| `openai-codex` | `https://github.com/openai/codex` | Apache-2.0; upstream `NOTICE` present | Study Codex CLI, `codex exec`, MCP, configuration, and automation behavior. |
| `harnesslab-claw-code-agent` | `https://github.com/HarnessLab/claw-code-agent` | No license file or package license found in the bootstrap clone | Reference-only unless the upstream license is clarified. |
| `openclaw-openclaw` | `https://github.com/openclaw/openclaw` | MIT | Study local-first control plane, sessions, tools, skills, cron, and sandboxing. |
| `mattpocock-skills` | `https://github.com/mattpocock/skills` | MIT | Study small composable skill design and handoff-oriented workflows. |
| `mattpocock-sandcastle` | `https://github.com/mattpocock/sandcastle` | MIT | Study sandboxed orchestration, worktrees, branch flow, implementation, and review loops. |
| `mattpocock-evalite` | `https://github.com/mattpocock/evalite` | MIT | Study eval harness patterns for prompts, skills, and workers. |
| `mattpocock-agent-rules-books` | `https://github.com/mattpocock/agent-rules-books` | MIT | Study concise rule-pack and skill-pack design. |
| `mattpocock-agent-browser` | `https://github.com/mattpocock/agent-browser` | Apache-2.0 | Study browser automation APIs designed for coding agents. |
| `mattpocock-node-DeepResearch` | `https://github.com/mattpocock/node-DeepResearch` | Apache-2.0 | Study bounded research, search, read, and synthesis loops. |

## Reuse Rules

- Treat cloned repositories under `sources/` as ignored references, not vendored dependencies.
- Review each upstream license before copying source, tests, prompts, or docs.
- Record a decision before direct code reuse or integration.
- Preserve upstream copyright, license, and notice requirements when reuse is approved.
