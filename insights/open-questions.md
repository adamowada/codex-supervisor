# Open Questions

- Should `codex-supervisor` adopt Sandcastle directly for TypeScript-based sandbox orchestration, or
  only borrow its patterns into Python?
- Should the MCP server be implemented before or after the Codex Exec backend?
- Which projects should be the first live adapter targets?
- What should count as enough evidence to auto-promote a skill update?
- How should multiple parallel workers resolve file conflicts?
- After Stage 6, which official Codex surface should `codex-supervisor` use to create, pause,
  resume, inspect, and clear native Goals without writing raw local database rows? Stage 5 only
  renders/preflights Goal Contracts and relies on prompt fallback when native Goals are unavailable.
- Should Story Loop iterations commit after every verified task by default, or should commit policy
  vary by project adapter?
