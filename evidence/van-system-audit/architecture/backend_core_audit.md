# VAN Backend Gateway Core — Read-Only Evidence Audit

Repository: /home/user/Van, branch claude/van-system-audit-ysgtcd, HEAD dff38a0
Scope: backend/van_gateway/ core (app, runtime_api, orchestrator, models, config, command/, mission/, capability/, action/, approval/, audit/, idempotency/, events/bus.py, storage/db.py, decisions/, degraded/, reminders/, attention/, briefing/, notifications/, projects/router.py, research/).
All paths below are relative to /home/user/Van/backend unless prefixed with a repo-level directory.
Verification runs: `python -m pytest -q -p no:cacheprovider` over test_mission_core, test_typed_command_resolver, test_gateway, test_capability_registry, test_mission_binding_api, test_a4_owner_approval, test_command_authority_constraints, test_runtime_resolver_api, test_hermes_bridge, test_permissions_computeruse_verifiers -> 112 passed. (Note: the bare `pytest` binary on PATH is a uv tool without project deps and fails at collection with `No module named 'pydantic'`; `python -m pytest` is required.)

---------------------------------------------------------------------------------------------------
## 0. Headline findings

1. There is NO LLM call anywhere in the backend. The only "model" is Hermes, an external process reached over HTTP (`van_gateway/hermes/bridge.py:58-75`, POST `{base}/p/van/v1/runs`). Hermes's model provider is `anthropic` per `hermes/profile/van/config.yaml:13-14`, but the Hermes runtime itself is not in this repository (only profile/skills/MCP shim under `hermes/`). grep for anthropic/openai/gemini/chat-completions in van_gateway returns only config flags and degraded-code strings.
2. The owner command path (`POST /v1/commands`) ends by forwarding the raw text plus metadata to Hermes (`orchestrator.py:496-528`). The gateway executes nothing itself on that path. Hermes is expected to call back into `/v1/runtime/actions/begin|submitted|verify` and `/v1/runtime/knowledge/actions/execute` via the MCP shim (`hermes/mcp/owner_runtime_stdio.mjs:74-92`).
3. Hermes unreachable -> `/v1/commands` returns `status="degraded"`, `degraded=["HERMES_OFFLINE"]`, audit row written, idempotency marked complete/fail, nothing executed (`orchestrator.py:474-488`, `orchestrator.py:529-541`). Verified by probe: `HermesBridge("http://127.0.0.1:1")` -> `health()` returns `{'ok': False, 'degraded': 'HERMES_OFFLINE', ...}`; `create_run` raises `HermesBridgeError("hermes_offline")`.
4. The typed resolver is regex/fixed-phrase only (`command/resolver.py:76-113`); anything else becomes `HERMES_INTERPRETATION_REQUIRED` (`resolver.py:190-194`). Probe: "Please stop trading now" and "book me a flight to Cape Town tomorrow" -> HERMES_INTERPRETATION_REQUIRED; "halt trading" -> trading.halt A4.
5. Mission Core is IMPLEMENTED_BUT_ISOLATED. `MissionService.create` is called only from `POST /v1/missions` (internal-control) (`mission/api.py:320-336`) and tests. No production code (orchestrator, automation dispatch, browser API, Hermes MCP shim, Hermes skills) creates a mission. `grep -rn mission hermes/` finds no mission tooling; the MCP shim exposes no `/v1/missions*` endpoint.
6. VERIFIED_SUCCESS structurally requires a `VerificationRecord` with status=VERIFIED, >=1 evidence_ref and no missing postconditions, and a checkable SuccessContract (`mission/service.py:209-237`, `mission/models.py:179-201`). BUT the record is supplied by the caller in the HTTP body (`mission/api.py:70-74`, `338-351`); no server-side verifier is executed. `VerifierRegistry` and all verifier adapters (`mission/verifiers.py`) are referenced only from tests (`tests/test_permissions_computeruse_verifiers.py`). So "verified" is a schema-shape gate, not an independent observation.
7. HTTP-created missions cannot bind automation Activities: `CreateMissionBody` has no `authority_envelope` field (`mission/api.py:54-67`) so every API-created mission gets the default `AuthorityEnvelope(max_action_class=A2)` (`mission/models.py:154`); `automation.workflow.execute` is declared A3 (`registries/capabilities.json`) -> `ABOVE_AUTHORITY_CEILING A3>A2` (probe output below). Tests only pass because they call `MissionService.create(authority_envelope=AuthorityEnvelope(max_action_class=A3))` directly (`tests/test_mission_binding_api.py:108`).
8. `CapabilityRouter.route()` is invoked from exactly one production call site: `POST /v1/missions/route` (`mission/api.py:385`). Neither the orchestrator nor automation dispatch nor browser API consults it.
9. Storage is SQLite via aiosqlite only, 16 migrations, 71 `CREATE TABLE IF NOT EXISTS` statements (`storage/db.py:13`, `1361-1390`). No Postgres anywhere. Every `Store.execute/fetchone/fetchall` opens a new connection (`db.py:1340-1400`); no WAL, no busy_timeout, no in-process lock. Idempotency `begin()` is a non-atomic SELECT-then-INSERT (`idempotency/service.py:100-110`); a probe with two concurrent `begin("k1", ...)` produced `[None, IntegrityError]` (unhandled -> HTTP 500 instead of `in_flight`).
10. Event bus is a SQLite table + cursor; no SSE/websocket/push (`events/bus.py:14-46`). Android polls `GET /v1/events` (`android/.../VanGatewayClient.kt:331-333`, caller `CommandCentreActivity.kt:580`) and polls `/health` every 60s (`VanApplication.kt:101,199`). No FCM/Firebase in the Android tree. Only two producers publish events: `decision.escalated` (`app.py:569`) and `attention.upserted` (`app.py:703`). Mission state changes never reach the bus.

