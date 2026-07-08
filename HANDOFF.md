# HANDOFF.md

Last updated: 2026-07-08

This is the current resume snapshot.

## Current State

Branch: `feature/substrate`

Master plan: `SUBSTRATE_PLAN.md`

Current product identity: `codex-supervisor` is the durable evidence substrate for Codex Goal Mode.
Goal Mode owns objective, strategy, sequencing, launch packet content, recovery decisions, and final
completion judgment. Supervisor owns durable state, launch records, worker assignment, evidence,
product provenance, acceptance, auditability, and compact recovery state.

Current model:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Active surface:

- CLI: `plan-init`, `task-create`, `queue-next`, `attempt-transition`, `attempt-run`
- MCP: `codex_supervisor.queue_next`
- Plugin: thin Desktop wrapper around the same source CLI and MCP stdio server
- Repo-local skills: `codex-supervisor`, `improve-codebase-architecture`,
  `reduce-codebase-complexity`

Planning database:

- `meta`
- `plans`
- `tasks`
- `attempts`
- `evidence_bundles`
- `acceptance_decisions`
- `decisions`

`plans/planning.sqlite3` and `HANDOFF.md` must stay current together.

## Substrate Pivot

The source-of-truth docs, repo-local skill, packaged Desktop skill, plugin README, plugin metadata,
package metadata, protected lock manifest, planning ledger, and handoff now align around the
substrate role split:

- Goal Mode thinks, sequences, recovers, and decides completion.
- Supervisor remembers, launches, verifies, records evidence, enforces product provenance, and
  exposes compact recovery state.
- Worker processes remain ephemeral and receive intelligence from Goal Mode launch packets.
- Work categories stay in task intent, launch packets, acceptance criteria, and generic lineage,
  not supervisor job types.

`SUBSTRATE_PLAN.md` is protected as a source-of-truth file for the branch plan. Protected source
locks were refreshed in `scripts/check_protected_files.py` and `src/codex_supervisor/locks.py`.

## Current Verification

Focused checks completed:

```text
AI prose audit over steering Markdown and plugin guidance
No matches for the audited stock phrase set after edits.

uv run --no-sync python -B scripts/check_protected_files.py
Protected source-of-truth files are unchanged.

uv run --no-sync python -B scripts/check_skill_inventory.py
Skill inventory checks passed.

uv run --no-sync python -B scripts/check_planning_integrity.py
Fresh planning integrity checks passed.
```

Full verification completed:

```text
uv run --no-sync python -B scripts/verify.py
146 passed
```

Latest focused verification completed:

```text
uv run --no-sync pytest -q tests/test_work_graph.py tests/test_evidence_codec.py tests/test_evidence_terminal_transition.py tests/test_small_interface.py tests/test_target_workspace.py tests/test_acp_gate_e2e.py tests/test_process_attempt_e2e.py
70 passed

uv run --no-sync ruff check src\codex_supervisor tests
All checks passed!

codex plugin add codex-supervisor@codex-supervisor-local
Installed plugin root: C:\Users\adams\.codex\plugins\cache\codex-supervisor-local\codex-supervisor\0.2.0+codex.20260708043832

uv run --no-sync python -B scripts/verify.py
146 passed
```

Latest projection-layer verification completed:

```text
uv run --no-sync pytest -q tests/test_projections.py tests/test_small_interface.py tests/test_acp_gate_e2e.py
37 passed

uv run --no-sync ruff check src\codex_supervisor tests
All checks passed!

uv run --no-sync python -B scripts/verify.py
148 passed

uv run --no-sync python -B scripts/check_target_workspace_acp.py --workspace . --path plans/planning.sqlite3 --json
failed: .codex-supervisor/planning.sqlite3 is not ignored by git; dirty source-maintenance paths
lack accepted attempt-run worker evidence.

ACP repair completed:

git check-ignore -q -- .codex-supervisor/planning.sqlite3
ignored

uv run --no-sync python -B scripts/check_target_workspace_acp.py --workspace . --path plans/planning.sqlite3 --json
ok true, failures []
```

Latest Patch 1 safety verification completed:

