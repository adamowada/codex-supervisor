# Workflow Patterns

## Fresh Context Over Long Context

Confidence: confirmed from private local telemetry and cross-project source review; public evidence
is redacted aggregate method.

Long Codex sessions eventually degrade. The supervisor should turn durable state into task prompts
and launch fresh workers instead of pushing one conversation indefinitely.

## Vertical Slices Over Horizontal Layers

Confidence: confirmed.

Matt Pocock's `to-issues` and `tdd` skills both push toward thin end-to-end slices. The supervisor
should compile plans into independently verifiable vertical tasks, not "build all models, then all
APIs, then all UI."

## Source Locks For Stable Doctrine

Confidence: confirmed.

`codex-subagent-testing` uses SHA-256 protected files to prevent casual drift in top-level source of
truth. `codex-supervisor` adopts that pattern for stable docs.

## SQLite For Operational Planning

Confidence: confirmed.

`nlp-stock-prediction` shows that tracked SQLite planning state gives Codex a queryable, durable
coordination substrate while leaving human-facing doctrine in markdown.

## Insights As Durable Learning Memory

Confidence: inferred.

`tech-resume` demonstrates a useful markdown insight wiki. `codex-supervisor` extends the pattern to
workflow learning and skill evolution.

## Goal Contracts Over Open-Ended Execution

Confidence: confirmed.

Codex Goals make long-running work safer when the objective, validation surface, constraints,
boundaries, and stop condition are explicit. `codex-supervisor` should derive Goal Contracts from
planning SQLite tasks and source-of-truth docs, then treat native Codex Goal state as execution
telemetry rather than project authority.

## One Story Per Fresh Context

Confidence: inferred.

Ralph demonstrates that autonomous coding loops become easier to control when each iteration starts
with fresh context, selects one incomplete story, runs checks, records progress, and stops or moves
to the next story. `codex-supervisor` should apply this as Story Loop policy over `AFK` supervisor
tasks.

## Current Queue Over Active Only

Confidence: confirmed.

Fresh threads need to see blocked successor plans as part of the current queue. Use
`story-loop-status --json`, `plan-summary --current-queue`, and
`task-list --current-queue-plans-only` for orientation; reserve active-only views for deliberately
narrow audits.

## PowerShell Native JSON Arguments

Confidence: confirmed.

When PowerShell passes JSON strings to native executables, quote characters can be stripped before
the target process receives `argv`. For JSON-heavy CLI arguments, double embedded quotes after
`ConvertTo-Json -Compress` and validate with a tiny `python -c` `repr(sys.argv[1])` probe before
running the mutating command. Prefer stdin, a temp file, or inline Python when the argument becomes
too complex.

Evidence: Stage 11A planning-shape commands failed until the JSON argument was transformed with
`$jsonArg = ($json -replace '"','""')`; the pattern is codified in
`.agents/skills/windows-shell-quoting/SKILL.md`.

Next action: use `windows-shell-quoting` whenever PowerShell commands contain JSON arguments,
nested quotes, regexes, or inline Python.

## External Skill Validators Need Dependency Envelopes

Confidence: confirmed.

System or plugin-provided validator scripts may depend on packages that are not part of the current
repository's development environment. When a validator is useful but not part of the repo's safe
verification command vocabulary, run it as an extra preflight with an isolated dependency envelope,
for example `uv run --with pyyaml --no-project python -B <validator> <target>`, then keep the
official planning `tests_run` evidence to repo-owned, integrity-approved commands.

Evidence: Stage 12A plugin validation failed under `uv run --no-sync python -B` because the
plugin-creator validator imports `yaml`; rerunning with `uv run --with pyyaml --no-project` passed
without adding PyYAML to `codex-supervisor`.

Next action: prefer repo-owned tests for durable verification and use external validators as
diagnostic or contract-confirming checks unless the dependency is intentionally adopted.

## File Purpose Verifiers Use Gate Names

Confidence: confirmed.

`scripts/check_file_justification.py` validates file-purpose verifier labels against a small
allow-list, so new public files should cite durable gate families such as `pytest` rather than a
specific test file path unless that verifier is explicitly allowed.