---------------------------------------------------------------------------------------------------
## 1. Route table

Auth layers (middleware `app.py:359-388`):
- INTERNAL = `X-Van-Internal-Token` equal to `VAN_INTERNAL_CONTROL_TOKEN` (constant-time compare, `google/control.py:237-246`). Paths classified by `internal_control_route()` (`app.py:299-357`) may bypass the ingress/device gate when the token is valid; each such handler ALSO re-verifies the header itself.
- INGRESS+DEVICE = `X-Van-Ingress-Token` == `VAN_INGRESS_TOKEN` (`app.py:373-378`) AND `X-Van-Device-Token` resolving to an unrevoked device (`app.py:384-388`, `auth/service.py:179-190`); sets `request.state.van_device_id`.
- HMAC = additionally a per-device HMAC-SHA256 signature over a canonical string (`auth/service.py:250-334`).
- NONE = exempt in middleware (`app.py:361-364`).
- If a path is INTERNAL-classified but the internal token is absent/invalid, the request falls through to INGRESS+DEVICE and then the handler's `require_internal_control` returns 403 (or 503 when unconfigured).

### 1.1 app.py routes
| Method | Path | Auth | Handler -> service |
|---|---|---|---|
| GET | /health | INGRESS only (`app.py:380-382`) | `hermes.health()`, `google.status()`, `google_broker.mesh_status()`, `owner_runtime.status()` (`app.py:397-436`) |
| POST | /v1/devices/pairing-ticket | INTERNAL | `auth.create_pairing_ticket` (`app.py:438-452`) |
| POST | /v1/devices/pair | NONE (pairing token >=32 chars in body) | `auth.pair_device`; returns ingress token + device token (`app.py:454-479`) |
| POST | /v1/devices/enroll | INTERNAL | `auth.enroll` (`app.py:481-491`) |
| POST | /v1/devices/{id}/revoke | INTERNAL | `auth.revoke` + `owner_runtime.actions.revoke_privileged_for_device` (`app.py:493-509`) |
| POST | /v1/commands | INGRESS+DEVICE + HMAC; device_id must equal token's device (`app.py:512-515`) | `orchestrator.handle` |
| GET | /v1/briefing | INGRESS+DEVICE | `hermes.health`, `google.status`, `google.calendar_agenda`, `briefing.build` (`app.py:517-532`) |
| POST | /v1/reminders | INGRESS+DEVICE | `reminders.create` (`app.py:534-536`) |
| GET | /v1/reminders | INGRESS+DEVICE | `reminders.list_open` |
| POST | /v1/reminders/{id}/resolve | INGRESS+DEVICE | `reminders.resolve` |
| POST | /v1/reminders/{id}/cancel | INGRESS+DEVICE | `reminders.cancel` |
| POST | /v1/reminders/parse | INGRESS+DEVICE | `parse_due_expression` + `reminders.create` (`app.py:552-566`) |
| POST | /v1/decisions/escalate | INGRESS+DEVICE | `decisions.escalate` + `events.publish` (`app.py:568-572`) |
| GET | /v1/decisions | INGRESS+DEVICE | `decisions.list_open` |
| POST | /v1/decisions/{id}/resolve | INGRESS+DEVICE | `decisions.resolve` |
| PUT | /v1/projects/{id}/truth | INTERNAL | `projects.cache_truth` (`app.py:584-597`) |
| POST | /v1/google/test-transport | INTERNAL | swaps in `FakeGoogleTransport` (`app.py:599-604`) |
| GET | /v1/google/gmail/search | INTERNAL | `google.gmail_search` |
| POST | /v1/google/gmail/send | INTERNAL | `google.gmail_send(action_class=A4, approved=<query flag>)` (`app.py:617-628`) |
| GET | /v1/google/status | INGRESS+DEVICE | `google.status` |
| POST | /v1/google/connect | INTERNAL | `google.store_refresh_token` |
| POST | /v1/google/revoke | INTERNAL | `google.revoke` |
| GET | /v1/google/mesh | INGRESS+DEVICE | `google_broker.mesh_status` |
| GET | /v1/google/capabilities | INGRESS+DEVICE | `google_broker.mesh_status` |
| POST | /v1/google/jobs/plan | INTERNAL | `google_router.plan` |
| GET | /v1/google/jobs/{id} | INTERNAL | `google_router.job` |
| POST | /v1/google/jobs/{id}/artifacts | INTERNAL | `google_router.record_artifact` |
| POST | /v1/attention | INGRESS+DEVICE | `attention.upsert` + `events.publish` (`app.py:693-704`) |
| GET | /v1/attention | INGRESS+DEVICE | `attention.list_open` |
| POST | /v1/attention/{id}/ack | INGRESS+DEVICE | `attention.acknowledge` |
| POST | /v1/notifications/ingest | INGRESS+DEVICE | `notifications.ingest` -> `attention.upsert` (`app.py:715-728`) |
| GET | /v1/degraded | INGRESS+DEVICE | `degraded.snapshot` |
| GET | /v1/projects | INGRESS+DEVICE | `projects.known_projects` |
| GET | /v1/projects/{id}/truth | INGRESS+DEVICE | `projects.load_truth` |
| GET | /v1/events | INGRESS+DEVICE; device_id query must match token (`app.py:743-746`) | `events.replay` |
| GET | /v1/trading/status, /trades, /portfolio, /accounts, /market-state, /risk, /trades/{id}, /bars, /tickets | INGRESS+DEVICE | `TradingService.*` (`app.py:749-827`, `894-896`) |
| POST | /v1/trading/accounts/action | INGRESS+DEVICE + HMAC over `canonical_action` + 300s skew (`app.py:829-877`) | `onboarding.run` |
| GET | /v1/trading/oauth/{broker}/callback | NONE (`app.py:363-364`) | `onboarding.oauth_callback` -> HTML (`app.py:879-892`) |
| POST | /v1/trading/halt | INTERNAL | `trading.halt` + audit (`app.py:898-919`) |
| POST | /v1/trading/tickets/{id}/confirm | INTERNAL | `trading.confirm_ticket` (`app.py:921-950`) |
| POST | /v1/events/reset | INGRESS+DEVICE (device match) | `events.reset_cursor`, sets EVENT_CURSOR_RESET (`app.py:952-961`) |

