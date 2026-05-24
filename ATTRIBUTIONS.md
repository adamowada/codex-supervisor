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
| `mattpocock-skills` | `https://github.com/mattpocock/skills` | MIT | Integrated selected engineering skills and supporting references as repo-local skills. |
| `mattpocock-sandcastle` | `https://github.com/mattpocock/sandcastle` | MIT | Study sandboxed orchestration, worktrees, branch flow, implementation, and review loops. |
| `mattpocock-evalite` | `https://github.com/mattpocock/evalite` | MIT | Study eval harness patterns for prompts, skills, and workers. |
| `mattpocock-agent-rules-books` | `https://github.com/mattpocock/agent-rules-books` | MIT | Study concise rule-pack and skill-pack design. |
| `mattpocock-agent-browser` | `https://github.com/mattpocock/agent-browser` | Apache-2.0 | Study browser automation APIs designed for coding agents. |
| `mattpocock-node-DeepResearch` | `https://github.com/mattpocock/node-DeepResearch` | Apache-2.0 | Study bounded research, search, read, and synthesis loops. |
| `snarktank-ralph` | `https://github.com/snarktank/ralph` | MIT | Study fresh-context autonomous coding loops, PRD-to-story execution, progress logs, checks, and stop conditions. |

## Reuse Rules

- Treat cloned repositories under `sources/` as ignored references, not vendored dependencies.
- Review each upstream license before copying source, tests, prompts, or docs.
- Record a decision before direct code reuse or integration.
- Preserve upstream copyright, license, and notice requirements when reuse is approved.

## Integrated Skill Material

Selected files under `.agents/skills/` are copied, adapted, or synthesized from
`https://github.com/mattpocock/skills` at source clone commit `b8be62f`.

Copied and adapted for Codex-supervisor source-of-truth, planning SQLite, GitHub connector,
and full-auto worker workflows:

- `.agents/skills/improve-codebase-architecture/`
- `.agents/skills/grill-with-docs/`
- `.agents/skills/to-issues/`
- `.agents/skills/triage/`
- `.agents/skills/diagnose/`
- `.agents/skills/tdd/`
- `.agents/skills/prototype/`
- `.agents/skills/zoom-out/`

Adapted or synthesized from Matt Pocock skill patterns:

- `.agents/skills/setup-agent-docs/`
- `.agents/skills/fresh-thread-code-reviewer/`
- `.agents/skills/skill-router/`

The upstream project is MIT licensed:

```text
MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
