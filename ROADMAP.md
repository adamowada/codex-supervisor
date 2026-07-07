# Roadmap

The `feature/substrate` branch turns `codex-supervisor` into the durable evidence substrate for
Codex Goal Mode.

The durable model stays:

```text
TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision
```

Every stage strengthens Goal Mode recovery and proof without adding supervisor job types.

## Stage 1: Substrate Source Contract

Purpose: make the repository speak one substrate language.

Steps:

1. Promote `SUBSTRATE_PLAN.md` as the branch master plan.
2. Update protected docs to name Goal Mode as the strategic layer and Supervisor as the durable
   evidence substrate.
3. Update repo-local and packaged skills so agents preserve the role split.
4. Update plugin and package descriptions away from orchestration/control-plane identity.
5. Record the branch state in `plans/planning.sqlite3` and `HANDOFF.md`.
6. Refresh protected source locks.
7. Run the verification gate.

Done when:

- `README.md`, `AGENTS.md`, `SUBSTRATE_PLAN.md`, `PLANS.md`, `ARCHITECTURE.md`, `CONTRACTS.md`,
  `ROADMAP.md`, `SOP.md`, `TESTING.md`, and `DECISIONS.md` agree.
- The packaged Desktop skill names the durable Goal Mode substrate contract.
- `scripts/check_protected_files.py` passes.
- `scripts/verify.py` passes.

## Stage 2: Launch Packet Capture

Purpose: let Goal Mode provide rich worker context while Supervisor records packet identity.

Steps:

1. Add a free-form launch packet input to the worker launch path.
2. Copy the packet into supervisor-owned evidence storage.
3. Hash the packet and expose the hash in assignment metadata.
4. Capture verifier intent and verifier intent hash when present.
5. Keep the packet schema flexible.
6. Add tests that prove packet path/hash are durable and available to the worker.

Done when:

- `attempt-run` records packet identity before product mutation.
- Workers can read the packet through assignment metadata.
- Queue inspection can surface packet identity.
- Verification passes.

## Stage 3: Launch-Time Command Metadata

Purpose: make active attempts inspectable while they are running.

Steps:

1. Write `command.json` before launching the worker process.
2. Include command, cwd, launcher, model/reasoning, timeout, task id, attempt id, packet hash,
   verifier hash, git head, and start time.
3. Preserve command metadata when launch fails or times out.
4. Add tests for running-state command metadata.

Done when:

- Active attempts have immediate launch metadata.
- Failed launches still leave durable command evidence.
- Verification passes.

## Stage 4: Generic Lineage

Purpose: make retry, repair, review, and final-proof relationships recoverable without job types.

Steps:

1. Add one generic relation mechanism for task lineage.
2. Support relation names such as `retry_of`, `repair_of`, `review_of`, and `shipping_proof_of`.
3. Show lineage in queue inspection.
4. Add integrity checks for missing lineage targets.
5. Add tests for repair and review linkage.

Done when:

- Goal Mode can link follow-up work to the rejected or accepted work that caused it.
- No semantic engineering category becomes a supervisor mode.
- Verification passes.

## Stage 5: Recovery-Oriented Queue State

Purpose: let Goal Mode resume from compact state alone.

Steps:

1. Enrich `queue-next` with active task, active attempt, liveness age, latest evidence, latest
   acceptance, packet hash, verifier hash, lineage, git summary, warning flags, and next transition.
2. Keep MCP read-only and explicit about the planning path.
3. Add tests for recovery state after running, failed, blocked, and accepted attempts.

Done when:

- Goal Mode can recover after compaction or crash without reading raw logs first.
- MCP exposes the same compact recovery shape.
- Verification passes.

## Stage 6: Evidence Digests

Purpose: summarize raw logs and artifacts without losing the detailed evidence trail.

Steps:

1. Generate compact digests for verifier result, changed files, declared artifacts, warnings, log
   sizes, important tails, risk/gap/next-action notes, and acceptance rationale.
2. Store digest references through the existing evidence path until repeated queries justify a new
   table.
3. Add tests for digest content and raw-artifact preservation.

Done when:

- Queue inspection can show useful evidence summaries.
- Raw logs remain available for audit.
- Verification passes.

## Stage 7: Repair And Final Proof

Purpose: make nondeterminism and shipping proof normal supervised work.

Steps:

1. Document and test repair tasks linked to rejected attempts.
2. Document and test review tasks linked to the work they inspect.
3. Document and test final-proof tasks linked to the work they prove.
4. Add warnings first, then hard gates when proven: missing packet, missing launch metadata, product
   mutation without accepted attempt, and completion without final proof.

Done when:

- A fresh Goal Mode plus Supervisor run can advance, retry, repair, review, and ship with durable
  proof.
- Final completion has evidence or an explicit unsupervised exception.
- Verification passes.
