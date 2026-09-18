# VAN Rev 3.1 Browser Boundary Escalation × Android Control Surface Reconciliation Amendment

**Date:** 2026-09-18  
**Repository:** `Vanguduza/Van`  
**Authority branch:** `gpt/rev3-1-full-knowledge-runtime-20260917`  
**Parent reconciliation authority:** `docs/project-state/VAN_REV31_KNOWLEDGE_BROWSER_RECONCILIATION_HANDOFF_2026-09-18.md`

## 1. Decision

A browser task discovering that the desired result requires work outside its currently authorized task boundary MUST NOT be treated as an automatic terminal failure.

The canonical behavior is a governed, resumable boundary-escalation protocol.

The browser agent/harness is execution transport only. It may detect a boundary conflict and propose the minimum required extension, but it may not self-authorize that extension.

Authority remains:

```text
Owner intent
 -> VAN/Hermes planning
 -> Gateway CommandAuthority / ActionRuntime
 -> Browser Harness deterministic control
 -> Stagehand semantic interaction where required
 -> postcondition/readback verification
 -> gateway owner-visible completion
```

## 2. Boundary classification

Every attempted boundary crossing MUST be classified before any out-of-envelope action occurs.

### 2.1 BOUNDED_SAFE_EXTENSION

A deterministic extension that remains inside the already-authorized action class, principal, domain policy, credential profile, project scope and mutation envelope.

Examples:
- following pagination on an already admitted site;
- opening a detail page required to complete an authorized read task;
- retrying an idempotent read after a transient browser error;
- handling a harmless interstitial without changing account state.

This MAY continue automatically if the browser policy explicitly permits it and an audit event is emitted.

### 2.2 OWNER_EXTENSION_REQUIRED

The required next step is useful and plausibly intended, but exceeds one or more current authority dimensions.

Examples:
- a new domain must be admitted;
- authentication is required when the task was public-only;
- a read task now requires mutation;
- a download/upload is newly required;
- a new external account or provider must be connected;
- the action class would increase;
- an owner choice is required between materially different paths;
- a CAPTCHA, consent, legal acknowledgement or irreversible provider step requires human action.

The task MUST transition to `WAITING_FOR_OWNER`, preserving browser/session/workflow state where safe.

A structured owner decision MUST be created through the existing gateway `DecisionService`, and an attention record MUST be produced through `AttentionEngine`.

### 2.3 POLICY_FORBIDDEN

The discovered step violates a hard policy or locked authority boundary.

Examples:
- broker live-order submission through generic Browser Harness;
- export of raw owner cookies or credentials;
- arbitrary JavaScript as a normal browser interface;
- cloud metadata access;
- bypass of A3/A4 authority;
- external content self-promoting into Owner Facts or Project Truth.

The task MUST stop the prohibited path immediately, emit an explicit policy-denied event and surface the reason to VAN/Hermes/owner. It MUST NOT offer an approval button that could override a hard prohibition.

### 2.4 AMBIGUOUS_OR_UNSAFE

The system cannot determine whether the discovered extension is within policy or cannot prove the safety/correlation required for continuation.

The workflow MUST fail closed into `WAITING_FOR_OWNER` or `BLOCKED_UNSAFE`, never silently broaden scope.

## 3. Required browser workflow states

The browser/runtime contract SHOULD support at least:

```text
PLANNED
AUTHORIZED
RUNNING
VERIFYING
WAITING_FOR_OWNER
RESUME_AUTHORIZED
BLOCKED_POLICY
BLOCKED_UNSAFE
VERIFIED_SUCCESS
VERIFICATION_FAILED
FAILED
CANCELLED
EXPIRED
```

`WAITING_FOR_OWNER` is non-terminal.

A task entering `WAITING_FOR_OWNER` MUST retain enough durable state to resume deterministically:
- task/workflow id;
- owner command id and immutable context snapshot hash;
- current action class;
- requested extension;
- reason code;
- originating URL/domain and browser profile id;
- safe browser session lease reference, never raw cookies;
- completed step ledger;
- pending step;
- idempotency key;
- expiry/deadline;
- screenshot/DOM/evidence references where permitted;
- proposed continuation plan;
- required approval class;
- rollback/compensation notes if applicable.

## 4. Escalation payload

The browser runtime MUST emit a typed escalation request. Minimum fields:

```json
{
  "task_id": "...",
  "command_id": "...",
  "project_id": "...",
  "boundary_type": "OWNER_EXTENSION_REQUIRED",
  "reason_code": "NEW_DOMAIN_REQUIRED",
  "current_scope": {},
  "requested_scope_delta": {},
  "current_action_class": "A2",
  "required_action_class": "A3",
  "summary": "...",
  "why_required": "...",
  "risk_summary": "...",
  "pending_step": "...",
  "evidence_refs": [],
  "session_lease_ref": "...",
  "idempotency_key": "...",
  "expires_at_unix": 0
}
```

