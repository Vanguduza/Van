# OpenMuse → VAN Convergence Development Pack — Revision 1.0

**Status:** CANONICAL DEVELOPMENT AUTHORITY — OPENMUSE CONVERGENCE SCOPE  
**Target repository:** `Vanguduza/Van`  
**VAN baseline:** `12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af`  
**Pinned upstream:** `CopilotKit/openmuse@34b15bc80340e582fb8c25573646cfb0bbc5184d`  
**Upstream licence:** MIT  
**Date:** 2026-09-27

## 0. Authority

This pack is canonical for OpenMuse→VAN convergence only. It is subordinate to:

1. `docs/SECURITY_POLICY.md`
2. `docs/PROJECT_TRUTH_PROTOCOL.md`
3. `docs/project-state/AUTHORITY_MAP.yaml` and its owning documents
4. existing browser, Google, trading, Android-security and deployment authorities.

A conflict with a higher authority is a defect in this pack; workers must fail closed rather than choose whichever text is easier to implement.

## 1. Mission

Absorb OpenMuse's strongest proven product capabilities without creating a second agent, authority plane, memory authority, attention plane, or execution identity.

Convergence is complete only when a capability is owner-reachable, authority-gated, restart-safe where claimed, evidence-linked, tested, provenance-tracked and honest about any remaining live/device/provider gate.

## 2. Non-negotiable invariants

- Hermes profile `van` remains VAN's sole agent runtime.
- The VAN Gateway remains upstream of every mutation.
- External PDFs, email, web, CSV and provider output are data, never authority.
- Existing A1–A5 classification and approval policy remains authoritative.
- No document/computer/browser/watch path can automate a payment.
- Source documents are immutable by default; mutations produce a new artifact.
- Historical evidence is immutable and separate from mutable live-session state.
- New work attaches to existing `command_id`, `mission_id`, `execution_id` semantics.
- Watches and Suggestions emit through VAN Attention; no second alert inbox.
- VAN memory remains the only canonical owner-memory authority.
- Missing workers/providers refuse before writing misleading PENDING work.
- Unknown mutation outcome is terminal until reconciled; never blind-retry.
- OpenMuse-derived code may sit below VAN authority, never above it.

## 3. Pinned upstream references

| OpenMuse path | Use |
|---|---|
| `docs/FEATURES.md` | implemented feature inventory |
| `docs/VERIFICATION.md` | proven behavior/limitations |
| `ROADMAP.md` | future ideas only |
| `packages/integrations/src/pdf.ts` | PDF/AcroForm reference |
| `packages/integrations/src/google.ts` | Gmail MIME/attachments + Calendar versioning |
| `apps/server/src/computer.ts` | computer/workspace reference |
| `apps/server/src/engine/worker.ts` | lease/recovery reference |
| `apps/server/src/actions.ts` | reviewed-action replay/uncertainty reference |
| `apps/server/src/browser.ts`, `apps/worker/*` | browser runtime/egress reference |
| `docs/RICH-THREADS.md` | thread UX/state reference |
| `apps/mobile/src/agent-ui.tsx` | rich result presentation |

Every copied or meaningfully adapted source file must identify upstream repository, commit, path, licence, VAN destination and adaptation decision.

## 4. Capability decisions

