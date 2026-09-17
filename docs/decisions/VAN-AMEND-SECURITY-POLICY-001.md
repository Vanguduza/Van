# VAN-AMEND-SECURITY-POLICY-001 — Automation & Browser Fabric amendment package

**Status:** `PENDING_OWNER`. This is a **proposal**, not an amendment.
**Target authority:** `docs/SECURITY_POLICY.md` — a locked authority under
`PROJECT_CANONICAL_STATE.json → canonical_state.locked_authorities`.
**Source:** Rev 1.3 §367, activation gate §368.
**Created:** 2026-09-17

---

## Why this exists

`PROJECT_CANONICAL_STATE.json` sets `agent_self_authorization_forbidden: true` and
`owner_instruction_is_project_truth_authority: true`. The Automation and Browser Fabric introduces a
new credential plane, a new ingress, a new egress surface and browser session secrets — all governed
by the locked Security Policy. An implementation agent therefore **proposes** the amendment and
builds fail-closed code behind disabled gates; it does not edit the policy body.

`docs/SECURITY_POLICY.md` is unchanged by this branch. Verified by
`tests/contracts/test_security_policy_amendment_proposal.py`.

## Activation gate (§368)

```text
SECURITY_AMENDMENT_PROPOSED     <- this document
  ↓
OWNER_APPROVED
  ↓
PROJECT_TRUTH_RECORDED
  ↓
CI CONTRACT TESTS
  ↓
LIVE CERTIFICATION
  ↓
READY
```

Until `OWNER_APPROVED`, every runtime flag named in §6 below stays disabled and every external gate
stays `PENDING_LIVE`.

---

## Proposed amendments

Each block is proposed authority text for insertion into `docs/SECURITY_POLICY.md`. Section names
match the existing document's structure.

### A1 — Automation Fabric boundary (new section, after *Hermes execution boundary*)

> n8n is a subordinate integration and workflow runtime. n8n never becomes an owner principal,
> Project Truth authority, trading Risk Authority, broker order sender, or Hermes peer agent.
> Consequential n8n effects require an existing owner command authority or a standing automation
> authority derived from an owner-authorized command and enforced by the VAN Gateway.

*Relates to:* §367.1. *Enforced by:* `automation/policy.py`, `command/standing.py`,
`tests/contracts/test_automation_authority_boundary.py`.

### A2 — Credential isolation (extends *Capability broker* and *Secrets*)

> n8n may hold only explicitly approved integration credentials classified for bounded read/write
> integration use. Owner signing keys, device HMAC secrets, VAN internal/root tokens, Project Truth
> authority credentials, broker execution credentials, VATI authority-store credentials and other
> root/financial authority secrets are prohibited from the n8n credential store.

*Relates to:* §367.2. *Enforced by:* `automation/credentials.py` credential classes C0–C4 from
`config/automation/credentials.yaml.example`; `test_n8n_cannot_hold_c0_c1_credentials`.

### A3 — Browser session sovereignty (extends *Secrets*)

> Browser cookies, localStorage/sessionStorage secrets, CDP bearer material, login sessions, OTPs
> and browser profile secrets are SECRET. They remain inside the Browser Session Broker / managed
> browser profile and are referenced by opaque aliases. They may not be copied into Hermes prompts,
> n8n workflow JSON, Stagehand model prompts, VEKL/VTIL, evidence text, logs or workflow artifacts.

*Relates to:* §367.3. *Enforced by:* `browser/policy.py` secret-reference rule,
`browser/evidence.py` redaction, `test_browser_secrets_never_leave_broker`.

### A4 — External egress (new section)

> Automation and browser egress is default-off per capability/domain. Gateway policy must
> explicitly authorize domains, credential plane, method/effect class and sensitivity. External
> content remains UNTRUSTED_EXTERNAL and cannot increase authority.

*Relates to:* §367.4. *Enforced by:* `automation/policy.py` domain policy + SSRF guard;
`VAN_AUTOMATION_EGRESS_ENABLED` defaults false; `test_egress_disabled_blocks_workflow_http`.

### A5 — Webhook ingress (new section)

> External webhooks are untrusted events, never owner commands. Provider signature/HMAC/mTLS/OAuth
> validation, replay protection and schema validation occur before an event may enter the VAN event
> fabric.

*Relates to:* §367.5. *Enforced by:* `automation/events.py` validation pipeline;
`VAN_AUTOMATION_INGRESS_ENABLED` defaults false; `test_external_event_cannot_become_owner_explicit`.

### A6 — Generated workflows (new section)

> Generated WorkflowIR and compiled n8n workflows are executable candidates, not authority.
> Generation cannot create a new privilege, credential, domain allowance, action-class exception,
> standing grant or Project Truth decision.

*Relates to:* §367.6. *Enforced by:* `automation/validator.py`, `automation/admission.py`,
`test_generation_cannot_create_privilege`.

### A7 — Browser workers (new section)

> Stagehand and Browser Harness are subordinate browser workers. They receive task-scoped grants
> and may not independently create VAN commands, elevate action classes, access owner signing
> secrets or place/modify/cancel broker trades.

*Relates to:* §367.7. *Enforced by:* `browser/policy.py`,
`test_stagehand_output_cannot_raise_action_class`.

---

## Interaction with the existing *Hermes execution boundary*

The existing locked text reads:

> Hermes profile `van` is the sole agent runtime. Android, the gateway, Gemini Live, Deep Research,
> Antigravity, Jules, Workspace Studio and other provider surfaces do not form independent VAN
> agent loops.

Stagehand tiers **L4 (act)** and **L5 (bounded agent)** place action selection inside the browser
worker. This proposal does **not** ask to weaken that sentence. Instead:

- Production default is capped at **L3** (observe → deterministic action), which keeps action
  selection deterministic and outside an agent loop. This is enforced in code, not prose, by
  `browser/policy.py` and `test_production_ladder_capped_at_l3`.
- L4/L5 remain available only behind `VAN_BROWSER_SEMANTIC_MAX_TIER`, which cannot exceed L3 unless
  the owner approves an explicit extension of the *Hermes execution boundary* section. That
  extension is deliberately **not** drafted here; it is a separate owner decision with its own
  reasoning, and Rev 1.3 §418's model-provider constraints would be its preconditions.

---

## What the owner is being asked to decide

1. Accept or amend the seven authority texts A1–A7.
2. Separately decide whether Stagehand L4/L5 is ever permitted in production, or whether VAN caps at
   L3 permanently.
3. Accept the three adoption decisions in `docs/decisions/VAN-ADOPT-*.yaml`, of which only n8n
   requires a licence-class decision (`SOURCE_AVAILABLE`).

On approval, record through the Project Truth process, then promote the stack-lock layers from
`trading/architecture/proposed/automation_browser_fabric_layers.json`.

```yaml
owner_signature_status: PENDING
owner_signed_at: null
owner_signature_evidence_ref: null
```
