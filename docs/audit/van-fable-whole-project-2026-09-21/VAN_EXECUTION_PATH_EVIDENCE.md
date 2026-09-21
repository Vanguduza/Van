# VAN execution path evidence (Fable whole-project audit)

Audited commit `0067d55071342b963293d0724f5a1604d233d105`. Each flow below is traced through the exact production code at this commit. "Proven" means an in-process test drives the real FastAPI app or the real Kotlin logic along that path; "live" means a token-free receipt exists. Where a link is missing the flow stops and the gap is named.

Common prefix for every owner command (used by flows 1–10, 15):

```
Android VanCommandController.submitText (control/VanCommandController.kt:221-283)
  → VanGatewayClient.dispatchCommand (gateway/VanGatewayClient.kt:908-1048): HMAC v3 canonical string, X-Van-Ingress-Token, X-Van-Device-Token, device-proof headers
  → POST /v1/commands (app.py:1492-1503) → middleware require_ingress_auth (app.py:1248-1333)
  → CommandOrchestrator._handle (orchestrator.py):
      idempotency.begin (:135) → signature verify (:159-233) → principal equality (:180-210) → nonce (:280-301)
      → typed resolution (command/resolver.py) → ingress trust (command/ingress_trust.py:91-125)
      → mission CAPTURED→UNDERSTOOD (command/mission_link.py) → A4 challenge if needed (:392-508)
      → project truth refs (:640-667) → context_requirements.derive (:672) → context.compile_snapshot (:678)
      → CommandAuthorityRecord sealed (:740-760) → mission AUTHORIZED → hermes.health (:784)
      → hermes.create_run(text, metadata{canonical_context, typed_resolution, owner_approved…}) (:803-838)
      → audit 'accepted' → CommandResult{status:'accepted', mission_id} → Android recordResponse (:319-378)
Hermes side (external): run → tools via hermes/mcp/owner_runtime_stdio.mjs → mission_result
  → POST /v1/runtime/missions/result (runtime_api.py:265-288) → MissionService.apply_hermes_result (mission/service.py:338-454)
  → VERIFYING → verifier (verification/production.py) → VERIFIED_SUCCESS | UNVERIFIABLE | FAILED
  → mission event (mission/service.py:695-720) → events bus → session WS/SSE (session/api.py:255-330) → Android VanEventStreamStore → Activity module; GET /v1/missions/{id} final_outcome → Missions module
```

## Flow 1 — "Van, summarize what needs my attention"

- Deterministic path: Overview module (`command/modules/OverviewModule.kt:61-76`) → `GET /v1/attention` (app.py:2172) and `GET /v1/briefing` (app.py:1715-1729) → `BriefingService.build` (briefing/service.py:24-107) aggregating `attention.list_open()`, reminders due today, audit completions. **Proven** (`tests/scenarios/test_acceptance_scenarios.py::test_scenario_1_morning_brief`).
- Narrative path: command → Hermes `owner-briefing` skill → Hermes would need attention/briefing tools; the shim has none (`hermes/mcp/README.md:10` names a `van-gateway` MCP server that does not exist). Hermes can only answer from Google reads and context queries. **Partial**: deterministic brief INTEGRATED_AND_EVIDENCED; Hermes narrative RUNTIME_CERTIFICATION_REQUIRED and tool-limited (GAP-F-006 family).

## Flow 2 — "Van, check my calendar and tell me what matters today"

- Prefix → no typed pattern → delegate-to-agent-runtime → Hermes run → shim `google_calendar_agenda` → `GET /v1/google/calendar/agenda` (app.py:2024-2031, internal-control GOOGLE scope) → `GoogleService.calendar_agenda` → `GoogleHttpTransport` (google/transport.py:81-133) → `https://www.googleapis.com/calendar/v3/calendars/primary/events` → JSON to Hermes → `mission_result COMPLETED summary` → VERIFYING → no postcondition for a read → UNVERIFIABLE with summary as final_outcome → Activity/Missions.
- Proven in-process: route + auth + transport contract (`backend/tests/test_google_capabilities_have_routes.py`); Workspace live canaries HTTP 200 (ledger 2026-09-16). Not proven: Hermes actually calling the shim (QUAL-HERMES-02). Status: RUNTIME_CERTIFICATION_REQUIRED. Note the owner reads the result in Activity, not in Chat (GAP-F-011).

## Flow 3 — "Van, investigate this link"

- Autonomous: prefix → Hermes; the shim has no browser tool; `POST /v1/browser/assignments` (browser/api.py:884-984) has no production caller. **Stops** — IMPLEMENTED_NOT_REACHABLE (GAP-F-006).
- Manual: `BrowserExternalLinkActivity` (AndroidManifest) → `BrowserActivity` → `/v1/browser/interactive-sessions/*` (VanGatewayClient.kt:518-651) → routers mounted only with a stream signing key (app.py:521-529,831-870) → Browser Stream Host (does not exist; QUAL-BRW-03). Repository complete, EXTERNAL.