### 1.2 runtime_api.py (`prefix /v1/runtime`, all INTERNAL, each handler calls `_require_internal`, `runtime_api.py:115-120`)
| Method | Path | Service |
|---|---|---|
| GET | /status | `OwnerRuntimeApi.status` (`runtime_api.py:131-149`) |
| POST | /resolve | `TypedCommandResolver.resolve` (`:159-162`) |
| POST | /context/facts | `OwnerContextService.admit_fact`; forced INFERRED+MODEL_DERIVED (`:122-125`, `:164-171`) |
| POST | /context/edges | `OwnerContextService.admit_edge` (`:173-181`) |
| POST | /context/graph/query | `context.traverse_graph` |
| POST | /context/lexical/query | `retrieval.lexical_query` |
| POST | /context/hot-capsules | `retrieval.compile_hot_capsule` |
| POST | /context/readiness | `context.readiness` |
| POST | /context/snapshots | `context.compile_snapshot` |
| GET | /context/export/{scope} | `context.export_scope` |
| DELETE | /context/scope/{scope} | `context.erase_scope` (`:230-233`) |
| GET | /knowledge/status | `KnowledgeRuntime.status` |
| POST | /knowledge/vekl/query, /vekl/certify-canary | `knowledge.query_vekl / certify_vekl` |
| POST | /knowledge/obsidian/query, /index, /certify | `knowledge.*obsidian*` |
| GET | /knowledge/notebook/enterprise/recent, /{id} | `knowledge.notebook_enterprise_*` |
| POST | /knowledge/notebook/enterprise/certify, /consumer/ask, /consumer/certify | `knowledge.*` |
| POST | /knowledge/actions/execute | `knowledge.execute_authorized_action(actions, ...)` — the ONLY in-gateway executor of typed actions; limited to 5 google.notebook.* action ids (`knowledge/service.py:190-250`) |
| POST | /actions/begin | `authority.authorize_action` then `actions.begin` (`runtime_api.py:332-365`) |
| POST | /actions/{execution_id}/submitted | `actions.mark_submitted` |
| POST | /actions/verify | `actions.verify` (`:383-392`) |
| GET | /actions/{execution_id} | `actions.get_execution` |
| GET | /research/status | `ExaResearchService.status` |
| POST | /research/search | `research.search` (`:407-414`) |
| POST | /research/certify-canary | `research.certify_canary` |

### 1.3 mission/api.py (`prefix /v1`; owner vs internal split decided by `app.py:315-320` and re-checked in handlers)
| Method | Path | Auth | Service |
|---|---|---|---|
| GET | /missions | INGRESS+DEVICE | `missions.list_missions` (`mission/api.py:163-169`) |
| GET | /missions/{id} | INGRESS+DEVICE | `missions.get`, `verification_record` (`:171-185`) |
| GET | /missions/{id}/activity | INGRESS+DEVICE | `binder.sync_from_subsystems` then `missions.activities/events` (`:187-200`) |
| GET | /missions/{id}/evidence | INGRESS+DEVICE | events + verification + `capability_router.decisions_for` (`:202-218`) |
| GET | /needs-you | INGRESS+DEVICE | `missions.needs_owner` + raw `decisions` SQL (`:220-232`) |
| GET | /activity | INGRESS+DEVICE | raw `mission_events` JOIN `missions` SQL (`:234-259`) |
| GET | /capabilities/status | INGRESS+DEVICE | `registry.routability` per capability (`:261-283`) |
| POST | /missions/{id}/cancel | INGRESS+DEVICE | `missions.transition(CANCELLED, actor=OWNER_DEVICE)` (`:287-297`) |
| POST | /missions/{id}/message | INGRESS+DEVICE | `missions.record_event(event_type=MISSION_CREATED ...)` (`:299-316`) — see defect D3 |
| POST | /missions | INTERNAL | `missions.create` (`:320-336`) |
| POST | /missions/{id}/transition | INTERNAL | `missions.transition` with caller-supplied VerificationRecord (`:338-351`) |
| POST | /missions/{id}/activities | INTERNAL | `missions.add_activity` (`:353-368`) |
| POST | /missions/route | INTERNAL | `capability_router.route` (`:370-406`) |
| POST | /missions/{id}/backfill | INTERNAL | `binder.backfill` (`:408-425`) |

