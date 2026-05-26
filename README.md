# Codex Supervisor

`codex-supervisor` is the Python-first control plane for an agentic engineering factory around
Codex.

It exists so a human can supply goals, constraints, taste, acceptance criteria, and risk tolerance
once, then let Codex coordinate fresh-context workers until a production-quality result is specified,
built, reviewed, tested, documented, and ready for a human decision.

This README is the locked end-state product brief for the repository. It describes the target shape
of the system, not the live task queue. Live operational progress, worker completion records, and
imported legacy evidence live in `plans/planning.sqlite3`; `HANDOFF.md` is only the current
human-readable resume snapshot.

## Product Shape

`codex-supervisor` is a combination of:

- a Python package, `codex_supervisor`, that owns planning, task contracts, worker orchestration,
  source locks, project adapters, result records, and learning loops;
- a CLI, `codex-supervisor`, for humans, scripts, CI jobs, and recurring automation;
- a Codex Exec harness for launching fresh-context Codex workers in isolated worktrees with
  structured output contracts;
- an MCP server that exposes supervisor capabilities to Codex Desktop and other agent harnesses
  without making MCP the state owner;
- a Codex plugin and repo-local skills that make the workflow ergonomic inside Codex Desktop;
- a project scaffold that gives new production-intended projects the same source-of-truth,
  planning, verification, review, and handoff discipline from day one.

The product is not a replacement for Codex. It is the orchestration layer that gives Codex durable
state, vertical-slice task boundaries, repeatable review loops, context reset discipline, and a way
to learn from repeated work.

## Agentic Factory Loop

For any new project:

1. Run an extensive planning session to lock goals, non-goals, assumptions, contracts, risks,
   acceptance criteria, and verification commands.
2. Persist the plan into tracked SQLite state.
3. Compile the plan into small vertical-slice tasks marked `AFK` or `HITL`.
4. Render a Goal Contract for each executable AFK slice.
5. Launch fresh-context Codex workers in disposable worktrees.
6. Execute exactly one vertical slice per story-loop iteration.
7. Require every worker to return structured evidence.
8. Run deterministic checks and automated review before accepting the result.
9. Repair issues through focused follow-up tasks or record a blocked/HITL decision.
10. Link commits, supporting artifacts, reviews, decisions, progress events, and handoff notes in
    planning SQLite.
11. Promote repeated lessons into `insights/` and repo-local skills.

The factory favors:

- small skill over giant methodology;
- domain glossary over repeated explanation;
- vertical slice over horizontal layer task;
- AFK-ready issue over vague plan item;
- compact handoff over bloated session;
- sandbox/worktree over risky direct edits;
- eval loop over "seems better."

## State Authority

Stable doctrine lives in protected source-of-truth documents:

- `README.md`
- `AGENTS.md`
- `PLANS.md`
- `ARCHITECTURE.md`
- `CONTRACTS.md`
- `ROADMAP.md`
- `SOP.md`
- `TESTING.md`
- `DECISIONS.md`
- `LICENSE`
- `ATTRIBUTIONS.md`
- `.gitignore`
- `.gitattributes`

Operational progress lives in:

- `plans/planning.sqlite3` for plans, tasks, worker runs, DB-backed worker result records,
  development-log entries, progress events, decisions, supporting artifacts, verification evidence,
  imported legacy records, and queue state;
- `HANDOFF.md` for the compact mutable human-readable resume point only.

Protected documents are contracts, not progress ledgers. Edit them only when doctrine changes, then
refresh the source-lock hashes intentionally.

## Operating Mode

The intended runtime posture is trusted local or controlled-runner full-auto Codex operation. The
safety boundary is not frequent permission prompts. The safety boundary is:

- isolated worktrees;
- explicit task contracts;
- narrow allowed paths;
- structured worker outputs;
- deterministic verification;
- automated review;
- source-of-truth locks;
- durable planning state;
- auditable database records, local run evidence, and compact handoffs.

## Repository Map

```text
src/codex_supervisor/      Python supervisor package
tests/                     Regression tests for planning, locks, Goal Contracts, Story Loop,
                           hygiene, inventory, and verification behavior
scripts/                   Repo maintenance and verification scripts
plans/planning.sqlite3     Tracked operational planning database
insights/                  Markdown knowledge graph and learning memory
.agents/skills/            Repo-specific Codex skills
sources/                   Ignored shallow clones of OSS inspiration sources
```

## Source-Of-Truth Documents

- `README.md`: human-facing product brief and factory goal.
- `AGENTS.md`: operating instructions for Codex and coding agents in this repo.
- `PLANS.md`: planning database contract and required planning workflow.
- `ARCHITECTURE.md`: system architecture, state ownership, and interface boundaries.
- `CONTRACTS.md`: durable runtime contracts for tasks, workers, adapters, reviews, and results.
- `ROADMAP.md`: stable master build plan for new Codex sessions.
- `SOP.md`: standard operating procedure for projects spawned by the supervisor.
- `TESTING.md`: verification strategy and required test surfaces.
- `DECISIONS.md`: stable architectural and workflow decisions.
- `HANDOFF.md`: compact mutable resume snapshot for the next Codex session.
- `LICENSE`: MIT license for this repository.
- `ATTRIBUTIONS.md`: reuse rules and attribution notes for copied or adapted material.
- `.gitignore` and `.gitattributes`: public hygiene, generated-file, line-ending, and binary-file
  guardrails.

