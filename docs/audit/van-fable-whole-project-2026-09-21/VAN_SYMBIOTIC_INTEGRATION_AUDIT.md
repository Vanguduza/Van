# VAN symbiotic integration audit (Fable whole-project audit)

Audited commit `0067d55071342b963293d0724f5a1604d233d105`, 2026-09-21.

Question answered here: **does VAN, at this commit, operate as one persistent owner intelligence** — observe → contextualize → reason → decide whether attention/action is warranted → seek approval → act/delegate → observe outcome → reconcile → learn → improve — or as a set of correct but disconnected subsystems?

Verdict first: **the loop is structurally designed and eight of its ten links are implemented, but it does not close.** Three links are broken at this commit (memory write, learning read-back, proactive initiation), one is reachable only for Google work (act/delegate), and the loop has never been observed live end to end. VAN today is a well-governed *reactive* command executor with a real attention engine, not yet a persistent extension of the owner.

## Link-by-link

| # | Link | Implemented by | Status | Break |
|---|---|---|---|---|
| 1 | **Observe** (owner commands, voice, notifications, shares, Google reads, trading ledger, project truth) | Android voice/notification/share → `/v1/commands`, `/v1/context/ingest`; Google transport; trading read models; `sync_project_truth.py` | Works (device gate for the physical sensors) | Trading and news are observed by the owner surface, not by the reasoning layer (GAP-F-003) |
| 2 | **Contextualize** (canonical kernel, readiness, snapshot, digest, live-state refs, policy refs) | `context/service.py`, `command/context_requirements.py`, `orchestrator.py:640-721` | Mechanism works; content empty | No producer for CANONICAL_OWNER facts (GAP-F-001); every requirement non-blocking (GAP-F-019); Hermes dereference unobserved (QUAL-HERMES-03) |
| 3 | **Reason** (Hermes Sonnet 5; gateway deterministic critic/assumption kernel) | `hermes/bridge.py`, `reasoning/kernel.py`, `reasoning/critic.py`, `epistemics/*` | Works for delegated runs; critic route has no caller | Model reasoning is external and unmeasured; `/v1/runtime/reasoning/premises` unreachable (GAP-F-020) |
| 4 | **Decide whether attention/action is warranted** | `attention/engine.py` + `scoring.py` (one engine), `notifications/intelligence.py`, quiet hours, budget, dedupe, snooze/ack | Works and is proven | Only reactive: nothing decides to *initiate* (GAP-F-028); embodiment ignores URGENT (GAP-F-012) |
| 5 | **Seek approval** (A4 biometric ECDSA over server challenge; boundary escalations; decisions) | `approval/service.py`, `security/BiometricGate.kt`, `browser/api.py:289-626`, `decisions/*` | Works and is proven | Escalation producer (browser) is itself unreachable (GAP-F-006) |
| 6 | **Act / delegate** (Hermes run; typed actions with authority records; Google mutations with readback; browser/automation; trading via VATI) | `orchestrator.py`, `action/service.py`, `google/service.py:158-300`, `automation/dispatch.py`, `browser/api.py`, `trading/vati` | Works for Google and knowledge actions; VATI acts autonomously under its own authority | No Hermes tool for browser/automation/trading (GAP-F-006, GAP-F-003); trading.halt has no executor (GAP-F-005) |
| 7 | **Observe outcome** (Hermes `mission_result`; provider readbacks; ledger events; browser evidence) | `runtime_api.py:265-288`, `verification/observations.py`, `mission/binding.py` | Works in-process | Live Hermes callback unobserved (QUAL-HERMES-02) |
| 8 | **Reconcile** (VERIFYING → independent verifier → VERIFIED_SUCCESS/UNVERIFIABLE/FAILED; mission events to device; idempotent duplicate callbacks; expiry) | `mission/service.py:338-504`, `verification/production.py` | Works and is proven | Result lands in Activity/Missions, not the conversation (GAP-F-011) |
| 9 | **Learn / update state** (learning_outcomes, execution_strategies, intent_nodes, decision_fingerprints, symbiotic_growth; owner confirm/correct/reject; trading capsule_health) | `learning/feed.py`, `understanding/api.py`, `trading/vati` cycle | Written reliably | Owner-agent side is write-only (GAP-F-008); owner memory never written from conversation (GAP-F-001) |
| 10 | **Improve future behaviour** | `strategies_for`/`permitted_for`, `RelationshipCalibrationEngine`, `DomainTrust`/`ProactivePolicy`; trading `capsule_health` read-back | Trading: yes (bounded ≤ 1). Owner agent: no | Zero callers for the read-back functions (GAP-F-008); no proactive job (GAP-F-028) |

## The fourteen symbiosis capabilities from the brief