No secrets, cookies, raw credentials or hidden provider tokens may enter this payload.

## 5. Owner/Hermes escalation path

Canonical flow:

```text
Browser Harness detects boundary condition
 -> browser policy classifier
 -> safe extension? continue + audit
 -> forbidden? block + attention
 -> owner extension required?
      persist resumable checkpoint
      create DecisionService record
      create AttentionEngine item
      notify VAN Android
      optionally notify owner channels governed by notification policy
      Hermes receives structured escalation context
      owner reviews
      gateway resolves decision
      if approved:
          create a NEW authorization for the delta
          bind it to the original task/workflow
          resume from checkpoint
      if rejected/expired:
          terminate or replan without the denied delta
```

Approval MUST never mutate the original signed owner-intent envelope in place. The newly authorized scope delta must be separately represented and auditable.

## 6. Reuse existing VAN gateway capabilities

The current Rev 3.1 branch already contains:
- `DecisionService` for first-class Hermes/owner escalations;
- `AttentionEngine` with BLOCKER/URGENT/FOLLOW_UP handling;
- Android `Decisions`, `Tasks`, `Activity`, `Systems` and `Connections` modules;
- Android gateway calls for `/v1/decisions`, `/v1/attention` and events;
- signed owner command dispatch;
- A4 biometric approval handling.

Browser escalation MUST plug into these existing surfaces rather than creating an independent browser approval authority.

## 7. Android product requirement

The current generic Decisions screen is insufficient for a production browser-control experience.

Add a dedicated **Browser & Automation** management area in VAN Command Centre, while retaining generic Decisions for cross-system governance.

Recommended module structure:

### 7.1 Browser Overview
- live Browser Harness status;
- Stagehand status;
- active sessions;
- authenticated profile readiness;
- current task count;
- tasks waiting for owner;
- policy denials;
- recent verification success/failure;
- quick link to browser policies/domains.

### 7.2 Active Browser Tasks
For each task:
- objective;
- project/context;
- current site/domain;
- state;
- current step;
- elapsed time;
- progress/evidence timeline;
- requested action class;
- browser profile;
- resumability status.

Owner actions, when allowed:
- pause;
- resume;
- cancel;
- inspect;
- replan through Hermes;
- open escalation.

### 7.3 Escalation Detail
A rich interactive screen for `WAITING_FOR_OWNER` records:
- what VAN was asked to achieve;
- what was completed;
- exact boundary discovered;
- why crossing it is necessary;
- requested scope delta;
- security/risk implications;
- target domain/provider;
- action-class change if any;
- screenshots/evidence references where policy permits;
- consequences of approve/reject;
- alternative safe paths suggested by Hermes.

Actions:
- Approve once;
- Approve for this task scope;
- Reject;
- Ask VAN/Hermes to replan;
- Cancel task;
- for eligible configuration cases, route to policy/domain management.

A4-equivalent sensitive approval MUST retain biometric proof and existing gateway challenge/signature semantics.

### 7.4 Browser Sessions
- active/idle session leases;
- profile type: public research vs authenticated owner;
- associated task;
- domain;
- last activity;
- expiration;
- safe terminate session control.

Never display or export raw cookies/tokens.

### 7.5 Domain & Capability Policy
Read-first UI for:
- admitted domains;
- observe/extract/mutate/download permissions;
- discovered-but-unadmitted domains;
- hard prohibitions;
- authentication requirement;
- mutation authority.

Changes are governed actions, not direct local preference toggles.

### 7.6 Browser Evidence
- screenshots where allowed;
- DOM/readback receipts;
- downloaded evidence artifacts;
- verification records;
- source URLs;
- correlation ids;
- timestamps;
- provider/task lineage.

### 7.7 Automation / n8n
Because Browser Harness, Stagehand and self-hosted n8n form the wider automation fabric, VAN Android SHOULD also expose:
- n8n runtime health;
- admitted workflows;
- running/executing workflows;
- failed/retrying executions;
- workflows waiting on owner;
- resource policy state;
- workflow evidence;
- explicit link from a browser escalation to the parent Temporal/n8n/Hermes workflow.

This screen is management/observability, not an unrestricted n8n editor.

## 8. Notification behavior

Owner escalation should be visible in-app and may additionally produce Android notifications.