Evidence: Stage 12A initially registered plugin files with `tests/test_codex_plugin.py` as the
verifier and the file-purpose gate rejected all three entries. Switching those entries to `pytest`
kept the focused test coverage while preserving the allow-list contract.

Next action: when adding public files, update both purpose rules and file-level purposes, then run
`uv run --no-sync python -B scripts/check_file_justification.py` before broader verification.

## Hygiene Tests Should Not Publish Forbidden Tokens

Confidence: confirmed.

Tests that assert public-hygiene behavior can accidentally trip the same hygiene patterns they are
defending against. Build forbidden local-path tokens from smaller string pieces when the test needs
to assert absence, so the repository source does not contain the sensitive-looking pattern itself.

Evidence: Stage 12A's plugin test initially asserted that plugin files did not contain a macOS user
path literal. `scripts/check_public_repo_hygiene.py` correctly rejected the test source. Rewriting
the assertion to construct the token from pieces preserved coverage and passed the hygiene gate.

Next action: whenever public hygiene detects a test fixture string, prefer token construction or a
redacted fixture over widening the hygiene allow-list.

## Worker Result JSON Must Stay Integrity-Safe

Confidence: confirmed.

`worker-run-status ... --result-path <json>` validates worker result JSON more strictly than review
artifacts. Completed worker results need `acceptance_results` as an object keyed by the exact task
acceptance criteria text, `tests_run` commands must be the exact repo-owned verification commands
without placeholder angle brackets or shell metacharacters, and `artifacts` entries must be existing
repo-relative paths rather than Markdown anchors.

Evidence: Stage 12B completion initially failed ingestion and planning integrity because the
transient worker result used a list for `acceptance_results`, included `<plugin-creator>` and
`<skill-creator>` placeholder commands, and listed `HANDOFF.md#...` anchors as artifacts. Stage 13A
then failed planning integrity after the raw JSON file was removed but the empty `worker-results/`
directory remained. Correcting the transient JSON and removing the `worker-results/` directory
itself after ingestion restored planning integrity.

Next action: before ingesting completed worker results, prefer only the task's official verification
commands in `tests_run`, keep external validators in review notes or handoff summaries, and delete
the ignored `worker-results/` import directory itself, not just the JSON file, immediately after the
DB row is created.

## New Verification Scripts Need Command-Safety Promotion

Confidence: confirmed.

Planning SQLite validates task verification commands against an approved read-only command shape.
Brand-new `scripts/*.py` files are not automatically safe as canonical task commands, even when the
script is read-only and useful. Until the script is intentionally added to the command-safety
allow-list, use focused pytest or existing approved checks as the task verification command and run
the new script as extra review or handoff evidence.

Evidence: Stage 12C shaping first tried to use
`uv run --no-sync python -B scripts/verify_codex_plugin_install.py` as a criterion verifier, and
planning rejected it because Python verification is limited to approved scripts or modules. The task
was shaped with focused plugin tests and full verify as canonical commands, while the new smoke
verifier still ran directly as extra evidence.

Next action: when shaping tasks that introduce new verifier scripts, either include command-safety
promotion and tests in scope or keep the canonical task commands on already-approved verification
surfaces.

## CI Publication Gates Should Verify Staged Blobs

Confidence: confirmed.

GitHub Actions workflows that run the repository's publication-ready gate should keep dependency
setup deterministic and avoid tracked-file mutation before the hygiene check. Use `uv sync --dev
--locked` in CI, then run `uv run python -B scripts/verify.py --publication-ready` so lock drift or
unexpected public files fail visibly instead of being normalized by the workflow.

Evidence: Stage 13A added the first GitHub Actions workflow and validated it locally by staging the
workflow, file-purpose map, and workflow contract tests before running
`uv run --no-sync python -B scripts/verify.py --publication-ready`. The gate passed against the
indexed blobs, matching the CI posture the workflow will use after publication.

