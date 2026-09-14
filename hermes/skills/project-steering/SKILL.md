---
name: project-steering
description: >-
  Aligns work across registered VAN projects using Project Truth, implementation
  ledger, and owner priorities. Use when steering roadmaps, cross-repo coordination,
  truth drift detection, or prioritizing dial/dde/gtr/goat/aeci/van work.
---

# Project Steering

## Authority

Project Truth outranks chat memory. Load truth before recommending or executing mutations.

Authority order (summary): owner-signed instruction → Project Truth → capability grants → deterministic state → Hermes memory → chat → untrusted content. Full order in `hermes/profile/van/SOUL.md` and `docs/PROJECT_TRUTH_PROTOCOL.md`.

## Registered projects

From `registries/projects.json`:

| id | Notes |
|---|---|
| van | truth: `docs/PROJECT_TRUTH_PROTOCOL.md` |
| dial, dde, gtr, goat, aeci | resolve `truth_path` when set; use `repo_hint` for clone context |

## Steering workflow

1. **Identify project_id** — never assume; ask if ambiguous
2. **Load Project Truth** — read canonical truth file at pinned SHA when mutating
3. **Compare request vs truth** — flag conflicts explicitly
4. **Check implementation ledger** (`docs/IMPLEMENTATION_LEDGER.md` for van) — distinguish IMPLEMENTED / PARTIAL / MISSING / EXTERNAL GATE
5. **Propose plan** with ordered steps, action classes, and evidence requirements
6. **Mutate only** after grants + policy hook + mutation protocol (before/after evidence)

## Truth drift detection

After repo operations:

- Detect unauthorized changes to truth protocol files
- Detect stale truth (SHA mismatch vs owner expectation)
- Surface in steering output; block further mutations until reconciled

## Output template

```markdown
## Steering — [project_id]

**Truth source:** [path] @ [sha or UNVERIFIED]
**Request alignment:** aligned | conflict | insufficient evidence

### Recommended sequence
1. [step] — A[n] — evidence: [...]

### Blockers
- ...

### Will not do (fail closed)
- ...
```

## Fail closed

Without truth load or SHA evidence, do not claim repo state or mark tasks complete.
