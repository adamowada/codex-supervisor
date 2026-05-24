---
name: skill-golden-eval-loop
description: Evaluate a Codex skill before promotion or after revision. Use when creating, changing, comparing, or trusting skills, prompts, worker instructions, or reusable agent workflows.
---

# Skill Golden Eval Loop

One skill change needs at least one realistic task that proves it helps.

If the current user turn is read-only or review-only, do not edit skills, spawn mutating evaluators,
write eval artifacts, or update insights. Return the golden task, rubric, and proposed eval protocol
only.

## Workflow

1. Define a tiny golden task with input artifact, expected behavior, and failure modes.
2. Run the current skill behavior or baseline if available.
3. Run the revised skill in fresh context when subagents are allowed.
4. Score with a small rubric: correctness, scope control, verification, privacy, and handoff quality.
5. Record the decision: promote, revise, split, or discard.
6. Add durable lessons to `insights/` when the result teaches a reusable pattern.

Avoid telling evaluators the intended answer unless the eval explicitly requires it.
