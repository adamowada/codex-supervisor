---
name: fresh-thread-code-reviewer
description: Prepare or run a fresh-context code review for a repository, branch, commit, diff, PR, or whole codebase. Use when the user asks to code review everything, review this branch, review this commit/diff, review for bugs, review for code quality, or review architecture.
---

# Fresh Thread Code Reviewer

Make the review scope and lens explicit before reading deeply.

Reviews are read/report-only unless the user separately asks to fix findings. In read-only,
review-only, audit-only, no-edits, or no-mutation mode, do not edit files, stage, commit, push,
mutate trackers, update planning state, or run cache-writing verification commands.

## Scope Modes

- `everything`: review the whole repo surface and source-of-truth docs.
- `branch`: compare the current branch to a base branch or merge base.
- `commit`: review one commit by SHA.
- `diff`: review staged, unstaged, or supplied patch text.
- `PR`: review changed files, discussion, and CI status from GitHub connector data.

If the user did not specify the fixed point for a branch review, ask for it or default to the repo's main branch when obvious.

## Review Lenses

- `everything`: correctness, regressions, tests, security/privacy, maintainability, architecture, docs, and release risk.
- `quality`: readability, duplication, naming, local patterns, error handling, and test fit.
- `architecture`: module depth, locality, seams, coupling, testability, ADR/domain-language fit, and AI navigability.
- `standards`: conformance to documented repo conventions, coding standards, AGENTS.md, ADRs, and source-of-truth rules.
- `spec`: whether the diff faithfully implements the originating issue, PRD, plan, or task contract.

For architecture-only reviews, use `improve-codebase-architecture` vocabulary: domain glossary
first, ADRs second, then report friction in terms of module depth, locality, seams, adapters, and
leverage.

For normal code reviews, findings must be concrete bugs, regressions, spec misses, security/privacy
risks, missing tests, or source-of-truth drift. Route broad architecture commentary to
`improve-codebase-architecture` or task shaping unless the user selected the `architecture` lens.

For branch, commit, diff, or PR reviews, consider a two-axis review split:

- **Standards**: read the repo standards, then report where the diff violates documented expectations.
- **Spec**: read the originating issue, PRD, plan, or task contract, then report missing requirements, scope creep, and incorrect implementations.

Run Standards and Spec reviews in separate fresh contexts when the host exposes subagent tools;
otherwise prepare self-contained prompts or run the lenses locally in separate passes, then aggregate
findings without blending the axes.

## Fresh Prompt Contract

Include:

- repo root, branch, base/ref, commit, or diff command;
- allowed read scope;
- review lens;
- source-of-truth docs to read first;
- commands to inspect diff and tests;
- expected finding format;
- instruction to prioritize actionable issues over summaries;
- instruction to avoid fixing unless explicitly asked.

Findings lead. Use file/line references when possible and separate confirmed bugs from judgment calls.