### 1.4 Other routers mounted by app.py (out of audit scope; listed for completeness)
- `/v1/automation/*` (AutomationApi, `automation/api.py:190-575`): route, compile, admit, generate, execute, hot/publish, hot/withdraw, standing-intents, templates — all INTERNAL by `app.py:310-311`.
- `/v1/automation/health`, `/v1/browser/health` — INTERNAL (`app.py:306-307`).
- `/v1/browser/*` (BrowserApi, `browser/api.py:624-875`): GET status/policy/tasks/escalations/evidence = owner; POST profiles/leases/tasks/evidence/complete/assignments = INTERNAL (`app.py:333-334`).
- `/v1/understanding*`, `/v1/permissions*`, `/v1/technology-radar`, `/v1/eval`, `/v1/autonomy` (UnderstandingApi): owner-facing except `POST /v1/understanding/observe` which is INTERNAL (`app.py:323-330`).

---------------------------------------------------------------------------------------------------
## 2. Owner command lifecycle (POST /v1/commands)

Step-by-step, `orchestrator.py`:
1. Idempotency begin (`:79-99`): prior COMPLETED result replayed; same key different hash -> `conflict`; IN_FLIGHT -> `in_flight`.
2. Device + signature (`:101-153`): `auth.require_device`; v1 canonical (`auth/service.py:262-283`) only if all provenance fields are default (`orchestrator.py:64-76`); v2 canonical (`auth/service.py:285-334`) requires OWNER_DEVICE principal and `requested_by == "device:<id>"` (`orchestrator.py:112-116`); HMAC-SHA256 verify (`auth/service.py:256-259`).
3. Typed resolution (`:155-157`): `resolver.resolve(req.text)`; effective class = max(signed, canonical) (`resolver.py:196-201`).
4. Expiry checks (`:159-196`): explicit `expires_at_unix`; typed `max_age_seconds`; global `owner_intent_max_age_seconds` (default 24h, `config.py:176`).
5. A5 hard deny (`:198-207`).
6. A4 (`:209-311`): requires EXACT_ACTION; without `approval_proof` issues one-time ECDSA challenge (`approval/service.py:278-331`, TTL 15..120s) and returns `approval_required`; with proof, `verify_and_consume` under `BEGIN IMMEDIATE` (`approval/service.py:333-429`), consumed atomically.
7. NO_STALE_REPLAY window <=60s check (`:313-334`).
8. Injection marker check (`:336-347`) — ONLY when `req.context_trust == UNTRUSTED`; default is CONVERSATION (`models.py:123`), so the check is opt-in by the client.
9. Project Truth gate (`:366-398`): A3/A4 with missing/stale truth -> `degraded` STALE_PROJECT_TRUTH.
10. Context snapshot sealed (`:400-435`): failure -> `degraded` OWNER_CONTEXT_UNAVAILABLE.
11. Authority record sealed into `runtime_meta` (`:437-472`, `command/authority.py:264-276`).
12. Hermes health probe (`:474-488`): not ok -> `degraded` HERMES_OFFLINE, nothing dispatched.
13. `hermes.create_run(req.text, metadata=...)` (`:490-528`): POST `{base}/p/van/v1/runs` with bearer (`hermes/bridge.py:58-75`, `:27-39`). Failure -> `degraded`, idempotency `fail` (allows retry).
14. Audit `accepted` with `model_delegate="hermes:van"` and `evidence_pointer=run.id` (`:543-566`); result `accepted` with `hermes_run_id`.

What "actually executes": nothing in the gateway on this path. Execution is expected to happen inside Hermes, which then calls `POST /v1/runtime/actions/begin` (authority re-check `command/authority.py:287-332`: principal, requested_by, turn_id, snapshot_id, expiry, device revocation, class escalation, typed action id and typed parameter constraints), `/submitted`, `/verify`. The only gateway-side executor is `knowledge.execute_authorized_action` for 5 notebook actions (`knowledge/service.py:200-206`). For `trading.halt`, `research.web.search`, `owner.context.read` there is no gateway executor (grep for those ids outside registry/resolver returns nothing) — Hermes must perform them using `/v1/runtime/research/search` etc.

LLM presence: none. `grep -rn -i "anthropic|openai|gemini|claude|chat/completions"` in van_gateway hits only `config.py:45,74`, `models.py:55`, `degraded/registry.py:14-40` (strings), `resolver.py:92,99` (regex word "gemini"). Hermes bridge docstring: "Never launches models directly" (`hermes/bridge.py:19`).

Hermes dispatch reality: `HermesBridge` is a thin httpx forward with health/create_run/capabilities/message_agent/create_council (`hermes/bridge.py:41-144`). No Hermes server is in the repo; `hermes/` contains profile (`hermes/profile/van/config.yaml`, model provider anthropic at `:13-14`), skills, policy hook, and the MCP stdio shim. Tests never talk to a real Hermes: `tests/test_gateway.py:40-44` and `tests/test_rev31_runtime_wiring.py:39-49` monkeypatch `hermes.health` and `hermes.create_run`; `tests/test_hermes_bridge.py:21-22,40-41` use `httpx.MockTransport`.