| Capability | Evidence | Verdict |
|---|---|---|
| Understand persistent owner goals | `intent_nodes` written from missions (`mission/service.py:180`), stale-marking job; shown at `/v1/understanding/intents` | Stored, not used in reasoning |
| Reason from historical context | `context_hot_capsule`, lexical/graph queries exist; kernel empty without GAP-F-001 | Mechanism only |
| Recognize unresolved matters | attention `list_open`, mission `expire_overdue`, WAITING_FOR_OWNER states | Yes (reactive) |
| Anticipate follow-ups without unauthorized action | `ProactivePolicyService.may_create()` never called | No |
| Identify contradictions | context `CONFLICTED` readiness; `/v1/context/conflicts`; `reasoning/critic.py` | Deterministic checks exist; critic unreachable |
| Challenge weak assumptions | assumption ledger blocks irreversible work (`runtime_api.py:183-219`) | Yes, on the action path |
| Distinguish fact from hypothesis | epistemic tiers (CANONICAL_OWNER / PROJECT_TRUTH / VERIFIED_* / INFERRED) with retrieval excluding INFERRED by default | Yes (design), empty in practice |
| Preserve intent across model/provider changes | durable missions, authority records bound to snapshot digests, `owner_approved` sealed server-side | Yes |
| Improve through interaction | confirm/correct/reject stored; calibrate() unused | No |
| Combine signals across apps/projects/services | attention engine merges notifications, reminders, escalations; project truth per project | Partially (trading and browser signals excluded from reasoning) |
| Maintain continuity | session epochs, outbox, mission persistence, restart-durable auth | Yes |
| Delegate while retaining one identity | single dispatch path to Hermes profile `van`; no Android→provider bypass (grep) | Yes |
| Explain consequential reasoning | mission events carry summaries; verification states are explicit | Partially (summaries are Hermes free text; no premise records reach the owner) |
| Request approval where authority requires it | A4 typed-only, biometric-bound; A5 denied | Yes |
| Surface uncertainty rather than fabricate | UNVERIFIABLE is a first-class terminal state; degraded codes; `MODEL_UNAVAILABLE` abstention in VATI | Yes, except `/health` 500 (GAP-F-007) and the stream grant (GAP-F-016) |

## Where the loop breaks (ordered by consequence)

1. **Memory never enters from the owner.** The kernel, tiers, provenance, readiness and snapshot digests are real and tested, and `orchestrator.py` asks the kernel on every command (P0-CTX-001 fix). But nothing an owner does on the phone or says to VAN writes a CANONICAL_OWNER fact; only Project Truth import populates the store. Consequence: `fact_ids` is always empty, so continuity across sessions is limited to missions and audit, and "VAN knew nothing" is the permanent state. (GAP-F-001, P1)
2. **Learning is write-only.** Every mission outcome is recorded with strategy fingerprints, and promotion gates exist, yet `strategies_for` is never called and the calibration engine is never invoked. The owner-agent runtime cannot get better. (GAP-F-008, P2)
3. **No proactive initiation.** VAN never opens a follow-up on its own; `may_create()` is dead. (GAP-F-028, P2)
4. **Reasoning cannot see trading or drive execution surfaces.** Hermes has no tool to read positions, run a browser assignment, execute an automation, or halt trading. The authority model is right (gateway seals authority, VATI sizes, Hermes proposes) but the tool surface is narrower than the model, so the intelligence layer is disconnected from the execution and trading planes. (GAP-F-003/005/006, P1)
5. **The conversation does not receive the answer.** Completion is visible in Activity/Missions and can be spoken only if the owner is on the chat when the synchronous response arrives. (GAP-F-011, P3)
6. **The embodiment does not react to attention.** URGENT, gestures and WAITING/SLEEPING have no producers. (GAP-F-012, P3)
7. **Nothing has been observed live end to end.** The Hermes run contract, the shim invocation and the `mission_result` callback have no token-free receipt. (QUAL-HERMES-01/02)

## Owner-control preservation (what is right)

- Authority never lives in the model: `owner_approved` comes from a sealed `CommandAuthorityRecord`; the shim's `google_action_execute` has no approval field; `ActionBeginBody.owner_approved` is ignored server-side (verified); VATI refuses model results carrying order fields (`cognition/contracts.py:249`); the commander binds `requested_by` to the HMAC principal.
- One dispatch path from the owner device to Hermes; third-party content enters only as UNTRUSTED_EXTERNAL evidence and can never become a command.
- Failure is visible: degraded codes, stalled missions, EXPIRED after silence, UNVERIFIABLE when no postcondition exists.

## What closing the loop requires (minimum, in order)

1. GAP-F-001 (memory producer + shim candidate tool or AGENTS.md correction) and GAP-F-002 (reminders producer).
2. GAP-F-003 and GAP-F-006 (read-only trading tools and browser/automation initiation tools on the shim, scoped credentials), then GAP-F-005 (trading.halt executor).
3. GAP-F-008 and GAP-F-028 (consume learned strategies; bounded proactive follow-up job).
4. GAP-F-011 and GAP-F-012 (conversation receives completion; embodiment reacts).
5. Live certification QUAL-HERMES-01/02 on the resulting build.
