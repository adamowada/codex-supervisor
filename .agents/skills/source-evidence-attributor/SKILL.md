---
name: source-evidence-attributor
description: Track inspiration, attribution, and license posture when using OSS sources, cloned repos, plugin caches, vendor imports, docs, examples, or external code. Use before copying, adapting, integrating, or citing source material.
---

# Source Evidence Attributor

Separate inspiration from reuse.

If the current user turn is read-only or review-only, do not edit attribution files, copy source
material, update planning SQLite, or change license posture. Return attribution findings and
proposed edits only.

## Rules

- If source code, tests, prompts, or docs are copied or closely adapted, check the upstream license first.
- Treat license-missing sources as reference-only until clarified.
- Preserve required copyright, license, and notice text.
- Add or update `ATTRIBUTIONS.md` for durable public-facing attribution.
- Because `ATTRIBUTIONS.md` is protected, route completed attribution edits through
  `source-lock-operator` before ACP or publication.
- Record a decision before direct code reuse or dependency integration.
- Prefer linking paths, commits, URLs, and license files over copying large excerpts.

Use "inspired by" only when the implementation is original and no protected expression was copied.