Resolver command set (`command/resolver.py`):
- HALT_TRADING exact phrases (`:76-84`): "halt trading", "stop trading", "pause trading", "halt/stop/pause autonomous trading", "emergency stop trading" -> `trading.halt` (A4, no_stale_replay, max_age 5s per `action/registry.py:419-427`).
- NOTE_PATTERNS (`:86-89`): "create|make [a] [new] notebooklm|notebook lm note [named|called] <title>" and "... note in notebooklm ..." -> `google.notebook.note.create` (A3).
- NOTEBOOK_ENTERPRISE_DELETE (`:91-95`) and DELETE_SOURCES (`:96-102`) -> `google.notebook.enterprise.delete` / `.sources.delete` (A4).
- RESEARCH_PATTERNS (`:104-108`): "research <q>", "search the web for <q>", "look up <q>" -> `research.web.search` (A2) unless composite mutation (`:44-49`).
- CONTEXT_PATTERNS (`:110-113`): "what do you know about <t>", "what have i told you about <t>" -> `owner.context.read` (A1).
- Everything else -> `GENERAL_OWNER_INTENT` / HERMES_INTERPRETATION_REQUIRED (`:190-194`).
Note: resolver only sets `title` for note.create but the action's schema requires `notebook_id` too (`action/registry.py:370-373`); typed_parameter_constraints then pin only `title`.

---------------------------------------------------------------------------------------------------
## 3. Mission Core

States (`mission/models.py:36-55`): CAPTURED, UNDERSTOOD, PLANNED, AUTHORIZED, RUNNING, WAITING_EXTERNAL, WAITING_FOR_OWNER, RESUME_AUTHORIZED, VERIFYING, VERIFIED_SUCCESS, PARTIAL_SUCCESS, FAILED, CANCELLED, EXPIRED, BLOCKED_POLICY, BLOCKED_UNSAFE, UNVERIFIABLE.
Terminal (`:60-69`): VERIFIED_SUCCESS, PARTIAL_SUCCESS, FAILED, CANCELLED, EXPIRED, BLOCKED_POLICY, BLOCKED_UNSAFE, UNVERIFIABLE.
LEGAL_TRANSITIONS (`:79-108`): linear ladder CAPTURED->UNDERSTOOD->PLANNED->(AUTHORIZED|WAITING_FOR_OWNER)->RUNNING->(WAITING_EXTERNAL|WAITING_FOR_OWNER|VERIFYING|FAILED); WAITING_FOR_OWNER->RESUME_AUTHORIZED->RUNNING; VERIFYING->(VERIFIED_SUCCESS|PARTIAL_SUCCESS|UNVERIFIABLE|FAILED|CANCELLED|EXPIRED); CANCELLED/EXPIRED/BLOCKED_* reachable from every non-terminal state. Creation is always CAPTURED (`mission/service.py:84-89,107`).

VERIFIED_SUCCESS gate (`service.py:178-181`, `209-237`): requires VerificationRecord present; `success_contract.is_checkable` (non-empty postconditions AND verifier_class set, `models.py:179-181`); `verification.supports_success` (status VERIFIED, >=1 evidence_ref, no missing postconditions, `models.py:194-201`). Test `tests/test_mission_core.py` covers these refusals (part of the 112 passing).
Caveat: the VerificationRecord is a request-body object at `POST /v1/missions/{id}/transition` (`mission/api.py:70-74`, `345-348`). Any internal-token holder can send `{"status":"VERIFIED","evidence_refs":["x"],"verifier_version":"y","verified_at_ms":0}`. No verifier adapter runs server-side.

Verifiers (`mission/verifiers.py`): ObservationVerifier base (`:86-131`) + ApiReadbackVerifier (`:134`), RepositoryShaVerifier (`:142`), CiRunVerifier (`:150`), LedgerEventVerifier (`:157`), ScreenshotVerifier (`:165`), EngineReportVerifier always UNVERIFIABLE (`:178-196`), VerifierRegistry (`:199-215`). Each takes an `observe` callable supplied by the caller; none is constructed in production code. Only `tests/test_permissions_computeruse_verifiers.py:29-31,193-255` uses them.

Callers of MissionService.create: `mission/api.py:326` (internal HTTP) only. `app.py:228` constructs the service. Orchestrator never imports mission. Hermes MCP shim (`hermes/mcp/owner_runtime_stdio.mjs:74-92`) has no mission tool; `grep -rni mission hermes/` -> no mission instructions. Conclusion: Mission Core is reachable only by hand-driven internal HTTP; it is not wired into the owner command path.

Binding (`mission/binding.py`): `browser/api.py:815-825` and `automation/api.py:416-426` call the binder only when the caller passes `mission_id`; exceptions are caught and returned as `mission_binding.error`. Because `add_activity` enforces routability against the mission envelope (`service.py:263`, `329-354`), under the default envelope: `automation.workflow.execute` -> ABOVE_AUTHORITY_CEILING A3>A2; `browser.semantic.extract` -> NOT_READY unless browser fabric enabled with readiness evidence (`capability/readiness.py:395-406`). Probe output under default envelope with the real manifest:
```
automation.workflow.execute   routable=False ABOVE_AUTHORITY_CEILING A3>A2
browser.harness.navigate      routable=False NOT_READY (no probe in probe harness; in app: BROWSER_FABRIC_DISABLED unless VAN_BROWSER_ENABLED)
browser.semantic.extract      routable=False NOT_READY
google.gmail.search           routable=False NOT_READY (GOOGLE_MESH)
google.gmail.send             routable=False ABOVE_AUTHORITY_CEILING A4>A2
knowledge.vekl.retrieve       routable=True
native.owner_context.read     routable=True
native.project_truth.read     routable=True
research.exa.search           routable=True
trading.vati.analyse          routable=True
trading.vati.submit_order     routable=False NEVER_ROUTABLE
```

---------------------------------------------------------------------------------------------------
## 4. Capability registry / router

