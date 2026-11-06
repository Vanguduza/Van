# DIAL Codex Engineering Authority

Codex must follow the same repository and Oracle orchestration authority as Claude.

## Operator mode

When `dial-oracle-control` is enrolled, use its typed `dial_*` tools for DIAL status, progress, instructions, pause/resume, reprioritisation and gate decisions. Oracle owns the persistent `dial-development-root` mission, queue, runtime selection, recovery and continuation; this Codex session does not.

- Read live run state from Oracle evidence. Never infer that DIAL is idle from a clean local worktree, absence of a local agent process, or the lifetime of this Codex session.
- Ordinary development enters through the persistent Oracle orchestrator and remains subject to the repository development gate.
- Never request, add or emulate a generic shell/filesystem primitive through the DIAL operator gateway.
- The gateway is DIAL-only and cannot control unrelated Hermes projects.
- WhatsApp owner control is another adapter to the same owner-control authority, not a separate orchestrator. Normal owner directions use `dial_owner_steer`: Hermes acknowledges immediately, preserves any active repository writer to a safe boundary, then executes the steer before autonomous work resumes. Read-only questions may use `dial_owner_live_turn`; `dial_submit_instruction` is deliberate background queueing only.
- Authenticated owner WhatsApp prose and supported uploads may create typed owner-steer requests, but they never expose a generic shell/filesystem primitive or bypass repository truth/security/verification boundaries.

## Project Truth authority

Project Truth writes are never self-authorized by an agent. Every substantive change must trace to an owner instruction through `OWNER_EXPLICIT`, `OWNER_DERIVED`, or `OWNER_DELEGATED_AUTONOMY` authority and be covered by an append-only authorization record. An owner instruction to fix blockers using the best/recommended solution counts as derived authority for necessary technical consequences and truth reconciliation, but not material scope expansion. Read-only requests, agent preference, research, CI and tool output are `NO_AUTHORITY`.

Use `node agent-system/orchestration/project-truth-authority.mjs issue ...` only against an existing owner-originated Oracle instruction job; never fabricate an owner instruction or authorization receipt. See `PROJECT_TRUTH_PROTOCOL.md`.

Canonical architecture: `docs/orchestration/DIAL_OPERATOR_GATEWAY.md`.

For implementation work, follow the Feature/FRC/security/VEKL rules in `CLAUDE.md` and current repository source of truth.