| Capability | VAN state | Disposition |
|---|---|---|
| chat/delegated work | VAN_PARTIAL | ADAPT_UX |
| durable execution | VAN_SUPERIOR | RETAIN_VAN |
| ideas | VAN_PARTIAL | ADAPT as Suggestion under Attention |
| owner goals | VAN_MISSING_PRODUCT_OBJECT | ADAPT |
| recurring watches | VAN_PARTIAL | ADAPT |
| browser authority/takeover | VAN_SUPERIOR | RETAIN_VAN |
| browser profile/runtime hardening | VAN_PARTIAL_RUNTIME | ADAPT |
| browser exact-IP egress | MIXED | ADOPT_HARDEN |
| Linux computer | VAN_MISSING_RUNTIME | ADAPT behind ComputerInteractionFabric |
| persistent workspace | VAN_PARTIAL | ADAPT |
| PDF inspect/fill | VAN_MISSING | ADAPT_EXPAND as Document Fabric |
| PDF viewer/workflow | VAN_MISSING | ADAPT |
| Gmail basic mutation | VAN_IMPLEMENTED | RETAIN_AUTHORITY |
| Gmail MIME/thread/attachments | VAN_WEAKER | ADAPT |
| Calendar agenda/reschedule | VAN_IMPLEMENTED | RETAIN |
| Calendar full CRUD/versioning | VAN_WEAKER | ADAPT |
| Drive/Contacts/Tasks | VAN_SUPERIOR_BREADTH | RETAIN_VAN |
| memory | VAN_SUPERIOR | RETAIN_VAN |
| notifications/attention | VAN_SUPERIOR | RETAIN_VAN |
| connector catalogue | VAN_SUPERIOR | RETAIN_VAN |
| generated results | VAN_PARTIAL | ADAPT as OwnerArtifact |
| rich threads | VAN_PARTIAL | REIMPLEMENT_SELF_HOSTED |
| OpenBot peer-agent path | NOT_REQUIRED | REJECT |
| personal finance CSV | VAN_MISSING | OPTIONAL_ADAPT |

## 5. Canonical target architecture

```text
Owner Android
   │
   ▼
VAN Gateway ── Project Truth / Context / Memory
   │         ├─ Attention / Decisions / Approval
   │         ├─ Mission / ActionRuntime / Verification
   │         └─ OwnerArtifact projection
   │
   └── Hermes profile van
          │
          ├── Browser Fabric ── adapted Chromium/runtime primitives
          ├── ComputerInteractionFabric ── subordinate worker
          └── Document Fabric ── PDF/OCR/document adapters
                    │
                    ▼
              evidence / receipts
                    │
                    ▼
             OwnerArtifact UI
```

## 6. Work packages

### OMV-005 — Owner Artifact Projection

Create a non-authoritative presentation/retrieval projection over canonical evidence.

Required fields: `artifact_id`, owner/project/command/mission/execution links, kind, title, summary, MIME metadata, canonical source type/id/digest, content/preview refs, evidence refs, timestamps and sensitivity.

Rules: no secret bytes in rows; no mutation authority; provenance mandatory; canonical source digest immutable.

### OMV-001 — Document Fabric

First complete E2E capability.

Required operations: import, inspect, schema extraction, missing-value request, proposal, fill supported PDF fields, render/preview, compare source/output digests, share/export, and later OCR/redaction/annotation/signature adapters.

PDF v1 accepts ordinary AcroForm PDFs, rejects encrypted PDFs, XFA, unsupported field types, oversized/page-count inputs, and embedded action execution. Text and checkbox fields are required. Source bytes are immutable. Output is a new artifact.

### OMV-002 — Computer Worker

Implement a real subordinate worker behind existing `ComputerInteractionFabric`.

Required: non-root workspace, bounded typed operations, persistent workspace, quotas, command/output receipts, timeout, crash recovery, lost-lease/generation fencing, no Docker socket, no VAN root/owner secrets, no arbitrary authority expansion. Registration is disabled until health/isolation tests pass.

### OMV-007 — Google Depth Expansion

Keep VAN's authority/readback model; extend provider semantics.

Gmail: complete threads, MIME decoding, attachments, reply headers, bounded attachment size and Document Fabric handoff.

Calendar: create/update/delete, ETag review binding, `If-Match`, timezone/DST correctness, and explicit outcome-unknown on ambiguous writes.

### OMV-003 — Goals & Watches

Add a long-lived owner Goal object distinct from Mission. Goals have milestones, status, priority and linked mission IDs.

Add Watch objects for periodic read-only conditions (page change, availability, threshold/difference). Watches run under existing scheduler/automation/browser authority, use retry/backoff, emit deduplicated Attention, pause after repeated failure, and never mint mutation authority.

### OMV-004 — Evidence-backed Suggestions

Add Suggestion object with source evidence, rationale, proposed owner prompt/action and `NEW|ACCEPTED|EDITED|DISMISSED`.

Acceptance creates a fresh owner intent; it never executes the suggested mutation directly.

### OMV-006 — Rich Conversation Store

Self-host main/side threads, rename/archive/restore/replay, per-thread draft/queued follow-up state and artifact references. Conversation history is never execution truth and replay never re-executes terminal actions.

