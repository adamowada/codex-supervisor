---
name: codex-state-readonly-audit
description: Perform privacy-safe read-only audits of a local Codex home folder. Use when inspecting ~/.codex structure, sessions, logs, state SQLite databases, config, plugins, skills, cached tools, archives, or recovery artifacts.
---

# Codex State Read-Only Audit

Audit by metadata first, content second, and secrets never.

## Rules

- Do not edit anything under the Codex home folder.
- Do not print token values, auth payloads, raw private chats, or full logs.
- Treat `auth.json`, `cap_sid`, `.sandbox-secrets`, and similar files as sensitive.
- For SQLite, open read-only when possible and report schemas, counts, ranges, and aggregates before row content.
- For JSONL sessions, report counts, roles, term frequencies, and patterns; quote only tiny non-sensitive fragments if essential.

## Report

Include folder size, largest areas, important databases, session volume, plugin/skill inventory, backup/recovery files, and candidate workflow skills.