Next action: for future CI or release workflow slices, run publication-ready verification only after
the intended public files are staged, and prefer locked dependency setup inside CI workflows.

## CI Planning Integrity Needs Reachable Commit Links

Confidence: confirmed.

Planning integrity checks that validate DB commit links depend on the local git object database. A
CI checkout with `fetch-depth: 1` can pass tests, lint, typecheck, and public hygiene, then fail
planning integrity because historical commits linked from `plans/planning.sqlite3` are not present.
For publication-ready CI, fetch enough history for commit-link validation instead of deleting
historical links or weakening the integrity rule.

Evidence: The Stage 13B post-repair GitHub Actions `Verify` run passed all 441 tests on Linux plus
ruff, formatting, mypy, CLI help, file-purpose, and public hygiene. It then failed
`scripts/check_planning_integrity.py` with missing historical commit links because the workflow used
the default shallow checkout. Stage 13C repaired the workflow with `fetch-depth: 0`, and GitHub
Actions run `26400531911` completed successfully for commit
`9e311ae99061bd8978a03d55d22ef0cbf9be4dda`.

Next action: when CI planning integrity reports missing git commits, inspect checkout depth before
changing planning data or integrity semantics.

## Pinned GitHub Actions Need Commit Objects

Confidence: confirmed.

GitHub Actions `uses:` pins should reference commit objects, not annotated tag objects. A 40-hex
tag object can look like a supply-chain-safe SHA but still fail during action archive download on
GitHub runners; resolve reviewed release tags to their peeled commit SHA before pinning.

Evidence: The Verify workflow pinned `astral-sh/setup-uv` to `e58605a...`, the `v5` tag object.
GitHub Actions failed in job setup while downloading
`https://codeload.github.com/astral-sh/setup-uv/tar.gz/e58605a...`. `git ls-remote` showed the
peeled `v5^{}` commit is `d4b2f3b...`, which is now the workflow pin.

Next action: when updating action pins, record the reviewed tag and peeled commit, and keep workflow
tests from accepting known tag-object pins.

## External CI Evidence Stays Out Of Artifact Links

Confidence: confirmed.

Planning artifact links are publication artifacts, not arbitrary evidence identifiers. External CI
run URLs should be stored in typed progress details and paired with a reachable commit link. Only add
an artifact link when the artifact ID resolves to a repo-local tracked file or a safe anchor on one;
otherwise publication-ready hygiene will correctly reject the planning state.

Evidence: Stage 13D first recorded GitHub Actions run `26400531911` as a synthetic
`ci-runs/github-actions/26400531911` artifact link. `scripts/verify.py --publication-ready` failed
because that path did not exist on disk. The repair made `ci-run-record` default to progress details
plus a `ci-head` commit link, with `--artifact-id` remaining optional for real repo-local evidence.

Next action: when adding new planning evidence helpers for external systems, keep URLs and remote IDs
in structured progress details unless the helper also creates or references a real tracked artifact.

## Evidence Upserts Must Remove Stale Derived Links

Confidence: confirmed.

Typed planning evidence helpers often create derived links in addition to the primary progress row:
commit links, artifact links, or review links. When the progress row is intentionally re-recorded
with changed external evidence, the helper must remove obsolete derived links that are no longer
referenced by current evidence. Otherwise planning SQLite keeps plausible-looking stale links that
can mislead later queue inspection and review.

Evidence: Stage 13E's review found that PR and issue-comment evidence upserts inserted new
`plan_commit_links` rows but did not remove the previous `pr-head` or `issue-comment-commit` link
when a PR head SHA changed or a comment was re-recorded without a commit SHA. Regression tests now
cover both replacement and removal.

Next action: when adding or reviewing evidence helpers, test both first-record and re-record paths,
including removal of optional artifact or commit evidence.

## Optional Scaffold Tiers Need Separate Triggers

Confidence: confirmed.

Spawned-project scaffolds should not bundle optional surfaces together just because they often travel
as a family. Durable learning, repo-local skills, and source-study evidence have different costs and
should be recommended by separate brief signals. This keeps small projects and learning-only
projects from receiving empty skill directories, source inventories, or attribution surfaces that
they have not earned.