```text
red: focused Patch 1 regressions failed before implementation

uv run --no-sync pytest -q tests/test_codex_plugin.py::test_plugin_cli_launcher_resolves_supervisor_paths_before_source_cwd tests/test_codex_plugin.py::test_installed_cache_cli_launcher_attempt_run_relative_workspace_uses_invocation_cwd tests/test_mcp_queue_next.py::test_mcp_queue_next_rejects_relative_tool_path tests/test_mcp_queue_next.py::test_mcp_queue_next_rejects_relative_context_path tests/test_process_attempt_e2e.py::test_reference_capture_failure_after_start_terminalizes_attempt
5 passed

uv run --no-sync pytest -q tests/test_codex_plugin.py tests/test_mcp_queue_next.py tests/test_mcp_stdio_e2e.py tests/test_process_attempt_e2e.py
43 passed

uv run --no-sync python -B scripts/verify.py
153 passed
```

Latest Patch 2 contract-alignment verification completed:

```text
red: Patch 2 contract/doc regressions failed before implementation

uv run --no-sync pytest -q tests/test_adapter_contracts.py::test_cli_plan_init_contract_declares_bootstrap_behavior tests/test_adapter_contracts.py::test_declared_adapter_surfaces_match_active_contract tests/test_simplified_contract.py::test_plans_doc_matches_live_schema_contract tests/test_simplified_contract.py::test_handoff_acp_repair_commit_wording_is_precise
4 passed

uv run --no-sync python -B scripts/check_protected_files.py
Protected source-of-truth files are unchanged.

uv run --no-sync python -B scripts/verify.py
156 passed
```

## Planning Ledger

Active plan:

- None.

Recently completed plans:

- `plan-contract-alignment-patch-20260708`: `Contract alignment patch`
- `plan-safety-patch-20260708`: `Path and attempt-run safety`
- `plan-acp-repair-20260708`: `ACP repair`
- `plan-projections-layer-20260708`: `Projection layer`
- `plan-module-deepening-20260708`: `Module deepening`
- `plan-work-graph-provenance-fixes-20260708`: `Work graph provenance fixes`
- `plan-plugin-cache-refresh-complexity-drift-20260707`: `Plugin cache refresh after complexity
  drift fixes`
- `plan-complexity-drift-fixes-20260707`: `Complexity drift fixes`
- `plan-plugin-cache-refresh-20260707`: `Plugin cache refresh`
- `plan-accepted-provenance-hardening-20260707`: `Accepted provenance hardening`
- `substrate-hardening-20260707`: `Substrate hardening`
- `plan-substrate-20260707`: `Goal Mode substrate pivot`
- `plan-completion-proof-20260707`: `Plan completion proof semantics`

Accepted tasks:

- `task-align-substrate-docs-20260707`: aligned source contracts, skills, metadata, protected
  hashes, planning ledger, handoff, and verification with the substrate branch plan.
- `task-remove-ai-prose-steering-docs-20260707`: tightened steering docs using the Pangram and
  Grammarly common-AI-prose references, refreshed protected hashes, and verified the repo.
- `task-launch-packet-capture-20260707`: added `attempt-run --launch-packet` and
  `--verifier-intent`, copied and hashed those files before worker product mutation, injected
  packet references into assignment metadata and worker environment, wrote launch-time
  `command.json` with workspace and cwd metadata, added focused e2e coverage, refreshed source
  locks, and verified the repo.
- `task-generic-lineage-20260707`: added `tasks.lineage_json`, `task-create --lineage`, queue
  projection of task lineage, integrity validation for lineage references, schema v3 migration,
  focused tests, source-lock refresh, and verified the repo.
- `task-recovery-state-20260707`: added latest acceptance reads, compact `recovery_state` output
  through CLI and MCP, liveness file age when available, packet hash recovery, lineage projection,
  git summary, warning flags, focused tests, source-lock refresh, and verified the repo.
- `task-evidence-digests-20260707`: added compact evidence digests to terminal evidence, exposed
  parsed digests through latest evidence and recovery state, preserved raw artifact references,
  refreshed source locks, and verified the repo.
- `task-linked-repair-20260707`: made blocked queue inspection surface repair-lineage guidance,
  allowed linked repair tasks to reactivate blocked plans through task intent, refreshed source
  locks, and verified the repo.
