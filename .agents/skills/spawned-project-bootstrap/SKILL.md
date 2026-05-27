---
name: spawned-project-bootstrap
description: Bootstrap a new project spawned by codex-supervisor with the full source-of-truth, planning SQLite, source-lock, verification, insights, skill, and handoff scaffold. Use when creating or auditing the initial agentic engineering factory structure for a new repo; use setup-agent-docs only for lightweight imported-skill prerequisites.
---

# Spawned Project Bootstrap

Create the full scaffold for a project that `codex-supervisor` will supervise. This is the concrete
bootstrap checklist; it is not a generic docs setup helper.

If the current user turn is read-only, review-only, audit-only, no-edits, or no-mutation mode, do
not create files, initialize databases, edit docs, update trackers, or run setup commands. Return
the exact proposed file tree, planning rows, source-lock set, verification commands, and scaffold
gaps only.

## Required Scaffold

1. Top-level doctrine: `README.md`, `AGENTS.md`, `PLANS.md`, `ARCHITECTURE.md`, `CONTRACTS.md`,
   `ROADMAP.md`, `SOP.md`, `TESTING.md`, `DECISIONS.md`, `LICENSE`, and `ATTRIBUTIONS.md` when
   public or source-inspired. Add `HANDOFF.md` as a mutable fresh-thread snapshot, not locked
   doctrine.
2. Root repo hygiene: `.gitignore` that excludes local caches, worktrees, generated artifacts,
   compiler metadata such as `*.tsbuildinfo`, and ignored source clones; `.gitattributes` that pins
   LF text files and marks SQLite/database files binary.
3. Operational state: `plans/planning.sqlite3` with at least one active plan, milestones,
   acceptance criteria, AFK/HITL tasks, and progress records.
4. Source locks: protected-file manifest and hash check for stable top-level doctrine files.
5. Insights memory: `insights/README.md`, `insights/graph.md`, `insights/open-questions.md`, and any
   task-relevant learning notes.
6. Verification: focused tests, broad local gate, file justification, public hygiene, planning
   integrity, skill inventory, source inventory, and lock checks scaled to repo scope. Prefer these
   named gates when the repo adopts the full supervisor scaffold: `scripts/verify.py`,
   `scripts/print_protected_hashes.py`, `scripts/check_protected_files.py`,
   `scripts/check_file_justification.py`, `scripts/check_planning_integrity.py`,
   `scripts/check_public_repo_hygiene.py`, `scripts/check_skill_inventory.py`, and
   `scripts/check_source_inventory.py`.
7. Skills: repo-local skills only when they remove repeated instructions; prefer small skills with
   explicit triggers over omnibus methodology.
8. Handoff: a compact fresh-thread bootstrap prompt that reads minimum orientation first, then uses
   planning SQLite to select task-relevant docs.

## Procedure

1. Read the user's project goals, non-goals, target runtime, public/private posture, expected
   deployment path, and known source inspirations.
2. Choose whether the project needs the full scaffold. If it only lacks imported-skill context,
   route to `setup-agent-docs` instead.
3. Draft the source-of-truth authority matrix: locked docs, planning state, issue tracker, handoff,
   insights, generated artifacts, and chat.
4. Seed planning SQLite with a bootstrap plan and one next actionable task. Once deterministic
   scaffold apply completes, mark the bootstrap scaffold plan complete and create the user's real
   product plan/task before running Story Loop. Use HITL honestly for unresolved product,
   credential, privacy, or publication decisions.
5. Add source locks only after the stable docs exist; keep `HANDOFF.md` mutable unless the project
   explicitly locks it.
6. Add verification gates that prove the scaffold, not merely the application code.
7. Record browser-smoke pass/fail as planning progress and link screenshots or logs when present;
   keep `HANDOFF.md` aligned with the latest smoke result.
8. Prefer OS-neutral file-list copy or equivalent promotion steps over shell-specific patch
   pipelines when promoting worker output into a checkout that already has planning mutations.
9. Run verification as separate command invocations instead of relying on shell-specific chained
   command lines.
10. For JSON-heavy queue mutations, prefer repo-local input files, stdin, or typed `--*-json-file`
   surfaces when available instead of nested shell-quoted JSON.
11. Record any copied, adapted, or inspiration source material in attribution files before publication.
12. Run focused checks first, then the broad gate. If publication is blocked by untracked files,
   leave the queue at a HITL ACP checkpoint.

## Result Contract

Report the created or proposed scaffold paths, planning rows, protected files, verification commands,
skills added, attribution posture, unresolved HITL decisions, and the next AFK/HITL task.
