# VAN-AMEND-SECURITY-POLICY-002 — scoped privileged control credentials

One decision per file. This was first appended to VAN-AMEND-SECURITY-POLICY-001, which
is SIGNED; a second PENDING block in a signed file made the governance reader report
the whole decision as pending and blocked automation activation. That reader was right,
and the fix is to separate the decisions rather than to weaken the reader.

**Status: PENDING.** `docs/SECURITY_POLICY.md` is a locked authority and this text does not
belong in it until the owner approves. It is recorded here because the code has already
changed and the locked document is now behind the system it describes — which is a smaller
problem than silently editing a document the owner locked, and a much smaller one than
leaving the credential root in place while waiting.

### What the audit found

`X-Van-Internal-Token` alone minted a pairing ticket. `POST /v1/devices/pair` then required
no authentication at all and returned both the ingress bearer and a device access token, so
one string produced owner-device authority. The same token reached Project Truth injection,
device revocation, Google connect and revoke, the trading halt, every automation route,
browser mutations and context scope delete. The Hermes MCP shim reads it from
`~/.config/van/gateway.env`, so a model-driven runtime holds it.

Separately, a failed internal check fell through to ingress plus device authentication, so a
route declared Hermes-only was reachable with an owner device token.

### What the code now does

Privileged control is **scoped**. A route belongs to exactly one control scope and a
credential carries a set of them:

- `VAN_INTERNAL_CONTROL_TOKEN` — the legacy single token, which now carries every scope
  **except** `device_enrolment`.
- `VAN_INTERNAL_CONTROL_SCOPED_TOKENS` — per-purpose credentials, `scope,scope:token; …`.
  Scopes: `runtime`, `automation`, `browser`, `google`, `trading`, `projects`, `missions`,
  `understanding`, `device_enrolment`.
- `VAN_DEVICE_ENROLMENT_TOKEN` — the only credential that can mint a pairing ticket, enrol a
  device or revoke one. It is the only path to owner-device authority, and the Hermes MCP
  shim does not read it. Empty means device enrolment is unreachable.

Two properties matter more than the split itself. A failed internal check is **terminal**: an
internal-control route answers 403 naming the scope it needed and never falls back to
owner-device authentication. And an owner device token is never an answer to a privileged
control route, however valid it is.

### What the owner is being asked to decide

1. Whether the scope list above is the right partition, or whether any two scopes should be
   merged or split further.
2. Whether `device_enrolment` should stay out of the Hermes runtime's reach permanently, or
   whether a time-boxed grant is wanted for setup.
3. Whether this text should replace the corresponding paragraph in `docs/SECURITY_POLICY.md`,
   which would change that file's locked hash and require re-pinning it in
   `PROJECT_CANONICAL_STATE.json` and `tests/contracts/test_automation_browser_governance.py`.

```yaml
owner_signature_status: PENDING
owner_signature_evidence_ref: null
```