## Fresh Thread Bootstrap

Use the repo-local `codex-supervisor` skill first. If the skill is unavailable in a fresh thread,
read `.agents/skills/codex-supervisor/SKILL.md` directly and follow its bootstrap contract before
interpreting queue state.

```sh
git status --short --branch
git rev-parse --short HEAD
```

If dependency setup and writes are allowed, also run:

```sh
uv python install 3.14
uv sync --dev
uv run python --version
```

Then read `AGENTS.md`, `PLANS.md`, and `insights/README.md`. Use those stable files to find
task-relevant source-of-truth docs after the live queue is known. Read `HANDOFF.md` only after the
live queue has been inspected; it is a mutable snapshot, not the queue authority.

Inspect the live queue before interpreting `task-current` or running broad checks:

```sh
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B -m codex_supervisor.cli task-current --after-story-loop-status --json
uv run --no-sync python -B -m codex_supervisor.cli task-list --current-queue-plans-only
uv run --no-sync python -B -m codex_supervisor.cli plan-summary --current-queue
uv run --no-sync python -B -m codex_supervisor.cli plan-list
```

`uv run` can create or update local dependency/cache state if the environment is missing. In a
strict read-only audit where dependencies are not already synced, use existing command output, Git
state, or read-only SQLite inspection and report that dependency setup is required for typed CLI
orientation.

Strict read-only SQLite fallback:

```sh
python -B -c "import json, sqlite3; c=sqlite3.connect('file:plans/planning.sqlite3?mode=ro', uri=True); c.row_factory=sqlite3.Row; rows=c.execute(\"\"\"SELECT p.plan_id,p.status AS plan_status,p.priority,st.task_id,st.title,st.status AS task_status,st.task_type,st.worker_backend,st.blocked_by_json FROM supervisor_tasks st JOIN plans p ON p.plan_id=st.plan_id WHERE p.status IN ('active','blocked') ORDER BY p.status='active' DESC,p.priority DESC,st.status='ready' DESC,st.updated_at DESC,st.task_id\"\"\").fetchall(); print(json.dumps([dict(r) for r in rows], indent=2)); c.close()"
```

Run task-relevant verification after orientation. The broad default gate is:

```sh
uv run python -B scripts/verify.py
```

Run the source lock guard after intentional source-of-truth edits or before publication:

```sh
uv run python -B scripts/check_protected_files.py
```

Initialize or migrate the tracked planning database only when intended:

```sh
uv run codex-supervisor plan-init --seed-bootstrap-plan
```

`.python-version` targets the Python 3.14 line. Use `uv python install 3.14` to install the newest
uv-managed 3.14 patch available for your platform, or install an exact system Python patch release
outside uv when uv does not publish that patch for your platform. Run `uv run python --version`
before verification and confirm it reports Python 3.14.x.

## Codex Goal Prerequisite

Goal Contracts can be carried into native Codex Goals when the local Codex install supports `/goal`.
Official OpenAI guidance, indexed in `insights/source-index.md`, says Goals require a Goals-capable
Codex build and documents lifecycle commands such as `/goal`, `/goal pause`, `/goal resume`, and
`/goal clear`. Before relying on native Goals, run `codex --version` and update Codex if needed.
For fresh-context workers, launch Codex with the intended `CODEX_HOME` and verify Goals are enabled:

```toml
[features]
goals = true
```

If `/goal` is not visible on a Goals-capable build, official OpenAI guidance says to enable
`features.goals` in `${CODEX_HOME}/config.toml` or run `codex features enable goals`. Restart or
start a fresh Codex session only if the running process does not pick up the config change. Treat
the config edit and `codex features enable goals` as setup mutations: run them only when Goal Mode
setup is explicitly in scope. In read-only, review-only, or already-synced worker contexts, render
the Goal Contract into the worker prompt and continue without writing to Codex internal goal
databases.

On Windows, `codex --version` can fail when the executable resolved through `WindowsApps` is not
directly callable from the current shell. Treat that as a Goal Mode preflight failure, not as a
reason to write local Codex databases directly. Use prompt-rendered Goal Contracts until the Codex
CLI path and `CODEX_HOME` are confirmed.

Worker metadata records the Goal Mode preflight evidence explicitly: resolved Codex executable,
`codex --version` output, intended `CODEX_HOME`, config path and feature state, whether the selected
worker backend has an official noninteractive native-goal path, and the fallback decision when the
contract is rendered into the prompt instead.

## Inspiration Sources

The ignored `sources/` directory may contain local shallow clones of:

- `openai/codex`
- `HarnessLab/claw-code-agent`
- `openclaw/openclaw`
- `mattpocock/skills`
- `mattpocock/sandcastle`
- `mattpocock/evalite`
- `mattpocock/agent-rules-books`
- `mattpocock/agent-browser`
- `mattpocock/node-DeepResearch`
- `snarktank/ralph`

The authoritative clone inventory lives in `sources/README.md`. `ATTRIBUTIONS.md` records reuse
rules and copied or adapted material.
