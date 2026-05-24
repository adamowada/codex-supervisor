# Codex Supervisor

`codex-supervisor` is a Python-first control plane for building an agentic coding factory around
Codex.

The goal is simple and ambitious: after I supply the required product, architecture,
acceptance, risk, and operating assumptions, Codex should be able to coordinate fresh-context Codex
workers until the plan is implemented, reviewed, tested, documented, and ready for a human decision.
Today, this repository implements the planning, Goal Contract, Story Loop, verification, source-lock,
skill, and handoff layers for that workflow. Automatic Codex Exec worker launch remains a planned
Stage 6 backend, not a current capability.

This repository is the source of truth for that workflow. It combines patterns from my busiest
projects:

- `nlp-stock-prediction`: tracked SQLite planning state with typed access.
- `codex-subagent-testing`: locked top-level source-of-truth documents protected by SHA-256 hashes.
- `tech-resume`: an `insights/` markdown knowledge graph with provenance and confidence labels.
- `observe-safety-monorepo`: structured, test-enforced planning and production-grade gates.

The local workspace may also include shallow source clones under `sources/` for study and
integration experiments. Those clones are intentionally ignored by git and are reproducible from
the pinned clone inventory in `sources/README.md`; `ATTRIBUTIONS.md` records reuse rules and copied
or adapted material.

## Dream Workflow

For any new project:

1. Run an extensive planning session to lock assumptions, contracts, non-goals, risks, and acceptance
   criteria.
2. Persist the plan into a tracked SQLite planning database.
3. Compile the plan into small vertical-slice tasks marked `AFK` or `HITL`.
4. Launch fresh-context Codex workers in isolated worktrees.
5. Give each worker a Goal Contract with objective, boundaries, verification, and stop conditions.
6. Execute one vertical slice per story-loop iteration.
7. Require every worker to return structured output.
8. Run automated checks and automated review before merge.
9. Record decisions, progress, artifacts, commits, failures, and follow-up tasks.
10. Update skills and the knowledge graph when repeated patterns or failures reveal something durable.

## Intended Operating Mode

This system is designed for trusted local or controlled-runner automation using dangerous/full-auto
Codex execution. The safety boundary is not permission prompts. The safety boundary is:

- disposable worktrees;
- explicit task scope;
- structured outputs;
- deterministic tests and checks;
- automated review;
- source-of-truth document locks;
- durable planning state;
- auditable logs and artifacts.

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

## Bootstrap And Source-Of-Truth Documents

- `README.md`: human-facing purpose, goals, and operating vision.
- `AGENTS.md`: instructions for Codex and other coding agents in this repo.
- `PLANS.md`: planning database contract and required planning workflow.
- `ARCHITECTURE.md`: supervisor architecture and backend boundaries.
- `CONTRACTS.md`: durable runtime contracts for tasks, workers, adapters, and results.
- `ROADMAP.md`: staged implementation plan for future Codex sessions.
- `SOP.md`: standard operating procedure for projects spawned by the supervisor.
- `TESTING.md`: testing and verification strategy.
- `DECISIONS.md`: baseline decisions; ongoing decisions belong in SQLite first.
- `HANDOFF.md`: mutable starting point for the next Codex session, not a locked stable
  source-of-truth document; planning SQLite remains canonical for current tasks.
- `LICENSE`: MIT license for this repository.
- `ATTRIBUTIONS.md`: reuse rules and attribution notes for copied or adapted material.
- `.gitignore` / `.gitattributes`: public hygiene, generated-file, line-ending, and binary-file
  guardrails.

Stable top-level source-of-truth documents, excluding the mutable `HANDOFF.md`, are locked by
`scripts/check_protected_files.py`.

## Fresh Thread Bootstrap

Use the repo-local `codex-supervisor` skill first. If the skill is not available in the fresh
thread, read `.agents/skills/codex-supervisor/SKILL.md` directly and follow its bootstrap contract
before interpreting queue state.

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
task-relevant source-of-truth docs after the live queue is known, instead of front-loading every
historical audit or insight file. Read `HANDOFF.md` only after the live queue has been inspected;
it is a mutable snapshot, not the queue authority.
Inspect the live queue before interpreting `task-current` or running broad checks:

```sh
uv run --no-sync python -B -m codex_supervisor.cli story-loop-status --json
uv run --no-sync python -B -m codex_supervisor.cli task-current --json
uv run --no-sync python -B -m codex_supervisor.cli task-list --current-queue-plans-only
uv run --no-sync python -B -m codex_supervisor.cli plan-summary --current-queue
uv run --no-sync python -B -m codex_supervisor.cli plan-list
```

`uv run` can create or update local dependency/cache state if the environment is missing. In a
strict read-only audit where dependencies are not already synced, do not run setup or `uv run`; use
existing command output, Git state, or read-only SQLite inspection and report that dependency setup is
required for typed CLI orientation.

Strict read-only SQLite fallback:

```sh
python -B -c "import json, sqlite3; c=sqlite3.connect('file:plans/planning.sqlite3?mode=ro', uri=True); c.row_factory=sqlite3.Row; rows=c.execute(\"\"\"SELECT p.plan_id,p.status AS plan_status,p.priority,st.task_id,st.title,st.status AS task_status,st.task_type,st.worker_backend,st.blocked_by_json FROM supervisor_tasks st JOIN plans p ON p.plan_id=st.plan_id WHERE p.status IN ('active','blocked') ORDER BY p.status='active' DESC,p.priority DESC,st.status='ready' DESC,st.updated_at DESC,st.task_id\"\"\").fetchall(); print(json.dumps([dict(r) for r in rows], indent=2)); c.close()"
```

`plan-list`, `plan-summary`, `story-loop-status`, `task-current`, `task-show`, and `task-list`
inspect existing planning state without initializing or mutating the database. `story-loop-status`
reports ready, running, HITL, blocked, completed, and empty queue states across active and blocked
current-queue plans by default; `--all` adds completed, abandoned, and superseded history.
`task-current` selects only executable AFK work. Inspect `story-loop-status --json` first, then
inspect the reported current task ID with `task-show ... --json` when one is present. If
`task-current --json` returns `null`, do not conclude there is no task until the JSON status reports
`completed` or `empty`.

Run task-relevant verification after orientation. Check `HANDOFF.md` for the expected verification
state before interpreting broad gate failures. During an ACP/HITL checkpoint, run the component
checks named in `HANDOFF.md` first if the broad gate is expected to fail. The broad default gate is:

```sh
uv run python -B scripts/verify.py
```

Run the source lock guard after intentional source-of-truth edits or before publication:

```sh
uv run python -B scripts/check_protected_files.py
```

During an active ACP/HITL checkpoint, the lock guard may fail until new protected files are tracked
and hashes are intentionally refreshed.

Initialize or migrate the tracked planning database only when intended:

```sh
uv run codex-supervisor plan-init --seed-bootstrap-plan
```

`.python-version` targets the Python 3.14 line because this repo intentionally tracks the latest
Python line from day one. Use `uv python install 3.14` to install the newest uv-managed 3.14 patch
available for your platform, or install an exact system Python patch release outside uv when uv does
not publish that patch for your platform. Run `uv run python --version` before verification and
confirm it reports Python 3.14.x.

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

Stage 6 worker metadata should record the Goal Mode preflight evidence explicitly: resolved Codex
executable, `codex --version` output, intended `CODEX_HOME`, config path and feature state, whether
the selected worker backend has an official noninteractive native-goal path, and the fallback
decision when the contract is rendered into the prompt instead.

## OSS Inspiration Sources

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
