# Roadmap

The simplification refactor rebuilds `codex-supervisor` from the inside out:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Every stage strengthens that model before adding surface area.

## Stage 1: Foundation Contract

Purpose: make the repository speak one control-plane language.

Steps:

1. Define the compact control-plane model in source-of-truth docs.
2. Keep planning SQLite on the schema from `PLANS.md`: `meta`, `plans`, `tasks`, `attempts`,
   `evidence_bundles`, and `decisions`.
3. Keep one repo-local skill that points agents at the active model.
4. Keep CI focused on the verification gate in `scripts/verify.py`.
5. Keep insights focused on durable design lessons.
6. Keep `HANDOFF.md` current and action-oriented.
7. Keep protected source-of-truth hashes aligned with the active source document set.

Done when:

- `README.md`, `AGENTS.md`, `PLANS.md`, `ARCHITECTURE.md`, `CONTRACTS.md`, `ROADMAP.md`, `SOP.md`,
  `TESTING.md`, and `DECISIONS.md` agree.
- `scripts/check_planning_integrity.py` validates the planning database.
- `scripts/check_skill_inventory.py` validates the active skill surface.
- `scripts/check_protected_files.py` passes.
- `scripts/verify.py` passes.
- The planning database has an active simplification plan and a ready next task.

## Stage 2: Policy Core

Purpose: make assurance levels executable.

Steps:

1. Add a small policy module for assurance and acceptance behavior.
2. Define `low`, `medium`, and `high` as explicit values.
3. Define evidence requirements for each assurance level.
4. Define acceptance requirements for each assurance level.
5. Add a function that maps task intent to an assurance policy.
6. Add a function that evaluates whether evidence satisfies a task's assurance.
7. Keep policy independent from CLI, MCP, plugin, and worker transport details.
8. Add focused tests for the assurance and acceptance matrix.
9. Record completion evidence in planning SQLite.

Done when:

- Assurance levels exist in code.
- Each assurance level has structured evidence requirements.
- Acceptance can be evaluated from task, attempt, and evidence records.
- The planning task `task-rebuild-policy-core-20260528` is completed with an evidence bundle.
- `scripts/verify.py` passes.

## Stage 3: Execution Attempts

Purpose: make all execution use one attempt shape.

Steps:

1. Define a typed `RunAttempt` model in code.
2. Define attempt statuses: `planned`, `running`, `succeeded`, `failed`, and `blocked`.
3. Add helpers to create and update attempt rows in planning SQLite.
4. Add helpers to attach evidence bundles to attempts.
5. Support manual attempts.
6. Support shell attempts.
7. Represent review as an attempt executor when it produces evidence.
8. Keep executor identity as transport.
9. Add tests for creating, completing, failing, and blocking attempts.

Done when:

- Manual, shell, review, and future Codex execution can share the same attempt shape.
- Attempt status transitions are validated.
- Attempt records can produce evidence bundles.
- Planning integrity catches invalid attempt and evidence relationships.
- `scripts/verify.py` passes.

## Stage 4: Small Interface

Purpose: prove the core can be operated through a tiny public surface.

Steps:

1. Add one inspection command.
2. Add one mutation command.
3. Make the inspection command answer the next operational state question from planning SQLite.
4. Make the mutation command perform one core transition.
5. Keep command arguments close to the database and contract vocabulary.
6. Add focused tests for both commands.
7. Keep the command surface auditable by inspection.

Done when:

- One read command works.
- One write command works.
- Both commands map directly to task, attempt, evidence, or acceptance behavior.
- Both commands have focused tests.
- The command surface remains small.
- `scripts/verify.py` passes.

## Stage 5: Worker Integration

Purpose: connect fresh-context Codex workers as attempt executors.

Steps:

1. Generate worker prompts from task intent plus assurance policy.
2. Launch a fresh-context Codex worker as a `RunAttempt`.
3. Capture worker output as evidence.
4. Normalize worker results into `EvidenceBundle` records.
5. Evaluate acceptance through the same policy path as manual and shell attempts.
6. Require high-assurance evidence for high-assurance worker tasks.
7. Add fake-worker tests before live Codex execution.
8. Add live Codex verification after the fake executor proves the contract.

Done when:

- Codex worker execution is represented as an attempt.
- Worker prompts are generated from the active task model.
- Worker results become evidence bundles.
- High-assurance worker work requires the evidence named by policy.
- Fake-worker tests pass.
- Live-worker behavior has a bounded verification path.

## Stage 6: Interface Growth

Purpose: grow larger surfaces as adapters over the proven core.

Steps:

1. Choose one adapter surface at a time: MCP, Desktop plugin, automation, GitHub, CI/CD, or spawned
   projects.
2. For each operation, declare the task intent it serves.
3. Declare the attempt it runs or inspects.
4. Declare the evidence it emits.
5. Declare the assurance level it can satisfy.
6. Declare the acceptance behavior it supports.
7. Add focused adapter tests.
8. Add the operation to the active surface after the core behavior exists.

Done when:

- Each adapter operation maps to task intent, attempt, evidence, and acceptance.
- Adapter state flows through the planning database or explicit external systems.
- Focused tests cover the adapter contract.
- The operation reduces operator effort enough to justify the surface.