Manifest `registries/capabilities.json` (version 1.0.0) declares 11 capabilities: native.owner_context.read (A1), native.project_truth.read (A1), knowledge.vekl.retrieve (A1), research.exa.search (A2, EXTERNAL_DISCLOSING, fallback browser.semantic.extract), browser.harness.navigate (A2, SCREENSHOT), browser.semantic.extract (A2, SCREENSHOT, fallback harness), automation.workflow.execute (A3, API_READBACK, AUTOMATION_REGISTRY), google.gmail.search (A2), google.gmail.send (A4, requires owner presence), trading.vati.analyse (A1, LEDGER_EVENT), trading.vati.submit_order (A4, NEVER_ROUTABLE).
Registry (`capability/registry.py`): load+validate (`:97-186`; refuses fallback self/undeclared/escalating/disclosing, mutation-without-verifier), `sync()` upserts `capability_registry` rows sealed by digest at boot (`:188-227`, called from lifespan `app.py:261`), `routability()` four-term gate (`:257-347`). Probes wired in `app.py:213-226`.
Router (`capability/router.py:160-239`): deterministic scoring over declared facts, policy filter first, persisted to `capability_route_decisions` (`:266-291`). Production call sites: `mission/api.py:385` (`POST /v1/missions/route`) and `decisions_for` at `mission/api.py:217`. No other caller (grep). `automation/api.py:194` uses the separate AutomationMediumRouter.
Dead filter: `RoutingConstraints.permit_external_disclosure` defaults True and `from_envelope` never sets it (`capability/models.py:196`, `:212-216`), so `PRIVACY_NOT_PERMITTED` (`registry.py:315-323`) cannot trigger from a mission envelope.

---------------------------------------------------------------------------------------------------
## 5. Storage

- Engine: aiosqlite only (`storage/db.py:9`, `1340-1344`); `PRAGMA foreign_keys=ON` per connection; no WAL/busy_timeout. No postgres/psycopg/asyncpg references anywhere in van_gateway.
- Migrations: 16 versions (`MIGRATIONS` keys 1..16), applied via `executescript` in `migrate()` (`db.py:1361-1390`), with a v5 healing step for a diverged v4 lineage (`db.py:1346-1358`).
- Tables by version (71 CREATE TABLE statements; `pairing_tickets` appears in both v4 and v5):
  v1 schema_migrations, devices, idempotency, attention, reminders, decisions, audit, events, event_cursors, google_connections, project_truth_cache, capability_grants; v2 google_principal, google_capability_connections, google_jobs, google_artifacts; v3 ALTER devices.encrypted_secret; v4 pairing_tickets + ALTER devices.access_token_hash; v5 runtime_meta, owner_facts, owner_context_edges, context_snapshots, action_definitions, action_executions, action_receipts, research_evidence; v6 automation_capabilities, automation_artifacts, automation_runs, automation_external_events, automation_standing_intents, standing_automation_authorities, automation_run_nonces, browser_tasks, browser_evidence, browser_profiles; v7 browser_escalations; v8 browser_scope_authorizations; v9 automation_workflow_health, automation_repairs, automation_dead_letter, automation_run_telemetry, automation_generation_telemetry; v10 missions, mission_activities, mission_events; v11 capability_registry, capability_route_decisions; v12 owner_cognitive_model, decision_fingerprints, shared_vocabulary, intent_nodes, intent_edges, intent_missions, strategic_memory, cognitive_complement_map, symbiotic_growth; v13 reasoning_assessments, assumption_ledger, premise_assessments; v14 attention_candidates, domain_trust, proactive_policies; v15 external_reality, technology_capabilities, benchmark_runs, execution_strategies, eval_runs; v16 permission_grants, computer_operations.
- Concurrency: each Store call is its own connection+commit (`db.py:1392-1400`). Atomic sections exist only where callers use `store.connection()` explicitly: approval consume with `BEGIN IMMEDIATE` (`approval/service.py:350-429`), permission revoke (`capability/permissions.py:519-526`), revoke_privileged (`action/service.py:291-302`), event publish (`events/bus.py:15-21`). Mission transition uses a compare-and-swap `WHERE state=?` but ignores rowcount (`mission/service.py:183-193`), so a lost race still emits a state event.
- Idempotency: SELECT then INSERT (`idempotency/service.py:100-110`); probe: concurrent same-key begin -> `[None, IntegrityError]` (500, not `in_flight`). Authority seal uses UPSERT and conflict detection (`command/authority.py:264-276`). Action begin dedupes by idempotency_key + parameters digest (`action/service.py:148-152`). Reminders dedupe by idempotency_key (`reminders/service.py:339-350`).

---------------------------------------------------------------------------------------------------
## 6. Events bus / Android notification

- `EventBus` = insert into `events` table (`events/bus.py:14-21`) + paged replay with cursor upsert (`:23-46`) + reset (`:48-56`). In-process, DB-backed, pull-only. No StreamingResponse/WebSocket/SSE anywhere (grep).
- Producers: only `decision.escalated` (`app.py:569`) and `attention.upserted` (`app.py:703`). Missions, actions, automation, browser emit nothing to the bus.
- Android: `VanGatewayClient.events(afterSeq)` -> `GET /v1/events` (`android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt:331-333`), used from `CommandCentreActivity.kt:580` with `events(0)` (always from seq 0). Health polled every 60s (`VanApplication.kt:101`, `:199`). Mission screens call `/v1/missions*`, `/v1/needs-you`, `/v1/activity`, `/v1/capabilities/status` (`VanGatewayClient.kt:233-274`) on demand. No FCM/Firebase in android sources (grep). Therefore Android learns of state changes by polling only.

