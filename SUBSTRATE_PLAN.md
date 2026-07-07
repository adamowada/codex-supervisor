# Substrate Plan

Branch: `feature/substrate`

## Thesis

`codex-supervisor` should be the durable Goal Mode substrate.

It is not the autonomous brain, not the strategic orchestrator, and not a rigid workflow engine.
Goal Mode owns judgment. Supervisor makes the work recoverable, inspectable, attributable, and
acceptance-gated.

## Role Split

Goal Mode owns:

- the long-lived objective, strategy, sequencing, and recovery choices;
- the free-form worker launch packet and verifier intent;
- diagnosis of failed or incomplete attempts;
- the choice to advance, retry, repair, review, ship, or stop;
- final judgment about whether the overall goal is complete.

Supervisor owns:

- durable `TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision`;
- launch packet capture, hashing, and injection into worker assignment;
- launch-time command metadata, liveness, logs, artifacts, and verifier output;
- product mutation provenance through `attempt-run`;
- generic task lineage for retry, repair, review, and final proof;
- compact read-only recovery state for Goal Mode;
- proof that accepted work matches actual worker and verifier reality.

Worker processes remain ephemeral `codex exec` workers. They should not be expected to remember the
project. Their intelligence comes from the launch packet Goal Mode gives them.

## Core Loop

```text
Goal Mode decides next unit
        |
        v
Goal Mode writes free-form launch packet + verifier intent
        |
        v
Supervisor records TaskIntent + packet/hash
        |
        v
Supervisor launches one RunAttempt
        |
        v
Worker does scoped work
        |
        v
Supervisor captures liveness, command metadata, logs, artifacts
        |
        v
Verifier/review/checks produce EvidenceBundle
        |
        v
Supervisor records AcceptanceDecision
        |
        v
Goal Mode reads compact state and chooses:
   advance | retry | repair | review | ship | stop
```

## Non-Goals

- Do not add supervisor job types for feature, bug, review, repair, shipping, or release work.
- Do not move strategy, sequencing, or semantic engineering judgment into Supervisor.
- Do not create a second workflow engine beside Goal Mode.
- Do not require strict packet schemas before repeated access patterns prove they are needed.
- Do not make worker processes responsible for durable memory.

## Implementation Sequence

1. Align source-of-truth docs, repo-local skills, packaged Desktop skill, plugin metadata, handoff,
   and planning ledger around the durable Goal Mode substrate identity.
2. Extend `attempt-run` with free-form launch packet capture, packet hashing, verifier intent
   hashing, and worker assignment injection.
3. Write `command.json` at launch time with command, cwd, launcher, model/reasoning, timeout, task
   id, attempt id, packet hash, verifier hash, git head, and start time.
4. Add generic task lineage, using one small relation mechanism such as `review_of`, `repair_of`,
   and `shipping_proof_of`.
5. Add `queue-next` and MCP read-only fields for active task, active attempt, liveness age,
   latest evidence, latest acceptance, packet hash, verifier hash, lineage, git summary, and warning
   flags.
6. Add structured evidence digests over raw logs: verifier result, changed files, declared
   artifacts, warnings, log sizes, important tails, risk/gap/next-action notes, and acceptance
   rationale.
7. Treat repair as a normal linked task. Failed verifier or review evidence should lead Goal Mode
   to create a repair task linked to the rejected attempt.
8. Treat shipping and final proof as normal supervised work. Goal Mode must not declare the goal
   complete until final proof is recorded or an explicit unsupervised exception is declared.
9. Add warnings first, then hard gates when behavior is proven: missing packet, missing launch
   metadata, product mutation without accepted attempt, and merge or completion without final proof.

## Acceptance Standard

The branch is done when a fresh Goal Mode plus Supervisor run can start intentionally, every product
mutation is attributable to an accepted attempt, every retry/repair/review is linked, active worker
state is visible while running, Goal Mode can recover from compact state alone, and final completion
has durable proof.

Clean hybrid: Goal Mode thinks. Supervisor remembers, launches, verifies, and proves.
