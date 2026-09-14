---
name: infrastructure-diagnostics
description: >-
  Diagnoses Hermes host, Van gateway, MCP servers, and profile install health
  in read-only mode unless explicit grants allow remediation. Use for doctor
  checks, connectivity failures, or is VAN/Hermes up questions.
---

# Infrastructure Diagnostics

## Scope

Read-only by default. Remediation scripts (install, restart) require owner direction and appropriate grants — not silent self-healing that hides failures.

## Diagnostic sequence

1. **Profile layout** — run or reason about `tools/hermes/doctor_van_profile.sh` expectations
2. **Policy hook** — import `van_policy_hook`; run self-test patterns from `hermes/policy/tests/`
3. **Gateway** — health endpoint reachability (when host known)
4. **MCP** — servers listed in `hermes/mcp/README.md`; report configured vs reachable
5. **Hermes execution** — profile `van` loaded, not alias profile
6. **Secrets** — verify no tokens in env dumps presented to owner (redact)

## Report template

```markdown
## Infrastructure diagnostics — [timestamp]

| Component | Status | Evidence |
|-----------|--------|----------|

### Fail closed items
- ...

### Remediation (requires approval)
1. [action] — class A[n] — command: ...
```

## Commands (Hermes host)

```bash
# Read-only verification
./tools/hermes/doctor_van_profile.sh

# Install/refresh (mutating — owner directed)
./tools/hermes/install_van_profile.sh
```

## Fail closed

- Do not claim "all systems green" without evidence
- Do not paste secret values in diagnostic output
- SSH/host unreachable → report EXTERNAL GATE, not simulated uptime