Evidence: Stage 14A review found that `durable_learning=True` initially selected the combined
skills/source-study surface, including `.agents/skills/` and `sources/README.md`. The repair split
durable-learning insight files from repo-local skill files and source-study files, with regression
coverage proving that durable learning alone does not create empty optional skill/source surfaces.

Next action: when adding scaffold classifiers or bootstrap templates, test each optional tier both
alone and in combination with adjacent tiers.

## Cross-Platform Adapters Normalize Before Resolving

Confidence: confirmed.

Project adapters that ingest repo-relative paths from JSON, markdown tables, or imported planning
records should normalize Windows-style separators before resolving against a `Path` root. On POSIX,
`root / "prompts\\browser-smoke.md"` treats the backslash as a literal filename character; normalizing
through `PureWindowsPath(value).as_posix()` first preserves intended relative paths while still
allowing explicit drive, absolute, and parent-traversal rejection.

Evidence: The first Stage 13 GitHub Actions `Verify` run passed setup but failed two
`tests/test_projects.py` cases on Linux: harness `prompt_path` normalization and insights graph
`allowed_paths` normalization. The same tests passed locally on Windows, so CI surfaced a real
cross-platform adapter contract gap.

Next action: when adapters accept human-authored paths, test both POSIX-style and Windows-style
relative separators, plus `..\\` traversal rejection, before relying on local Windows-only results.

## CLI Branch Locals Need Specific Names

Confidence: confirmed.

Large argparse dispatch functions still share one Python function scope across all command
branches. Reusing a broad local name like `proposal` for different dataclass result types can pass
tests and lint, then fail mypy once a new branch introduces a second incompatible assignment. Name
branch-local values by domain, such as `skill_proposal` or `spawned_project_proposal`, when the
dispatch function handles multiple typed command families.

Evidence: Stage 14B added `spawned-project-propose` and initially reused `proposal` in the same
`main()` scope where skill-promotion validation also used `proposal`. Full verification passed
tests, Ruff, and formatting but mypy rejected the later skill-promotion branch until the local was
renamed to `skill_proposal`.

Next action: when adding CLI subcommands to `src/codex_supervisor/cli.py`, run mypy before review
and avoid generic local result names in command branches that return different typed records.

## Gap Reports Must Name Missing Evidence

Confidence: confirmed.

Release, hygiene, and readiness reports should never pair `gap` status with optimistic evidence
phrases. Each check should identify the present evidence and the missing evidence explicitly so the
next action is traceable from the report without re-running a debugger or reading the implementation.

Evidence: Stage 15A review found that the first release-readiness audit correctly marked an empty
repo dry-run as gaps, but text-contract checks still emitted positive evidence strings for missing
CLI, documentation, and CI contracts. The repair changed those checks to emit `present:` and
`missing:` evidence and added regression coverage for missing text contracts.

Next action: when adding evidence reports, test an empty or deliberately incomplete fixture and
assert that every gap exposes the missing proof, not only the intended proof.

## JSON Import Artifacts Need UTF-8 Without BOM

Confidence: confirmed.

Planning import commands parse JSON as strict UTF-8. On Windows PowerShell, `Set-Content
-Encoding UTF8` can write a UTF-8 BOM that Python's default `json.loads` path rejects. For transient
review or worker-result payloads, write UTF-8 without BOM or use repo-owned JSON helpers before
ingesting.

Evidence: Stage 15A review-result ingestion first failed with `Unexpected UTF-8 BOM` after
PowerShell wrote the transient review JSON. Rewriting the file with
`[System.Text.UTF8Encoding]::new($false)` allowed `review-result-ingest` to accept and persist the
same structured payload.

Next action: when creating temporary JSON for planning CLI ingestion on Windows, use a no-BOM writer
and rerun the ingest command before recording progress.

## Planning Writer Helpers Must Opt Out Of Read-Only

Confidence: confirmed.