---------------------------------------------------------------------------------------------------
## 7. Stub / TODO / placeholder inventory (in scope)

grep -i "TODO|FIXME|not yet|placeholder|simulated|synthetic|stub|fake|not implemented|XXX|HACK" over scope:
- `app.py:22,599-604,611` — `FakeGoogleTransport` and `POST /v1/google/test-transport` swaps live Google transport for a fake at runtime. INTERNAL-only but present on the production app object (production path, reachable with internal token).
- `attention/scoring.py:214` — "requires owner dismissal feedback; not yet collected" (attention scoring; not on the /v1/commands path).
- `hermes/bridge.py:114` — comment "no fake council runtime"; `create_council` falls back to direct messages when Hermes lacks group rooms (production path if ever called; no caller in gateway).
- No TODO/FIXME/NotImplemented markers in scope.
Functional stubs by behaviour rather than marker:
- `mission/verifiers.py` — full adapter set, zero production construction (isolated).
- `command/resolver.py` — deliberately fixed-pattern only (documented, `:69-73`).
- `mission/api.py:311-315` — owner "message" recorded as `MISSION_CREATED` event type (no MISSION_MESSAGE type exists in `models.py:267-282`).
- `reminders/service.py:414-427` `fire_due()` — no scheduler calls it (grep: only defined); reminders never fire server-side.
- `notifications/intelligence.py:309,322` — `_seen` dedupe set is in-memory, lost on restart.
- `degraded/registry.py:310-324` — in-memory set only; state lost on restart.

---------------------------------------------------------------------------------------------------
## 8. Subsystem classification

| Subsystem | Class | Justification |
|---|---|---|
| app.py wiring + auth middleware | INTEGRATED | All routers mounted, middleware enforces three layers (`app.py:359-388`); covered by tests (test_gateway, test_rev31_runtime_wiring). |
| orchestrator (owner command path) | INTEGRATED (Hermes side unverified) | Full pipeline to `hermes.create_run` (`orchestrator.py:79-566`); real Hermes never exercised in repo tests (monkeypatched at `tests/test_gateway.py:40-44`). |
| hermes/bridge.py | PARTIAL | Real httpx forward (`bridge.py:58-75`), but the Hermes runtime is external and absent; MockTransport tests only. |
| command/resolver.py | IMPLEMENTED (fixed patterns) | 5 pattern families (`resolver.py:76-113`); no NL understanding by design. |
| command/authority.py | INTEGRATED | Sealed at `orchestrator.py:472`, enforced at `runtime_api.py:339-347` and by automation dispatcher (`app.py:167-170`). |
| command/standing.py | INTEGRATED (automation) | Wired via `app.py:180` into AutomationApi; derives run authority through the same `CommandAuthorityService`. |
| mission/service + models | IMPLEMENTED_BUT_ISOLATED | State machine and gates correct and tested; only entry is internal HTTP (`mission/api.py:326`); no production creator. |
| mission/verifiers.py | IMPLEMENTED_BUT_ISOLATED | No production construction; receipts on the transition route are caller-supplied. |
| mission/binding.py | PARTIAL | Wired into browser/automation APIs (`browser/api.py:815`, `automation/api.py:418`) but unbindable for HTTP-created missions (default A2 envelope vs A3 automation; browser needs readiness). |
| mission/api.py | INTEGRATED (read model) / ISOLATED (writes) | Android reads it (`VanGatewayClient.kt:233-274`); writes need an internal-token caller that does not exist in-repo. |
| capability/registry.py | INTEGRATED | Loaded+synced at boot (`app.py:261`), probes wired (`app.py:213-226`), used by mission add_activity and /v1/capabilities/status. |
| capability/router.py | IMPLEMENTED_BUT_ISOLATED | Only `POST /v1/missions/route` calls it (`mission/api.py:385`). |
| capability/readiness.py | INTEGRATED | Probes wired in `app.py:213-226`. |
| capability/permissions.py | IMPLEMENTED_BUT_ISOLATED (within scope) | Grants only created by UnderstandingApi/tests; no core path calls `grant()`. |
| action/ (runtime, registry, models) | INTEGRATED | Builtins installed at startup (`runtime_api.py:129`), begin/verify routes, revoke on device revoke (`app.py:505`). Execution of non-notebook actions is external to gateway. |
| approval/ (A4 ECDSA challenges) | INTEGRATED | Issued/consumed in orchestrator (`orchestrator.py:229-296`); atomic consume; test_a4_owner_approval passes. |
| audit/ | INTEGRATED | Written on every orchestrator branch and trading/account routes. |
| idempotency/ | PARTIAL | Works serially; non-atomic begin races to IntegrityError (probe). |
| events/bus.py | PARTIAL | Works as DB log; only 2 producers; poll-only. |
| storage/db.py | INTEGRATED | 16 migrations applied at lifespan (`app.py:254`); SQLite only; no concurrency tuning. |
| decisions/ | INTEGRATED | escalate/list/resolve routes + attention link; surfaced in /v1/needs-you. |
| degraded/ | INTEGRATED (volatile) | Set from health/orchestrator; in-memory only. |
| reminders/ | PARTIAL | CRUD + parse wired; `fire_due` has no caller/scheduler. |
| attention/engine.py | INTEGRATED | Used by decisions, notifications, briefing, /v1/attention. |
| briefing/ | INTEGRATED | `/v1/briefing` (`app.py:517-532`); calendar only when Google transport live. |
| notifications/intelligence.py | INTEGRATED (volatile dedupe) | `/v1/notifications/ingest` -> attention. |
| projects/router.py | INTEGRATED | Truth gate in orchestrator (`orchestrator.py:366-398`); PUT truth internal. |
| research/ (Exa) | INTEGRATED, default OFF | Real httpx call to api.exa.ai (`research/exa.py:89-91`) gated by `exa_egress_enabled=False` default (`config.py:197`); `HTTPStatusError` not translated (500). |
| E2E_VERIFIED | none | No test or tool in repo drives phone -> gateway -> real Hermes -> runtime callback. |

