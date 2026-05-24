# Attributions

`codex-supervisor` is MIT-licensed original work. It uses the repositories below as ignored local
study sources and possible integration references. Their source code is not
vendored into this repository as full upstream projects; selected MIT-licensed skill material copied
or adapted into `.agents/skills/` is documented separately below.

## Ignored Inspiration Sources

The authoritative source clone inventory lives in `sources/README.md`: upstream URLs, pinned local
commits, observed license posture, license evidence hashes, and documented use posture are validated
there by `scripts/check_source_inventory.py`.

This file intentionally does not repeat that table. Keep source-clone metadata in one place to avoid
attribution drift; use this file for reuse rules and copied/adapted material that is actually present
in this repository.

## Reuse Rules

- Treat cloned repositories under `sources/` as ignored references, not vendored dependencies.
- Review each upstream license before copying source, tests, prompts, or docs.
- Record a decision before direct code reuse or integration.
- Treat Ralph and similar loop references as conceptual inspiration unless a later decision records
  direct copying or adapted material.
- Preserve upstream copyright, license, and notice requirements when reuse is approved.

## Integrated Skill Material

Selected files under `.agents/skills/` are copied, adapted, or synthesized from
`https://github.com/mattpocock/skills` at upstream commit
`b8be62ffacb0118fa3eaa29a0923c87c8c11985c`, as documented in `sources/README.md`.

The local provenance index for integrated skills lives at `.agents/skills/NOTICE.md`.

Copied and adapted for Codex-supervisor source-of-truth, planning SQLite, GitHub connector,
and full-auto worker workflows:

- `.agents/skills/improve-codebase-architecture/`
- `.agents/skills/grill-with-docs/`
- `.agents/skills/to-issues/`
- `.agents/skills/triage/`
- `.agents/skills/diagnose/`
- `.agents/skills/tdd/`
- `.agents/skills/prototype/`
- `.agents/skills/zoom-out/`

Adapted or synthesized from Matt Pocock skill patterns:

- `.agents/skills/setup-agent-docs/`
- `.agents/skills/fresh-thread-code-reviewer/`
- `.agents/skills/skill-router/`

The upstream project is MIT licensed:

```text
MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