Notification requirements:
- BLOCKER for a currently blocked owner-requested task;
- URGENT only when the underlying task is truly time-critical;
- dedupe by decision/task id;
- never expose secrets in notification text;
- tapping notification opens the exact Escalation Detail screen;
- quiet-hours policy applies except for permitted urgent/blocker behavior;
- resolution automatically clears/updates the linked attention item.

## 9. Hermes responsibilities

Hermes should receive a structured escalation event and may:
- explain the boundary in owner-friendly language;
- propose safer alternatives;
- reduce requested scope;
- replan around the blocked step;
- recommend whether a new tool/provider path is preferable.

Hermes MUST NOT:
- approve on the owner's behalf;
- widen signed scope silently;
- convert a hard policy prohibition into an approvable decision;
- claim task completion while the browser workflow is waiting.

## 10. Stagehand / Browser Harness responsibilities

Browser Harness owns deterministic session/process lifecycle, policy enforcement, checkpoints, retries, observability and resumability.

Stagehand is used only where semantic browser understanding/action materially helps. Stagehand does not own authority.

Direct Playwright currently used by personal NotebookLM MUST be refactored behind the canonical Browser Harness boundary while preserving:
- managed persistent owner profile;
- no raw cookie export;
- Notebook provider idempotency;
- DOM/readback verification;
- ActionRuntime completion semantics.

## 11. Temporal / n8n integration

Long-running browser work MUST be resumable above the browser process.

Recommended separation:
- Temporal: durable mission/workflow state, waits, retries, long-running coordination;
- n8n: admitted automation workflows/integration fabric;
- Browser Harness: deterministic browser runtime;
- Stagehand: semantic page interaction;
- Hermes: planning/replanning;
- Gateway: authority and owner-visible verification truth.

A browser boundary escalation should therefore suspend the durable workflow rather than destroy it.

## 12. Required API additions

Reconciliation should add or formalize typed endpoints equivalent to:

```text
GET  /v1/browser/status
GET  /v1/browser/tasks
GET  /v1/browser/tasks/{id}
POST /v1/browser/tasks/{id}/pause
POST /v1/browser/tasks/{id}/cancel
GET  /v1/browser/sessions
POST /v1/browser/sessions/{id}/terminate
GET  /v1/browser/policies
GET  /v1/browser/evidence/{task_id}
GET  /v1/browser/escalations
GET  /v1/browser/escalations/{id}
POST /v1/browser/escalations/{id}/resolve
```

Where an escalation is also represented by the canonical `DecisionService`, IDs/references must be cross-linked rather than duplicated as competing sources of truth.

## 13. Required tests

At minimum:

1. read task encountering a new page on same admitted domain continues as bounded safe extension;
2. new unadmitted domain creates `WAITING_FOR_OWNER`, decision and attention records;
3. mutation discovered during read-only task cannot execute before new authorization;
4. action-class elevation cannot be self-approved by browser/Stagehand/Hermes;
5. hard prohibited operation never surfaces as an approvable action;
6. approval creates a new authority record and resumes the original workflow checkpoint;
7. rejection does not lose completed evidence and terminates/replans deterministically;
8. expired escalation cannot be replayed;
9. duplicate escalation retries dedupe to the same decision/task;
10. raw cookies/credentials never appear in payloads, logs, Android responses or model context;
11. Android detail screen reflects gateway truth, not optimistic local state;
12. notification tap opens the matching escalation;
13. NotebookLM browser transport preserves provider idempotency/readback after Browser Harness refactor;
14. voice and typed browser commands converge on the same authority/escalation path;
15. process restart while waiting for owner restores the task and session/checkpoint safely.

## 14. Reconciliation consequence for current WIP branches

The trading/bootstrap branches containing Browser Harness/Stagehand foundations are far behind the current certified Rev 3.1 lineage and MUST NOT be merged wholesale.

Their browser/automation assets should be transplanted or semantically reconciled onto the current Rev 3.1 lineage.

The currently observed browser foundation already has the correct directional controls:
- Stagehand pinned;
- Playwright pinned;
- managed browser profiles;
- raw cookie/credential export forbidden;
- mutations deny-until-admitted;
- A3/A4 discovery requires reauthorization;
- broker live-order submission prohibited.

The missing production behavior is chiefly the durable escalation/resume protocol and the comprehensive owner-facing Android management surface defined above.

## 15. Acceptance rule

A browser task is not considered robust merely because it can fail safely.

Production acceptance requires that a legitimate, useful boundary overrun can:
1. stop before unauthorized action;
2. preserve progress;
3. explain the required extension;
4. reach Hermes/owner through VAN;
5. be inspected and managed on Android;
6. receive a new, explicit authorization if approved;
7. resume deterministically;
8. verify the final postcondition;
9. retain complete provenance.

This amendment is normative for the browser reconciliation work.