## Flow 4 — "Van, ask an agent to inspect this project"

- Prefix with `project_id` → `projects.load_truth` SHA + repo SHA into `live_state_refs` (orchestrator.py:640-667) → snapshot → Hermes run with `project_id` metadata → Hermes delegation (councils/message_agent are Hermes-native per `hermes/bot/*`; bridge duplicates removed 2026-09-19) → result via `mission_result`. Proven in-process up to dispatch (`test_context_snapshot_lineage`, `test_command_creates_mission`). Hermes-side delegation and return: RUNTIME_CERTIFICATION_REQUIRED (QUAL-HERMES-01/02).

## Flow 5 — "Van, remember this decision"

- Prefix → resolver has no `remember` pattern (command/resolver.py:107-155) → delegate to Hermes → Hermes has no memory-candidate tool (shim) → nothing writes `owner_facts`. The device-authenticated writer `POST /v1/context/facts` (app.py:1810) has no Android caller. **Stops** — OPEN_GAP (GAP-F-001). Reading works: "what have I told you about X" → typed `owner.context.read` (resolver.py:154-155; action/registry.py:10).

## Flow 6 — "Van, remind/follow up on this later"

- Prefix → no pattern → Hermes → no reminder tool. `POST /v1/reminders` and `/v1/reminders/parse` (app.py:1731-1765) have no Android or shim caller. Consumers work: `_sweep_reminders` (app.py:592-616) → attention + `reminder.fired` event. **Stops at creation** — BACKEND_ONLY (GAP-F-002).

## Flow 7 — "Van, tell me why my active trade is moving"

- Owner display: Trading Command Centre (`trading/TradingCommandCentreActivity.kt`, `trading/ui/*.kt`) → `TradingRepository` → `GET /v1/trading/{portfolio,market-state,risk,cognition,trades,bars}` (app.py:2443-2487; owner-device routes) → `backend/van_gateway/trading/service.py` reads the hash-chained ledger (SQLite or Postgres DSN, staleness 15 min). Proven (`test_trading_api`, JVM trading tests).
- Reasoning: prefix → Hermes → commander tools (`status`, `ledger_status`, `accounts`; trading/commander/app.py:242-353) return no positions; shim has no trading tool; owner-device trading routes are unreachable with the internal token. **Stops** — IMPLEMENTED_NOT_REACHABLE on the cognition side (GAP-F-003).

## Flow 8 — "Van, determine whether this news materially changes my trade thesis"

- No news/event ingress exists beyond the economic calendar recorder (`trading/vati/calendar/recorder.py`, dual-source → `tier1_event_blackout_active` → `risk/authority.py:244`). VATI shadow cognition has no invoker (`trading/vati/app/account_service.py:178`; GAP-F-004). Hermes research (`research_search` → Exa) is default off (`exa_egress_enabled=False`) and Hermes cannot read the position (Flow 7). **Stops** — OPEN_GAP (GAP-F-003, GAP-F-004).

## Flow 9 — "Van, propose what to do with this position"

- Deterministic: `DecisionCycle` (`trading/vati/app/cycle.py:1-9`) `… → PROTECT → RECONCILE → TCA → REVIEW → VTIL PROPOSE`; `capsule_health` multiplier written post-trade (cycle.py:341-360) and read by `arbiter/opportunity.py:146,202`, `arbiter/meta_labeler.py:91` (bounded ≤ 1). Cognition reduce-only multiplier contract (`cognition/contracts.py:229-249`) exists but never fires (no invoker). Owner-facing proposal via Hermes: no read path. Status PARTIAL_IMPLEMENTATION (GAP-F-003/004). Authority boundary proven sound: `ExecutionRouter.execute` is the single `adapter.submit` caller (`execution/router.py:226`).

## Flow 10 — "Van, perform an action that requires biometric approval"

- "halt trading" → resolver `HALT_TRADING` (resolver.py:89-168) → typed `trading.halt` A4 → orchestrator issues challenge → `CommandResult{status:'approval_required', approval_challenge…}` (**proven**: `test_scenario_17b_typed_a4_reaches_owner_approval`) → Android `PendingA4Approval` → `BiometricGate.requestA4CommandApproval` (security/BiometricGate.kt:40-88; CryptoObject signature over the challenge) → resubmit with `approval_proof` → `OwnerApprovalService.verify_and_consume` (approval/service.py:114-210) → `owner_approved=True` sealed → Hermes run.
- Execution: Hermes `action_begin(trading.halt)` → AUTHORIZED (action/service.py); but nothing calls `POST /v1/trading/halt` (needs TRADING scope + `owner-halt` OwnerAuthority token; Android prepares only `capsule-promote`, VanGatewayClient.kt:205-219). Verifier `trading-halt` (verification/production.py:129) would find no OWNER_HALT event. **Stops after approval** — PARTIAL_IMPLEMENTATION (GAP-F-005). Google A4 (gmail send / calendar reschedule) has a complete executor (`google_action_execute` → `execute_authorized_action`, google/service.py:158-300) and is the working reference path.