### OMV-008 — Browser Runtime Harvest

Retain VAN browser authority. Adapt persistent Playwright profile lifecycle, exact-IP egress mediation, immutable evidence-vs-live-session identity, download failure persistence and worker unavailable semantics. Screenshot mode is evidence/degraded fallback, not a WebRTC replacement.

### OMV-009 — Durable Regression Harvest

Add regressions for:
- completed reviewed action never becoming pending on replay;
- evidence identity never becoming session identity;
- worker offline never showing stale READY;
- agent/worker step-limit stop surfaced explicitly;
- repeated failure-streak dedupe resets after recovery;
- lost worker lease/generation cannot checkpoint completion;
- unknown external mutation result is never blindly retried.

### OMV-010 — Personal Finance

Optional only. Deterministic CSV parsing, exact cents, no inferred currency conversion, bounded file size and separate semantics from VATI/trading.

## 7. Execution order

```text
Wave 0: provenance + OMV-009 regression lock
Wave 1: OMV-005 Artifact Projection
Wave 2: OMV-001 Document Fabric + OMV-002 Computer Worker
Wave 3: OMV-008 Browser runtime + OMV-007 Google depth
Wave 4: OMV-003 Goals/Watches + OMV-004 Suggestions
Wave 5: OMV-006 Rich Conversation Store
Wave 6: OMV-010 optional finance
```

A later wave may start only when its dependency contracts are green.

## 8. Required repository placement

```text
docs/OPENMUSE_VAN_CONVERGENCE_DEVELOPMENT_PACK_REV_1.md
docs/project-state/OPENMUSE_VAN_CONVERGENCE_MATRIX_REV_1.json
docs/project-state/OPENMUSE_VAN_UPSTREAM_PROVENANCE_REV_1.json
docs/project-state/OPENMUSE_VAN_EXECUTION_GRAPH_REV_1.json

backend/van_gateway/artifacts/
backend/van_gateway/documents/
backend/van_gateway/goals/
backend/van_gateway/suggestions/
backend/van_gateway/conversations/
backend/van_gateway/personal_finance/
backend/van_gateway/computer_use/ (existing fabric, new worker)
backend/tests/test_owner_artifacts.py
backend/tests/test_document_fabric.py
backend/tests/test_goals_watches.py
backend/tests/test_suggestions.py
backend/tests/test_conversation_store.py
backend/tests/test_openmuse_regressions.py
```

## 9. Acceptance scenarios

1. **PDF safe fill** — import AcroForm, inspect fields, fill into a new copy, source hash unchanged, output hash/evidence recorded.
2. **Unsupported PDF** — encrypted/XFA/unsupported type returns explicit refusal and no false-success artifact.
3. **Gmail attachment round trip** — full thread → attachment → Document Fabric → reviewed reply → verified send receipt.
4. **Stale Calendar review** — changed ETag causes refusal; no blind overwrite.
5. **Computer crash** — old worker generation cannot publish completion after restart.
6. **Suggestion boundary** — suggestion cannot execute until accepted into fresh owner intent and independently gated.
7. **Watch streak** — one alert per failure streak; new streak after recovery may alert again.
8. **Conversation replay** — restore/archive/replay renders artifacts but does not replay mutations.
9. **Browser evidence** — historical capture remains immutable while live session moves elsewhere.
10. **Degraded truth** — disabled Document/Computer/Browser/Google capability reports exactly what is unavailable.

## 10. CI gates

The convergence validator must enforce pinned upstream SHA, package IDs, provenance rows, authority invariants, exhaustive artifact kinds/renderers, migration/state-map exhaustiveness and separation of repository proof from live certification.

Focused convergence tests do not replace existing broad backend/contracts/Hermes/services/Android/trading suites.

## 11. Definition of director state

OMV-001 through OMV-009 are repository-complete, every remaining live gate is explicitly external with no hidden repository work, owner surfaces are reachable, provenance is complete, broad suites are green, and no duplicate agent/memory/attention/execution authority exists.

The target state is not “VAN contains OpenMuse.” It is:

> VAN has absorbed the useful proven OpenMuse capabilities into one coherent owner-assistant architecture while retaining one authority model, one execution identity chain, one verification model and one owner-facing product truth.
