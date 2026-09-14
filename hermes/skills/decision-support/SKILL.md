---
name: decision-support
description: >-
  Structures decisions with options, tradeoffs, risks, and explicit approval
  paths for destructive (A4) actions. Use when the owner faces a choice,
  asks what to do, or needs approval-ready decision records.
---

# Decision Support

## Purpose

Help the owner decide — not decide for them on A4 matters. Surface options with honest uncertainty and policy gates.

## Workflow

1. **Frame decision** — decision statement, constraints, reversibility
2. **Classify actions** — tag each option's peak action class (A1–A5)
3. **Load context** — Project Truth, grants, deterministic state relevant to decision
4. **Generate 2–4 options** — including explicit "do nothing / wait" when valid
5. **Score dimensions** — impact, risk, effort, reversibility, truth alignment
6. **Approval path** — for any A4 option, specify owner approval mechanism (device biometric when available)
7. **Record** — if owner chooses, log to decisions engine via gateway when available

## A4 handling

Destructive / irreversible / send-as-owner options must include:

```markdown
⚠ A4 — Requires explicit owner approval before execution
- Preview: [exact effect]
- Rollback: [possible | impossible | partial]
- Policy hook: approval_required expected
```

Never execute A4 from decision-support output alone.

## A5 handling

Options that imply disabling audit, truth, or security hooks are **removed**, not listed as viable. Note why if the owner asked about them.

## Output template

```markdown
## Decision: [title]

**Context verified:** yes/no — [gaps]

| Option | Summary | Peak class | Reversible? |
|--------|---------|------------|-------------|

### Recommendation
[option id] — because [truth-aligned reasoning]

### If you choose [option]
- Preconditions: ...
- Evidence to capture before/after: ...
```

## Fail closed

Insufficient truth or grants → present options marked `blocked` with restoration steps, not faux-ready plans.