`open_existing_planning_database(...)` defaults to a read-only store. Inline typed-helper scripts are
still the right escape hatch when CLI JSON quoting would be fragile, but writer scripts must pass
`read_only=False` explicitly before calling upsert or progress methods.

Evidence: Stage 15B shaping first used the typed planning store without `read_only=False` and SQLite
rejected the milestone write as an attempt to write a read-only database. Re-running the same typed
helper script with `open_existing_planning_database(default_planning_database_path(),
read_only=False)` created the milestone, criteria, task, and shaping progress correctly.

Next action: when using inline Python for planning mutations, import `default_planning_database_path`
and open the store with `read_only=False`; reserve the default for orientation and audits.

## Retained Smoke Artifacts Need Explicit Destinations

Confidence: confirmed.

Dry-run smoke commands that clean up by default may offer an inspection mode, but retained artifacts
must be written to an operator-chosen path. If `--keep-workspace` silently creates a random temp
directory, the smoke run is no longer auditable from its own output and can leave hidden runtime
state behind.

Evidence: Stage 15C review found that `factory-loop-smoke --keep-workspace` without `--workspace`
would retain an anonymous temp directory. The repair made retained workspaces require an explicit
workspace path and added API plus CLI regression coverage.

Next action: when adding dry-run or smoke CLIs with retention flags, require an explicit destination
or include a deterministic, inspectable artifact path in the command output.

## Supervisor Plugins Must Fail Closed When Backend Tools Are Missing

Confidence: confirmed.

Claim: A Codex Desktop skill being available is not proof that its backing MCP server, CLI fallback,
planning database, or worker backend is available. For `codex-supervisor`, skill-only mode must not
silently degrade into ordinary current-thread implementation, especially when the user asked for
AFK or full-auto supervision.

Evidence: A 2026-05-26 Desktop smoke in a fresh todo-list folder loaded the cached
`codex-supervisor` skill, but the thread exposed no supervisor MCP tools, `uv` was unavailable in
the effective shell, and the output project contained a working app without `.agents/`,
`plans/planning.sqlite3`, `HANDOFF.md`, git state, task claims, or worker-result evidence. The
plugin skill currently says to use MCP "when available" and the CLI as fallback, while the plugin
MCP command in `plugins/codex-supervisor/.mcp.json` relies on ambient `uv` and a relative `cwd`.

Scope: Codex Desktop plugins, supervisor bootstrap, full-AFK requests, and any workflow where
auditability depends on repo-owned planning state rather than chat memory.

Next action: add a supervisor runtime preflight and hard-stop rule: if MCP tools and CLI fallback
are unavailable, record a blocker or ask for setup/repair instead of starting implementation.

## Installed Plugin Cache Layout Is A Release Surface

Confidence: confirmed.

Claim: Plugin verification must exercise the installed Desktop cache layout, not only the source
plugin directory. Relative MCP `cwd` values that work from `plugins/<name>/` can point at the wrong
directory after Desktop copies the plugin into `$CODEX_HOME/plugins/cache/...`.

Evidence: The same smoke exposed a mismatch between source verification and real Desktop startup:
the source plugin's `../..` resolves to the repository root, while the cached plugin's `../..`
resolves inside the plugin cache and lacks `pyproject.toml`, `src/codex_supervisor`, and
`plans/planning.sqlite3`. Existing plugin verification checks the source plugin path and fake-runs
the intended `uv` command shape, so it did not catch the cache relocation or broken-PATH startup
failure.

Scope: plugin packaging, clean-profile installs, release readiness, and Desktop smoke tests.

Next action: add an installed-cache verifier that reads the enabled plugin config, resolves the
cached `.mcp.json` exactly as Desktop does, launches `initialize`/`tools/list`, and asserts the
expected supervisor tools are exposed.

## Plugin Cache Refresh Must Be Observable

Confidence: confirmed.

Claim: Source-side plugin fixes are not live Desktop fixes until the installed plugin cache refreshes
to a new version or otherwise proves it is running the updated skill and MCP wiring. A stale cache
can continue to load old prose instructions after the repository commit that fixed them.