- `task-shipping-proof-20260707`: exposed `shipping_proof_of` lineage as final proof recovery
  state, kept final proof as generic task intent, refreshed source locks, and verified the repo.
- `task-warning-gates-20260707`: added ACP warnings for missing packet hashes, missing launch
  metadata artifacts, and completed plans without final proof; preserved unbacked product mutation
  as a hard ACP failure; exposed recovery warning flags; refreshed source locks; and verified the
  repo.
- `task-final-proof-20260707`: recorded final substrate proof with full verification, source-lock
  check, queue final-proof lineage evidence, and `SUBSTRATE_PLAN.md` implementation audit.
- `task-plan-completion-semantics-20260707`: corrected plan completion semantics so accepted
  non-final tasks leave their plan active for linked follow-up work, accepted `shipping_proof_of`
  tasks close the plan, idle active plans surface lineage guidance through `queue-next`, ACP warns
  when final proof is still missing, protected docs and skills name the contract, and verification
  passed.
- `task-plan-completion-final-proof-20260707`: recorded final proof for the completion-semantics
  correction with full verification, protected lock, planning integrity, and handoff evidence.
- `task-substrate-hardening-20260707`: allowed cross-plan historical lineage, surfaced latest
  evidence and acceptance for active plans with no open task, recorded effective packaged-launcher
  reasoning metadata, added deterministic raw-log summaries to evidence digests, bumped the plugin
  cachebuster, and verified the repo.
- `task-substrate-hardening-proof-20260707`: recorded final proof for the substrate hardening work
  with full verification, plugin validation, source ledger evidence, and handoff update.
- `task-accepted-provenance-hardening-20260707`: enforced accepted attempt-run provenance for ACP,
  validated real attempt-run metadata, filtered pre-existing dirty product paths out of worker
  attribution, migrated the planning schema to v4 with `review_required` and a database-level
  single-active-plan invariant, hardened timeout/log handling, fixed launcher path/source
  resolution, corrected low-assurance policy, expanded integrity checks, and verified the repo.
- `task-accepted-provenance-hardening-proof-20260707`: recorded final proof for the accepted
  provenance hardening with Ruff, full verification, planning integrity, and source evidence.
- `task-plugin-cachebuster-20260707`: bumped the plugin source manifest to
  `0.2.0+codex.20260707223857`, validated the package, and verified the repo.
- `task-plugin-cache-refresh-proof-20260707`: recorded final proof for the plugin cachebuster
  source update before installing the refreshed Codex cache.
- `task-complexity-drift-fixes-20260707`: centralized product provenance inspection, added
  current product-state proof for ACP, extracted lifecycle policy helpers, bounded verifier
  stdout/stderr retention, declared the active CLI/MCP/plugin/worker surfaces, hardened
  outside-workspace artifacts, marked the old follow-up-plan insight superseded, and verified the
  repo.
- `task-complexity-drift-fixes-proof-20260707`: recorded final proof for the complexity drift
  fixes with focused tests, Ruff, full verification, and planning integrity.
- `task-plugin-cache-refresh-complexity-drift-20260707`: bumped the plugin source manifest to
  `0.2.0+codex.20260707232244`, validated the package, ran plugin tests, and installed the local
  Codex plugin cache.
- `task-plugin-cache-refresh-complexity-drift-proof-20260707`: recorded final proof for the
  refreshed plugin cache before final ACP.
- `task-work-graph-provenance-fixes-20260708`: extracted shared durable completion checks into
  `work_graph.py`, made ACP use the same durable-completion predicate as the store, preserved
  rename source deletion in product provenance, added regression coverage, and verified the repo.
- `task-plugin-cache-refresh-work-graph-20260708`: bumped the plugin source manifest to
  `0.2.0+codex.20260708040855`, validated the package, ran plugin tests, and installed the local
  Codex plugin cache.
- `task-work-graph-provenance-proof-20260708`: recorded final proof for the work graph provenance
  fixes and plugin cache refresh with full verification, planning integrity, skill inventory, and
  protected source checks.
