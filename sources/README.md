# Sources

This directory contains shallow clones of public repositories used for inspiration and possible
integration experiments. Some are permissively licensed OSS; license-unclear repositories are
reference-only until reviewed.

The cloned repositories are ignored by git. Keep this README tracked so future agents understand why
the directory exists.

## Cloned Repositories

| Directory | Upstream | Local commit | Observed license posture | License evidence | Use posture |
| --- | --- | --- | --- | --- | --- |
| `openai-codex` | `https://github.com/openai/codex` | `7d47056ea42636271ac020b86347fbbef49490aa` | Apache-2.0; upstream NOTICE present | LICENSE sha256:d17f227e4df5da1600391338865ce0f3055211760a36688f816941d58232d8dc; NOTICE sha256:9d71575ecfd9a843fc1677b0efb08053c6ba9fd686a0de1a6f5382fd3c220915 | Study Codex CLI, codex exec, MCP, configuration, and automation behavior. |
| `harnesslab-claw-code-agent` | `https://github.com/HarnessLab/claw-code-agent` | `816bc3a2591910f4dd569e3b1fe24c35280abc5e` | No license file or package license found in the bootstrap clone | none found | Reference-only unless the upstream license is clarified. |
| `openclaw-openclaw` | `https://github.com/openclaw/openclaw` | `d485464dbc4b6a2f2302b24f42b42364fe90fa8e` | MIT | LICENSE sha256:9efd316ecf1c4c60f6fd5d26433142fff2b6794d7d328e9bc6179b29bf9c82a4 | Study local-first control plane, sessions, tools, skills, cron, and sandboxing. |
| `mattpocock-skills` | `https://github.com/mattpocock/skills` | `b8be62ffacb0118fa3eaa29a0923c87c8c11985c` | MIT | LICENSE sha256:0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5 | Integrated selected engineering skills and supporting references as repo-local skills. |
| `mattpocock-sandcastle` | `https://github.com/mattpocock/sandcastle` | `65063f6c8ea2fccde22d7d415be4d03212668678` | MIT | LICENSE sha256:0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5 | Study sandboxed orchestration, worktrees, branch flow, implementation, and review loops. |
| `mattpocock-evalite` | `https://github.com/mattpocock/evalite` | `e18a793789400b9292f92465d1084344340aef9b` | MIT | LICENSE sha256:d771b938c81101a190dcae20b14f19af77062361e8c4a57af97df26bc61025d7 | Study eval harness patterns for prompts, skills, and workers. |
| `mattpocock-agent-rules-books` | `https://github.com/mattpocock/agent-rules-books` | `a7d7649044505b9c377c8dca28d2d6a543bc7f8c` | MIT; local license copyright Maciej Ciemborowicz | LICENSE sha256:c21def7bbce1900717a361a06af67399903d31bd3a695757fff534d6698d1bdb | Study concise rule-pack and skill-pack design. |
| `mattpocock-agent-browser` | `https://github.com/mattpocock/agent-browser` | `ea17db856473e2b1f89f35b485ad1cb250678a6b` | Apache-2.0 | LICENSE sha256:014bb31e83d5c2e76aea1cc6e82217346ab41362f32cb355ad0f5c10aa0aeaff | Study browser automation APIs designed for coding agents. |
| `mattpocock-node-DeepResearch` | `https://github.com/mattpocock/node-DeepResearch` | `69f345ef8ef28f725aaa778177f6be181801411e` | Apache-2.0; local license copyright Jina AI | LICENSE sha256:4e0e989fafce6b20008458b60c238699994547ab5dd9cba6c4d0bf5472a2fd25 | Study bounded research, search, read, and synthesis loops. |
| `snarktank-ralph` | `https://github.com/snarktank/ralph` | `6c53cb0b831ebe8739c6a003e22af14902d8b0b5` | MIT | LICENSE sha256:102b6470e861e782d90a42d9086f48b8a2f38cbc4c0229216bcf0364f79ea5a3 | Study fresh-context autonomous coding loops, PRD-to-story execution, progress logs, checks, and stop conditions. |

Refresh a source with a shallow fetch only after recording why the newer revision matters.

## Reproducing Ignored Clones

Use the table above as the canonical inventory. To recreate an ignored clone:

```sh
git clone --filter=blob:none <upstream-url> sources/<directory>
cd sources/<directory>
git fetch --depth=1 origin <local-commit>
git checkout --detach <local-commit>
```

If a host does not support fetching the exact commit by SHA with `--depth=1`, fetch the default
branch shallowly, then deepen only as needed to reach the pinned commit. Record any intentional
source refresh in this README before citing the refreshed code in tracked insights, plans, skills,
or source-of-truth documents. Treat ignored clones as inspection caches; durable evidence should be
the pinned upstream commit, tracked inventory row, permalink, tracked excerpt, or tracked synthesis
artifact.

## Use Rules

- Study architecture, tests, interfaces, and workflows.
- Respect licenses.
- Treat license-unclear repos as reference-only until reviewed.
- Do not copy source code into this project without a decision record.
