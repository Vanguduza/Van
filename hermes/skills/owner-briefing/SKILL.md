---
name: owner-briefing
description: >-
  Produces owner-facing situational briefings from verified gateway state,
  attention queues, reminders, and project health. Use when the owner asks for
  a daily brief, status update, what needs attention, or end-of-day summary.
---

# Owner Briefing

## Purpose

Synthesize **verified** owner-relevant state into a concise briefing. Briefings inform; they do not mutate projects unless explicitly requested and authorized.

## Preconditions

- Gateway attestation or deterministic read APIs available (A1)
- Target projects identified; Project Truth paths known from `registries/projects.json`
- No OAuth tokens in prompt context

## Workflow

1. **Scope** — Confirm time window (today, week) and projects in scope
2. **Gather verified state only**
   - Attention queue / reminders (deterministic)
   - Open decisions awaiting owner input
   - Infrastructure readiness (gateway, Hermes profile doctor if relevant)
   - Per-project: last known SHA, ledger gaps — **only if evidenced**
3. **Label gaps** — Items you cannot verify are listed under "Unverified / blocked", not implied as OK
4. **Format output** using template below
5. **Action class** — Briefing delivery is A1; any follow-up mutations need separate authorization

## Output template

```markdown
# Owner briefing — [date/window]

## Needs attention now
- [item] — source: [gateway/reminder/truth] — action class if acting: [A1–A4]

## Project pulse
| Project | Verified state | Blockers |
|---------|----------------|----------|

## Decisions waiting on you
- ...

## What I will not claim without evidence
- ...

## Suggested next actions (non-mutating unless you approve)
1. ...
```

## Fail closed

If gateway or truth sources are unreachable:

- Do not invent counts, deploy status, or "all clear"
- Return partial briefing with explicit `DEGRADED` header
- List what restores full briefing capability

## References

- Authority order: `hermes/profile/van/SOUL.md`
- Project registry: `registries/projects.json`