- `task-module-deepening-20260708`: deepened the highest leverage modules without expanding the
  substrate state space: `work_graph.py` now owns relation vocabulary and read-side graph
  projections, `recovery.py` owns queue recovery projection, `process_attempt.py` has explicit
  path/reference/environment/verifier phases, `evidence_codec.py` owns compact evidence check
  encoding and parsing, focused tests were added, the plugin cachebuster was refreshed to
  `0.2.0+codex.20260708043832`, and verification passed.
- `task-module-deepening-proof-20260708`: recorded final proof for the module deepening refactor
  with full verification, focused module/e2e coverage, refreshed plugin cache, and current
  handoff/planning evidence.
- `task-projections-layer-acp-assessment-20260708`: documented the requested ACP run against the
  source repo, recorded that the target-workspace ACP gate failed because `.codex-supervisor/` is
  not ignored and dirty source-maintenance paths were not attempt-run-backed product mutations, and
  recovered the blocked projection-layer implementation task.
- `task-projections-layer-proof-20260708`: recorded final proof for the projection-layer work with
  full verification, focused projection/queue/ACP coverage, Ruff, projected recovered-blocker
  coverage, and the ACP outcome preserved as a source-workspace caveat.
- `task-acp-repair-20260708`: added the missing `.codex-supervisor/` ignore rule, refreshed the
  protected `.gitignore` hash, verified source locks and full tests, and confirmed clean-worktree
  ACP passes with no failures. The `.gitignore` change landed in `c00e2d1`; the ACP repair proof
  was recorded in `36cb840`.
- `task-acp-repair-proof-20260708`: recorded final proof for the ACP repair with full verification,
  durable final-proof lineage, and commit `36cb840`.
- `task-safety-patch-20260708`: fixed plugin CLI path binding so supervisor-owned relative paths
  are resolved against the invocation workspace before the source CLI cwd changes, rejected relative
  MCP planning paths at dispatch, resolved plugin MCP env paths before launch, terminalized
  post-start `attempt-run` reference-capture failures as failed evidence, and added red/green
  regression coverage.
- `task-safety-patch-proof-20260708`: recorded final proof for Patch 1 with focused regression
  tests, affected-surface tests, full verification, and durable planning evidence.
- `task-contract-alignment-patch-20260708`: declared `plan-init` in adapter operation contracts,
  aligned `PLANS.md` with live meta keys and the `review_required` task field, refreshed the
  protected `PLANS.md` hash, corrected the ACP repair handoff commit wording, and added focused
  contract/doc regression tests.
- `task-contract-alignment-proof-20260708`: recorded final proof for Patch 2 with focused contract
  tests, protected lock verification, full verification, and durable planning evidence.
- `task-ci-path-normalization-repair-20260708`: fixed the GitHub CI path-normalization failure by
  normalizing relative artifact strings before workspace containment checks; the first terminal
  evidence record was rejected because high-assurance evidence was missing risk notes.
- `task-ci-path-normalization-repair-evidence-20260708`: recovered the blocked CI repair task with
  accepted high-assurance evidence, including focused Windows verification, a Linux Python 3.14
  container spot check for `..\\outside.txt`, full verification, and risk notes.
- `task-ci-path-normalization-repair-proof-20260708`: recorded final proof for the CI repair chain;
  `queue-next` returns `none` after the accepted proof.

Ready next task:

- None. `plan-substrate-20260707`, `plan-completion-proof-20260707`,
  `substrate-hardening-20260707`, `plan-accepted-provenance-hardening-20260707`,
  `plan-plugin-cache-refresh-20260707`, `plan-work-graph-provenance-fixes-20260708`,
  `plan-module-deepening-20260708`, `plan-projections-layer-20260708`, and
  `plan-acp-repair-20260708`, `plan-safety-patch-20260708`,
  `plan-contract-alignment-patch-20260708`, and
  `plan-ci-path-normalization-repair-20260708` are complete.

## Next Action

No source task is ready. Patch 1 and Patch 2 of the three-patch sequence are verified and recorded.
Patch 1 fixed plugin/MCP path binding and `attempt-run` setup-failure terminalization. Patch 2
declared `plan-init`, aligned `PLANS.md` with the live schema contract, refreshed protected locks,
and corrected ACP repair provenance wording. The GitHub CI path-normalization repair is verified and
recorded; after its ACP lands, the next source task is Patch 3 projection-layer cleanup.