Evidence: A second 2026-05-26 todo-list Desktop smoke started after commit
`9e86338938234ac0fed477cfdc31f5b37671bc87`, but the thread still loaded
`$CODEX_HOME/plugins/cache/codex-supervisor-local/codex-supervisor/0.1.0/.../SKILL.md`, whose
mtime predated the source fix and lacked the runtime-preflight full-AFK guardrails. The source skill
had the guardrails; the live Desktop cache did not.

Scope: Codex Desktop plugin releases, local marketplace development, smoke tests, and any skill
fix that must affect live plugin behavior.

Next action: bump the plugin version or run an explicit cache refresh before Desktop smoke tests,
then verify the installed cache skill and MCP tool list, not only the source tree.

## MCP Launchers Need A Diagnostic Fallback

Confidence: confirmed.

Claim: A Desktop MCP server that cannot import its real backend should still expose a minimal
diagnostic surface when its launcher can start. For `codex-supervisor`, the minimum safe surface is
`codex_supervisor.runtime_preflight` returning a blocked report, because that is the canary full-AFK
requests must call before implementation.

Evidence: The second todo-list Desktop smoke had no supervisor MCP tools and no visible in-thread
MCP startup diagnostic. The agent saw only a failed CLI import from the fresh project directory and
continued as ordinary current-thread Codex, leaving no planning database, task claim, worker run, or
Goal Contract. The hidden startup failure changed the run mode without the user seeing a hard
blocker.

Scope: MCP stdio launchers, plugin cache startup, runtime preflight, full-AFK supervisor requests,
and fail-closed Desktop diagnostics.

Next action: route plugin `.mcp.json` through a cache-safe launcher that either delegates to the
real supervisor package or serves a minimal runtime-preflight diagnostic MCP server.

## Desktop Full-AFK Requires Live MCP Authority

Confidence: confirmed.

Claim: When a user invokes `codex-supervisor` from the Codex Desktop plugin in full-AFK mode, the
current Desktop session's live MCP canary is the only authority that can approve the run. CLI
package checks may explain why MCP failed, but they must not authorize plugin full-AFK readiness or
override a successful live MCP canary.

Evidence: The `todo-list-test-3` smoke first called `runtime_preflight` with Desktop-callable names
such as `codex_supervisor_runtime_preflight`, then reran the live MCP canary with canonical dotted
names such as `codex_supervisor.runtime_preflight` and passed. A later CLI `runtime-preflight`
diagnostic supplied only one `--mcp-tool` value and falsely reported missing tools; that diagnostic
was recorded as a HITL blocker even though MCP had already passed.

Scope: Codex Desktop plugin full-AFK requests, runtime preflight, tool-name normalization, packaged
skill instructions, and smoke-test interpretation.

Next action: normalize Desktop callable tool aliases before comparing required MCP tools, make CLI
preflight diagnostics-only for Desktop plugin full-AFK, and prevent secondary CLI checks from
downgrading a successful live MCP canary.

## Execution Mode Ledgers Should Precede Full-AFK Work

Confidence: confirmed.

Claim: Full-AFK supervisor runs need a visible execution-mode ledger before code work starts. The
ledger should name whether the run is using MCP or CLI, whether planning SQLite exists or was
created, whether execution is a fresh worker or current thread, whether the Goal Contract is native
or prompt-rendered, whether evidence is strict or degraded, and whether target infrastructure such
as Docker or a database is real or a disposable fallback.

Evidence: The todo-list smoke completed useful implementation work while several modes changed
silently: supervisor backend became skill-only prose, native Codex thread Goals stood in for a
supervisor Goal Contract, Docker MongoDB became memory MongoDB, and full-AFK worker execution became
current-thread implementation. Each switch was individually understandable, but together they
changed the meaning of "complete."

Scope: Story Loop launch, spawned-project bootstrap, plugin smoke tests, and project acceptance
summaries.

Next action: make full-AFK start with an explicit ledger and require user approval or a recorded
HITL/blocker for `unavailable`, `current_thread`, `prototype_light`, `memory_database`, or
`degraded_evidence` modes.