---------------------------------------------------------------------------------------------------
## 9. Security observations

S1 (Medium) Caller-asserted verification: `POST /v1/missions/{id}/transition` accepts an arbitrary `VerificationRecord` (`mission/api.py:70-74`, `345-348`); any internal-token holder can mint VERIFIED_SUCCESS without any observation. Combined with `evidence_refs` being free strings, the "receipt" is not independently checkable.
S2 (Medium) Internal control token is a single shared static secret compared with `hmac.compare_digest` (`google/control.py:245`); it grants: device enrollment/revocation, project truth injection, Google connect/revoke/send, trading halt/confirm, all `/v1/runtime/*` including `DELETE /v1/runtime/context/scope/{scope}` (`runtime_api.py:230-233`) and `/v1/google/test-transport` which silently replaces live Google I/O with a fake (`app.py:599-604`). One credential, very wide blast radius, no per-route scoping.
S3 (Low) Injection screening is client-opt-in: `INJECTION_MARKERS` only apply when `context_trust == UNTRUSTED` (`orchestrator.py:336-347`); default `CONVERSATION` (`models.py:123`). The markers list is 6 phrases (`orchestrator.py:27-34`).
S4 (Low) Replay: v1/v2 HMAC covers idempotency_key and issued_at (`auth/service.py:262-334`); replay of an identical signed request returns the cached result (`orchestrator.py:80-82`), so no double execution. `nonce` is signed but never stored/uniqueness-checked (grep: only `orchestrator.py:72,138,513`). Window is 24h by default (`config.py:176`) for A1-A3 non-typed commands; typed A4 actions 5-30s (`action/registry.py:403-426`). A captured signed A1-A3 command can be resubmitted with the same key only (cached), so replay risk is bounded to the idempotency table lifetime (no expiry/cleanup found).
S5 (Low) Idempotency race -> unhandled `IntegrityError` (`idempotency/service.py:106-110`), yielding HTTP 500 rather than `in_flight`; also leaves the row IN_FLIGHT for the winner while the loser's client sees an error.
S6 (Low) `PUT /v1/projects/{id}/truth` trusts `truth_sha`/`repo_sha` from the caller; no recomputation of the hash over `truth` (`app.py:584-597`, `projects/router.py:448-462`).
S7 (Low) Decision spoofing: `POST /v1/decisions/escalate` is device-authenticated, with `source` defaulting to "hermes" (`decisions/service.py:24`); a device can create escalations attributed to Hermes and they surface in `/v1/needs-you`.
S8 (Low) Reflected content in HTML: `trading_oauth_callback` interpolates `exc.detail` and `result['broker']` into an HTMLResponse without escaping (`app.py:883-891`). `exc.detail` values are server-side constants (`trading/accounts.py:168,176,183,186`) and `broker` is validated to "ctrader"/"deriv" before echo, so not exploitable today, but the pattern is fragile.
S9 (Info) Owner mission reads are not scoped to the authenticated device (`mission/api.py:163-169` accepts any `owner_principal_id`); acceptable in a single-owner deployment.
S10 (Info) `hmac.compare_digest` on `str` inputs raises `TypeError` for non-ASCII (`google/control.py:245`, `app.py:369`); a non-ASCII header value would 500 rather than 403. Minor.
S11 (Info) `/health` requires the ingress token (`app.py:373-382`); reverse-proxy probes must carry it.
S12 (Info) Hermes base URL defaults to plaintext `http://127.0.0.1:8642` (`config.py:157`); bearer token sent in clear if pointed off-host.

---------------------------------------------------------------------------------------------------
## 10. Defects noted in passing (non-security)

D1 `mission/api.py:311-315` — owner message recorded with `MissionEventType.MISSION_CREATED`; the timeline will show a second "mission.created" entry for each message.
D2 `mission/service.py:183-207` — CAS update ignores rowcount; a lost race still records the transition event and returns the refreshed (other) state.
D3 `capability/models.py:196,212-216` — `permit_external_disclosure` never derived from the envelope; privacy filter is dead for missions.
D4 `mission/api.py:54-67` — no `authority_envelope` on CreateMissionBody; envelope cannot be widened via HTTP, so A3 automation binding is impossible for API-created missions (probe: ABOVE_AUTHORITY_CEILING A3>A2).
D5 `runtime_api.py:407-414` — `httpx.HTTPStatusError` from Exa (`research/exa.py:91`) not translated -> 500.
D6 `command/resolver.py:128-139` vs `action/registry.py:370-373` — note.create resolution omits required `notebook_id`.
D7 `app.py:115` `MissionApi.__init__` creates its own `MissionBinder` while `app.py:236` creates another; both stateless, harmless but duplicated.
D8 `events/bus.py:39-45` — GET replay mutates `event_cursors`; Android always passes `after_seq=0` (`CommandCentreActivity.kt:580`), so cursors are effectively unused.
D9 `reminders/service.py:414` — `fire_due` has no scheduler.
