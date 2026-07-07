I reviewed the `.codex` SQLite state, the rollout conversation logs it points to, the heartbeat history, the Monopoly run thread, and the current `codex-supervisor` docs/code paths. My definite proposal:

**Codex Supervisor should become the durable Goal Mode substrate.**

Not the autonomous brain. Not the colloquial “supervisor.” Not a rigid workflow engine. Goal mode owns judgment; Supervisor makes the work recoverable, inspectable, attributable, and acceptance-gated.

**Core Loop**

```text
Goal Mode decides next unit
        |
        v
Goal writes free-form launch packet + verifier intent
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
Goal reads compact state and chooses:
   advance | retry | repair | review | ship | stop
```

**Responsibilities**

Goal mode MUST own:
- Long-lived objective, strategy, sequencing, and recovery.
- The free-form worker context packet.
- Failure diagnosis and whether to retry, repair, review, or advance.
- Final judgment about whether the overall goal is complete.

Supervisor MUST own:
- Durable `TaskIntent -> RunAttempt -> EvidenceBundle -> AcceptanceDecision`.
- Product mutation provenance through `attempt-run`.
- Worker process launch, liveness, command metadata, evidence capture, and acceptance records.
- Compact read-only state for Goal mode to resume after compaction/crash.
- Proof that accepted work matches actual worker/verifier reality.

Worker processes remain ephemeral `codex exec` workers. They should not be expected to remember the project. Their intelligence comes from the launch packet Goal gives them.

**Concrete Changes**

1. Add flexible launch packets, not strict schemas.
   Goal mode decides packet content. Supervisor copies it, hashes it, stores its path/hash, and injects it into the worker assignment.

2. Write `command.json` at launch time.
   Today it appears too late. Active attempts need immediate metadata: command, cwd, launcher, model/reasoning, timeout, task id, attempt id, packet hash, verifier hash, git head, and start time.

3. Add generic lineage.
   Use one small relation mechanism, not workflow-specific job types:

   ```text
   task A --review_of--> task B
   task C --repair_of--> task A
   task D --shipping_proof_of--> task A
   ```

4. Enrich `queue-next` / MCP read-only state.
   It should return enough for Goal to recover: active task, active attempt, liveness age, latest evidence, latest acceptance, packet hash, verifier hash, lineage, git summary, and warning flags.

5. Add structured evidence digests.
   Keep raw logs, but expose compact summaries: verifier result, changed files, declared artifacts, warnings, log sizes, important tails, acceptance rationale.

6. Treat repair as first-class, not exceptional.
   Failed verifier/review should naturally lead Goal to create a same-unit repair task linked to the rejected attempt. This embraces nondeterminism without making the system brittle.

7. Add shipping/final-proof as normal supervised work.
   Merge, final main validation, and release proof should have durable evidence too. Steering first: the skill should say Goal mode MUST not treat the goal as complete until final proof is recorded or an explicit unsupervised exception is declared.

**Implementation Order**

1. Update docs/skill language: “durable Goal Mode substrate,” not “autonomous manager.”
2. Extend `attempt-run` with launch packet capture, launch-time `command.json`, and hashes.
3. Add generic task lineage.
4. Enrich `queue-next` with compact recovery state.
5. Add evidence digest generation.
6. Add final-proof/shipping task guidance.
7. Add warnings before hard gates: missing packet, missing launch metadata, product mutation without accepted attempt, merge without final proof.

**Acceptance Standard**

The integration is “done” when a fresh autonomous run intentionally starts in Goal+Supervisor mode, every product mutation is attributable to an accepted attempt, every retry/repair/review is linked, active worker state is visible while running, Goal mode can recover from compact state alone, and final completion has durable proof.

That is the clean hybrid: Goal mode thinks; Supervisor remembers, launches, verifies, and proves.