## Flow 11 — Continue a task after Android process death

- Before dispatch: `EncryptedCommandQueue.enqueue` (queue/EncryptedCommandQueue.kt:65-92, `commit()`), replay on `APP_START` (VanApplication.kt:290), network/gateway edges (VanApplication.kt:384-426), `NO_STALE_REPLAY` never auto-retried (CommandQueueModels.kt:129-134). Boot: `OverlayRecoveryReceiver` restarts the service → process alive → replay. After dispatch: mission durable in SQLite; `GET /v1/missions` / `/v1/missions/{id}` (mission/api.py) restore the view; session epochs (session/service.py:210-233) fence stale frames. Proven in-process (`test_stored_command_is_deliverable`, `test_session_epoch_contract`, `test_recovery_matrix`); device behaviour DEVICE gate (QUAL-AND-01).

## Flow 12 — Operate while Hermes is temporarily unavailable and reconcile later

- `hermes.health` not ok → `DegradedCode.HERMES_OFFLINE` set, mission `note_stall`, `CommandResult{status:'degraded'}`, idempotency `complete` (orchestrator.py:784-800); dispatch error → idempotency `fail` (allows resend) (:840-857). Android: degraded status → `DegradedPanel`; `/health.ok` tracks Hermes (60 s poll). There is no automatic re-dispatch: the owner resends (same idempotency key replays a completed result, a failed claim is retaken). Proven (`test_scenario_12_hermes_failure`, `test_recovery_matrix`). Status INTEGRATED_AND_EVIDENCED with manual reconciliation; Hermes-side dedupe is QUAL-HERMES-04.

## Flow 13 — Share a URL/document/image into VAN

- `ShareIntakeActivity` (manifest SEND/SEND_MULTIPLE) → `ShareIntake` classifier drops secret-looking content (share/ShareIntake.kt:41-45; ShareIntakeActivity.kt:164) → `CONTEXT_INGEST` queue record → `QueueReplayer` routes to `POST /v1/context/ingest` (device-proofed) → `NotificationIntelligence.ingest_durable` → `attention.upsert` + event (app.py:2240-2300). Proven (`test_scenario_15_secret_notification`, `test_context_ingest_queue_routing`); share-sheet behaviour DEVICE gate. Content reaches Hermes only if Hermes queries context (evidence tier UNTRUSTED_EXTERNAL); there is no path that turns a shared URL into an autonomous investigation (Flow 3).

## Flow 14 — Urgent notification while another task is active

- `VanNotificationListenerService` (notification/…:21-73) policy/quiet hours/redaction/dedupe → CONTEXT_INGEST → `/v1/context/ingest` → classification URGENT → `attention.upsert` (severity from classification; scoring.py dispositions incl. URGENT_INTERRUPT) → `attention.upserted` event → device stream → Overview. The overlay's `URGENT` durable state has no producer (`VanLiveVisualState.urgent()` never called), so the embodiment does not change (GAP-F-012). Attention budget/quiet hours proven (`test_attention_is_one_engine`, scenario 2). Status PARTIAL_IMPLEMENTATION.

## Flow 15 — Delegate a multi-step job and return the completed result

- Prefix → Hermes run (mission RUNNING, deadline 15 min) → Hermes tools limited to context/knowledge/Google/research/actions; browser and automation unavailable (Flow 3) → `mission_result COMPLETED` → VERIFYING → verifier registry (`ledger-event`, `trading-halt`, `browser-evidence`, `api-readback`) → VERIFIED_SUCCESS only with an independently checkable postcondition, else UNVERIFIABLE → owner-visible mission events → Activity; final_outcome in Missions. In-process proven (`test_command_execution_result:96-134`). Chat does not update (GAP-F-011). Status PARTIAL_IMPLEMENTATION + RUNTIME_CERTIFICATION_REQUIRED.

## Summary

| Flow | Result |
|---|---|
| 1 | Deterministic brief works; narrative brief tool-limited |
| 2 | Complete in code; live Hermes→shim proof missing |
| 3 | Not reachable (no initiator) |
| 4 | Complete to dispatch; Hermes side external |
| 5 | Not implemented (no memory producer) |
| 6 | Not implemented (no reminder producer) |
| 7 | Owner can see; VAN cannot reason (no read path for Hermes) |
| 8 | Not implemented (no news path, no cognition invoker) |
| 9 | Deterministic only |
| 10 | Approval works; executor missing for trading.halt |
| 11 | Complete in code; device gate |
| 12 | Complete (manual resend) |
| 13 | Complete in code; device gate |
| 14 | Attention works; embodiment does not react |
| 15 | Complete in code minus browser/automation; live proof missing |
