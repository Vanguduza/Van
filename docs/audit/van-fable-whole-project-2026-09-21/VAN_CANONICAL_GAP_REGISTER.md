# VAN canonical gap register (Fable whole-project audit)

Audited commit: `0067d55071342b963293d0724f5a1604d233d105` (branch `claude/van-fable-forensic-audit-ds8g0o`, clean tree). Date: 2026-09-21.

Status vocabulary is the audit taxonomy (INTEGRATED_AND_EVIDENCED, IMPLEMENTED_NOT_REACHABLE, PARTIAL_IMPLEMENTATION, STUB_OR_PLACEHOLDER, TEST_ONLY, UI_ONLY, BACKEND_ONLY, EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE, RUNTIME_CERTIFICATION_REQUIRED, DELIBERATELY_REMOVED_CANON_CORRECTED, CONTRADICTORY_IMPLEMENTATION, OPEN_GAP). Priority is operational consequence (P0 authority/safety, P1 core product failure, P2 integration/coherence, P3 resilience/operability/UX, P4 refinement).

This register is independent of `docs/audit/van-whole-project-2026-09-21/21_GAP_REGISTER.json` (the reconstructed Sol register, all repository items CLOSED). Every item below was found open at the audited commit by tracing code, and none duplicates a REC-* item except where noted. The companion JSON is generated from the same source and is byte-consistent with this file.

> **Forensic-history rule.** Detailed finding bodies below preserve what was true at the audited
> commit; they are not current defect claims. The closure table is re-stated by the post-Fable
> product pass in PR #59. Current live/device/provider gates are authoritative only in
> `VAN_RUNTIME_QUALIFICATION_MATRIX.md`.

## Summary

| Priority | Count |
|---|---|
| P0 | 0 |
| P1 | 5 |
| P2 | 5 |
| P3 | 11 |
| P4 | 7 |
| **Total** | **28** |

| Status | Count |
|---|---|
| BACKEND_ONLY | 2 |
| CONTRADICTORY_IMPLEMENTATION | 3 |
| EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE | 1 |
| IMPLEMENTED_NOT_REACHABLE | 4 |
| OPEN_GAP | 8 |
| PARTIAL_IMPLEMENTATION | 7 |
| STUB_OR_PLACEHOLDER | 1 |
| TEST_ONLY | 1 |
| UI_ONLY | 1 |

## Closure (2026-09-22)

Original Fable closure HEAD: `100d898`; post-Fable product closure: PR #59. Full evidence per gap is reconciled in `VAN_FABLE_IMPLEMENTATION_CLOSURE_REPORT.md` §2 and the runtime qualification matrix.

| Closure status | Count |
|---|---|
| FIXED_AND_EVIDENCED | 27 |
| SUPERSEDED_BY_BETTER_IMPLEMENTATION | 1 |
| **Total** | **28** |

Mixed rows (a slash) count under their first status; the second half names the part that is deliberately removed or externally gated.

| Gap | Closure status | Commits |
|---|---|---|
| GAP-F-001 | FIXED_AND_EVIDENCED | 528366b, b78cbf4, 5498a6f |
| GAP-F-002 | FIXED_AND_EVIDENCED | 528366b, b78cbf4, 5498a6f |
| GAP-F-003 | FIXED_AND_EVIDENCED | b78cbf4, 3d845bc |
| GAP-F-004 | FIXED_AND_EVIDENCED | 3d845bc |
| GAP-F-005 | FIXED_AND_EVIDENCED | 528366b, 81805c9 |
| GAP-F-006 | FIXED_AND_EVIDENCED | b78cbf4 |
| GAP-F-007 | FIXED_AND_EVIDENCED | c193d47 |
| GAP-F-008 | FIXED_AND_EVIDENCED | b952b40, 528366b |
| GAP-F-009 | FIXED_AND_EVIDENCED | c193d47 |
| GAP-F-010 | FIXED_AND_EVIDENCED | 5498a6f |
| GAP-F-011 | FIXED_AND_EVIDENCED | 5498a6f |
| GAP-F-012 | FIXED_AND_EVIDENCED | 17f4fba, 3d845bc |
| GAP-F-013 | FIXED_AND_EVIDENCED (repository local-TTS path) / DEVICE_ARTEFACT_QUALIFICATION_REQUIRED | 17f4fba, PR #59 |
| GAP-F-014 | FIXED_AND_EVIDENCED | 17f4fba, 5498a6f |
| GAP-F-015 | FIXED_AND_EVIDENCED | b78cbf4 |
| GAP-F-016 | FIXED_AND_EVIDENCED | 1b6e44e |
| GAP-F-017 | FIXED_AND_EVIDENCED | 1b6e44e |
| GAP-F-018 | FIXED_AND_EVIDENCED | 1b6e44e |
| GAP-F-019 | SUPERSEDED_BY_BETTER_IMPLEMENTATION | 528366b |
| GAP-F-020 | FIXED_AND_EVIDENCED | c193d47, 1b6e44e, b78cbf4 |
| GAP-F-021 | FIXED_AND_EVIDENCED | 1b6e44e |
| GAP-F-022 | FIXED_AND_EVIDENCED | 1b6e44e |
| GAP-F-023 | FIXED_AND_EVIDENCED (mutation, instrumentation job) / EXTERNALLY_GATED_REPOSITORY_COMPLETE (device sign-off) | 1b6e44e, a60b009 |
| GAP-F-024 | FIXED_AND_EVIDENCED | c193d47, 5498a6f |
| GAP-F-025 | FIXED_AND_EVIDENCED | 1b6e44e |
| GAP-F-026 | FIXED_AND_EVIDENCED (repository durable runtime) / PENDING_LIVE | PR #59 |
| GAP-F-027 | FIXED_AND_EVIDENCED | 5498a6f, b46ca65 |
| GAP-F-028 | FIXED_AND_EVIDENCED | b952b40 |

## Root causes

| Root cause | Statement | Gaps |
|---|---|---|
| RC-A | **Audit-time state:** the Hermes tool surface had 30 tools and was narrower than the gateway authority model. **Current post-closure state:** the fixed allowlist has 51 tools, including memory candidates, trading reads, browser/automation initiation and Temporal durable controls; exact shim/registration equality is contract-tested. | GAP-F-001 (part), 003, 005 (part), 006, 015 |
| RC-B | Owner-facing write surfaces exist in the gateway with no owner-side producer (no Android caller, no typed command): owner facts, reminders, trading halt execution, Google revoke. | GAP-F-001, 002, 005, 024 |
| RC-C | Learning, calibration, proactive-policy and context-requirement stores are produced but never consumed by a decision path. | GAP-F-008, 019, 028 |
| RC-D | Enum/catalog/predicate drift with no exhaustiveness test: DegradedCode vs CATALOG, legacy vs scoped internal tokens, two Google readiness predicates, Android degraded vocabulary, stream-grant mount gate. | GAP-F-007, 009, 010, 016, 025 |
| RC-E | An external dependency is declared in a comment but has no injection point in code (VATI cognition invoker). | GAP-F-004 |
| RC-F | UI coherence: the conversational surface and the embodiment do not consume the runtime signals that exist. | GAP-F-011, 012 |
| RC-G | Design artefacts left unwired (SpeechCueClock, sherpa TTS preference, dead symbols). | GAP-F-013, 020 |

## Gaps

### GAP-F-001 — Owner memory has no conversational producer: canonical owner facts are never written from any owner interaction

- **Priority:** P1  
- **Status:** OPEN_GAP  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 528366b, b78cbf4, 5498a6f — command/local_executors.py memory.remember + memory.decision.record via OwnerFactAuthor; owner-fact-readback verifier; test_local_typed_actions.py; shim context_fact_candidate/context_edge_candidate; memory/MemoryRoute.kt  
- **Affected requirements:** REQ-MEM-02, REQ-SYM-09, REQ-FLOW-05  
- **Subsystem:** gateway context / Android Command Centre / Hermes MCP shim  
- **Root cause:** RC-B (gateway write surfaces without an owner-side producer) + RC-A (Hermes tool surface narrower than the authority model)
- **Evidence:**
  - backend/van_gateway/app.py:1810 POST /v1/context/facts is the only CANONICAL_OWNER writer (device-authenticated) - zero callers in android/app/src/main (grep 'context/facts' → none)
  - hermes/mcp/owner_runtime_stdio.mjs:50-114 exposes 30 tools; none maps to /v1/runtime/context/facts or /context/edges (the INFERRED candidate route at runtime_api.py:295-312)
  - backend/van_gateway/command/resolver.py:107-155 typed patterns cover notebook notes, research, 'what do you know about'; no 'remember ...' pattern
  - backend/van_gateway/orchestrator.py:672-721 compile_snapshot → canonical_context.fact_ids: with no producer the kernel is always empty (only PROJECT_TRUTH import via PUT /v1/projects/{id}/truth app.py:1784 populates owner_facts)
  - hermes/profile/van/AGENTS.md:12 states Hermes 'may submit inferred/model-derived memory candidates' - the shim provides no such tool (contradiction)
- **Dependent symptoms:**
  - GAP-F-015
  - GAP-F-019
  - Flow 5 'Van, remember this decision' cannot complete
  - Flow 1/2 context snapshots carry requirements_asked>0 with fact_ids=[] on every command
- **Repository fix required:** (1) Add a typed owner-device action 'memory.remember' (A2/A3, allowed_principals OWNER_DEVICE) in action/registry.py + resolver pattern ('remember (that )?...') whose executor calls OwnerFactAuthor.state; (2) add a Memory module to the Command Centre that calls POST /v1/context/facts, GET /v1/context/memory, DELETE /v1/context/facts; (3) either add a 'context_fact_candidate' shim tool bound to /v1/runtime/context/facts (INFERRED only) or correct AGENTS.md:12.
- **External qualification required:** None. Live proof that Hermes dereferences fact_ids remains RUNTIME_CERTIFICATION_REQUIRED (QUAL-HERMES-03).
- **Acceptance criteria:** A signed owner command 'remember that my accountant is Thandi' produces an owner_facts row at CANONICAL_OWNER; the next command's canonical_context.fact_ids is non-empty and /v1/runtime/context/lexical/query returns the fact. Contract test asserts POST /v1/context/facts has an Android caller or a typed-action executor.

### GAP-F-002 — Reminders have no production producer

- **Priority:** P1  
- **Status:** BACKEND_ONLY  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 528366b, b78cbf4, 5498a6f — reminder.create executor + resolver; migration 29 reminders.source; reminder-readback verifier; shim reminder_create → POST /v1/runtime/reminders; Home 'Upcoming' from GET /v1/reminders  
- **Affected requirements:** REQ-ATT-04, REQ-FLOW-06  
- **Subsystem:** gateway reminders / Android / typed resolver  
- **Root cause:** RC-B
- **Evidence:**
  - backend/van_gateway/app.py:1731-1765 POST /v1/reminders and /v1/reminders/parse exist (owner-device routes)
  - android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt: no '/v1/reminders' path (grep → none); Command Centre has no reminder module (command/CommandModule.kt:14-38)
  - hermes/mcp/owner_runtime_stdio.mjs: no reminder tool; backend/van_gateway/command/resolver.py: no 'remind' pattern (only context_requirements.py:47 names people for 'remind Thandi')
  - Consumers are real: app.py:592-616 _sweep_reminders fires due reminders into attention + events; briefing/service.py:57-64 lists TODAY
- **Dependent symptoms:**
  - Flow 6 'Van, remind/follow up on this later' cannot complete
  - README claim 'deterministic attention/reminders' is consumer-only
- **Repository fix required:** Add resolver patterns ('remind me (to|about) ... (at|in|on) ...', 'follow up on ... later') resolving to a typed owner-device action 'reminder.create' executed by the gateway via parse_due_expression + ReminderService.create; add a Reminders card to the Overview/Tasks module calling POST /v1/reminders.
- **External qualification required:** None.
- **Acceptance criteria:** 'remind me to call Thandi at 3pm' → reminders row with due time; sweep fires it into /v1/attention and the device event stream; contract test asserts a production producer exists for reminders.create.

### GAP-F-003 — Hermes has no in-repository path to observe trading state (positions, portfolio, risk, trades)

- **Priority:** P1  
- **Status:** IMPLEMENTED_NOT_REACHABLE  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits b78cbf4, 3d845bc — /v1/runtime/trading/* (6 tools); commander positions/assessment read-only; test_runtime_hermes_surface.py; test_owner_runtime_mcp_contract.py (48 tools)  
- **Affected requirements:** REQ-TRD-01, REQ-TRD-05, REQ-FLOW-07, REQ-FLOW-08, REQ-FLOW-09  
- **Subsystem:** Hermes MCP shim / trading commander / gateway trading routes  
- **Root cause:** RC-A
- **Evidence:**
  - trading/commander/app.py:34 COMMANDS = status, ledger_status, services, restart_service, tail_log, run_backtest, vekl_resolve, halt, doctor, accounts (+gateway-only account/promotion). cmd_status (app.py:245-251) returns host/uptime/ledger head+count/units; cmd_ledger_status returns chain_ok/counts - no positions, no trades
  - backend/van_gateway/app.py:2443-2487 /v1/trading/* GET routes have control_scope None (app.py:1056-1125) → owner-device routes; hermes/mcp/owner_runtime_stdio.mjs has no trading tool and only carries the internal token
  - hermes/skills/trading-intelligence/SKILL.md:16-27 instructs Hermes to analyse open positions and submit TradeIntent (A3) - no tool exists for either
  - backend/van_gateway/trading/cognition.py:12 live_advisory DISABLED; no news/event feed other than the economic calendar recorder (trading/vati/calendar/recorder.py) which only drives tier1 blackout
- **Dependent symptoms:**
  - Flows 7-9 (why is my trade moving / does this news change my thesis / propose what to do) have no cognition-side data path
  - hermes/skills/trading-intelligence promises analysis it cannot ground
- **Repository fix required:** Add read-only shim tools (trading_portfolio, trading_positions, trading_risk, trading_market_state, trading_trade_detail) bound to new internal-control routes under /v1/runtime/trading/* (ControlScope.RUNTIME) that reuse backend/van_gateway/trading/service.py read models; or add a 'positions' command to the commander tool list. Keep all mutation out of scope (VATI authority unchanged).
- **External qualification required:** Live VATI ledger (Postgres) on van-trading-core; broker live path (QUAL-TRD-01/02).
- **Acceptance criteria:** Hermes 'van' can call trading_positions and receive the same read model Android shows; no new mutation tool is added; test_owner_runtime_mcp_contract updated.

### GAP-F-004 — VATI shadow cognition has no model invoker in production; the entire cognition package abstains MODEL_UNAVAILABLE

- **Priority:** P2  
- **Status:** IMPLEMENTED_NOT_REACHABLE  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 3d845bc — cognition/invokers.py Null/HttpJson/HermesRun from session config; read model names the real invoker or MODEL_INVOKER_UNCONFIGURED; test_active_trade_e2e.py. Live invoker credentials remain QUAL-TRD-05.  
- **Affected requirements:** REQ-TRD-06, REQ-TRD-08  
- **Subsystem:** trading/vati/cognition  
- **Root cause:** RC-E (external dependency declared but no injection point)
- **Evidence:**
  - trading/vati/app/account_service.py:175-178 ShadowCognitionRuntime(ledger=self._ledger) constructed without an invoker; comment: 'A provider invoker is an external runtime dependency'
  - trading/vati/cognition/runtime.py:132-140 with invoker None → narrative 'no model invoker is configured on this runtime'
  - grep invoker across trading/ (non-test) → no config, CLI, env or service constructs one
  - backend/van_gateway/trading/cognition.py:11-22 read model advertises model_hierarchy [fable-5.1, gpt-6-astra, claude-opus-5, gpt-5.6-sol] while shadow/handoffs/decision_exam are structurally empty in production
- **Dependent symptoms:**
  - Android Cognition screens render an empty shadow book
  - Trading learning loop's cognition attribution (trade_lifecycle.py:844 resolve_trade) never has entries
- **Repository fix required:** Add a provider-invoker construction path (config-driven, credentials from vault, provider registry in cognition/providers.py) in account_service or a dedicated vati-cognition worker; until then, mark cognition_mode in the read model as MODEL_INVOKER_UNCONFIGURED rather than OFFLINE_EVOLUTION+SHADOW_LIVE.
- **External qualification required:** Model provider credentials on van-trading-core (QUAL-TRD-05).
- **Acceptance criteria:** With a configured invoker, wake() records a CognitiveAssessment; without one the read model states the abstention explicitly; RiskAuthority decision unchanged in both cases (existing contract tests).

### GAP-F-005 — Typed A4 action trading.halt reaches biometric approval but has no executor

- **Priority:** P1  
- **Status:** PARTIAL_IMPLEMENTATION  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 528366b, 81805c9 — TradingHaltExecutor with owner-halt OwnerAuthority token (client_context.owner_halt_authority_ref) + A4 proof; test_local_typed_actions.py halt cases; Android trading/TradingHaltAuthority.kt + Trading screen halt path  
- **Affected requirements:** REQ-SEC-05, REQ-TRD-09, REQ-FLOW-10  
- **Subsystem:** gateway action runtime / Android trading / commander  
- **Root cause:** RC-B + RC-A
- **Evidence:**
  - backend/van_gateway/command/resolver.py:89-168 'halt trading' → typed action trading.halt (A4); tests/scenarios/test_acceptance_scenarios.py:207-211 proves approval_required
  - backend/van_gateway/action/registry.py:119-126 trading.halt allowed_principals OWNER_DEVICE, verifier DOMAIN_ATTESTATION; verification/production.py:129 'trading-halt' readback expects an OWNER_HALT ledger event
  - backend/van_gateway/orchestrator.py:803-838: after approval the command is dispatched to Hermes; no gateway-side executor for trading.halt (grep 'trading.halt' → registry, verification, descriptor, control_scopes only)
  - backend/van_gateway/app.py:2820-2842 POST /v1/trading/halt requires ControlScope.TRADING and owner_signature_ref = OwnerAuthority token for act 'owner-halt' (trading/service.py:310-313); the shim has no trading tool; android/app/src/main has no 'owner-halt' OwnerAuthorityToken preparation (only 'capsule-promote', VanGatewayClient.kt:205-219)
- **Dependent symptoms:**
  - Flow 10 ends at approval; the mission would reach VERIFYING then UNVERIFIABLE/FAILED
  - Owner has no emergency kill-switch surface on the phone (Android trading is read-only + promotion)
- **Repository fix required:** On A4-approved trading.halt, have the gateway self-execute: Android prepares an 'owner-halt' OwnerAuthorityToken (subject 'van-trading-core') alongside the approval proof; orchestrator calls trading.halt() before/instead of Hermes dispatch and verifies via trading_halt_readback. Add a Halt button to TradingCommandCentreActivity behind BiometricGate.
- **External qualification required:** Owner authority key enrolled on van-trading-core (registries/owner_authority_keys.json is empty by design; QUAL-TRD-03).
- **Acceptance criteria:** 'halt trading' + biometric → OWNER_HALT event in the ledger → mission VERIFIED_SUCCESS via trading-halt readback; scenario test extended past approval_required.

### GAP-F-006 — Autonomous browser and automation execution has no production initiator

- **Priority:** P1  
- **Status:** IMPLEMENTED_NOT_REACHABLE  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits b78cbf4 — shim browser_task_create/assignment_run/task_status/task_evidence + automation_route/execute/run_status; AGENTS.md/skills truthful  
- **Affected requirements:** REQ-BRW-01, REQ-AUT-01, REQ-FLOW-03, REQ-FLOW-15  
- **Subsystem:** Hermes MCP shim / browser api / automation api  
- **Root cause:** RC-A
- **Evidence:**
  - backend/van_gateway/browser/api.py:884-984 run_assignment is 'the only way a browser worker runs autonomously' (internal-control, ControlScope.BROWSER); backend/van_gateway/automation/api.py:243-759 all internal-control
  - hermes/mcp/owner_runtime_stdio.mjs: no browser_* or automation_* tool; hermes/profile/van/config.yaml:110-128 registers only van_trading_commander; tools/hermes/register_owner_runtime_mcp.sh registers only van_owner_runtime
  - hermes/mcp/README.md:8-10 lists a 'van-gateway' MCP server (grants, evidence, health) that has no shim or registration script in the repository
  - android VanGatewayClient.kt:498-517 browser calls are GET only (+ owner interactive sessions); Android never POSTs /v1/browser/tasks or /assignments
  - Reachability worker: /v1/automation/* (13 routes) have no caller in Android, shim, tools, deploy or gateway-internal code
- **Dependent symptoms:**
  - Flow 3 'investigate this link' cannot reach Harness/Stagehand; only the owner's manual remote browser (needs stream host) exists
  - Flow 15 delegated multi-step job cannot use automation/browser
  - Boundary escalation (browser/api.py:289-626) is reachable only from tests
- **Repository fix required:** Add scoped shim tools: browser_assignment_run/browser_task_status/browser_task_evidence (→ /v1/browser/assignments, /tasks/{id}) and automation_route/automation_execute/automation_run_status (→ /v1/automation/*), registered through register_owner_runtime_mcp.sh with BROWSER/AUTOMATION scoped credentials; or ship the documented 'van-gateway' MCP server. Update hermes/skills/browser-intelligence and automation-fabric to name the tools.
- **External qualification required:** Harness/Stagehand/n8n live runtimes (QUAL-BRW-01/02, QUAL-AUT-01).
- **Acceptance criteria:** With browser_enabled=true and a fake worker, a Hermes tool call creates a browser task bound to the command's mission and its evidence appears in /v1/missions/{id}/evidence; test_owner_runtime_mcp_contract lists the new tools.

### GAP-F-007 — /health and /v1/degraded return HTTP 500 when an uncatalogued DegradedCode is active (9 of 35 codes missing from CATALOG)

- **Priority:** P2  
- **Status:** OPEN_GAP  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits c193d47 — degraded/registry.py 9-code CATALOG, tolerant snapshot(); test_degraded_catalog_is_exhaustive.py  
- **Affected requirements:** REQ-RES-04, REQ-OBS-03  
- **Subsystem:** gateway degraded registry / observability  
- **Root cause:** RC-D (enum/catalog drift with no exhaustiveness test)
- **Evidence:**
  - backend/van_gateway/degraded/registry.py CATALOG has 26 entries; backend/van_gateway/models.py DegradedCode has 35 members; missing: GOOGLE_PRINCIPAL_UNVERIFIED, GOOGLE_CAPABILITY_UNAVAILABLE, GOOGLE_OAUTH_CLIENT_UNCONFIGURED, GOOGLE_ACCOUNT_ENTITLEMENT_UNVERIFIED, OWNER_CONTEXT_UNAVAILABLE, OWNER_CONTEXT_CONFLICTED, RESEARCH_UNAVAILABLE, RESEARCH_EGRESS_DENIED, DEVICE_OR_GRANT_REVOKED
  - backend/van_gateway/orchestrator.py:685 degraded.set(DegradedCode.OWNER_CONTEXT_UNAVAILABLE, True) on any snapshot exception - the only one of the 9 missing codes that reaches DegradedRegistry.set() today; the other 8 appear only as strings in response payloads (google/service.py:73, google/mesh.py:302,362, action/service.py:295) and are latent
  - Reproduced (scratch probe against create_app): GET /health 200 → after set(OWNER_CONTEXT_UNAVAILABLE) → KeyError → HTTP 500 (log line error_class KeyError)
  - android VanApplication.kt:537-558 marks 'gateway' BROKEN on non-200 /health → owner sees 'gateway broken' during a context-store fault
- **Dependent symptoms:**
  - Observability lost during the fault it should report
  - False 'gateway broken' on Android
- **Repository fix required:** Add the 9 CATALOG entries; add a test asserting set(DegradedCode) == set(CATALOG); make snapshot() tolerate unknown codes with a generic entry.
- **External qualification required:** None.
- **Acceptance criteria:** Test passes; /health returns 200 with degraded list containing OWNER_CONTEXT_UNAVAILABLE when set.

### GAP-F-008 — Learning and adaptation stores are write-only with respect to future decisions

- **Priority:** P2  
- **Status:** PARTIAL_IMPLEMENTATION  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits b952b40, 528366b — learning/feed.py strategies_for; calibrate() wired in understanding/api.py; ActionAutonomyGate; canonical_context.permitted_strategies; test_learning_read_back.py, test_action_runtime_autonomy.py  
- **Affected requirements:** REQ-SYM-08, REQ-SYM-10, REQ-COG-06  
- **Subsystem:** gateway learning / evolution / reasoning / proactive  
- **Root cause:** RC-C
- **Evidence:**
  - backend/van_gateway/learning/feed.py:233 strategies_for → evolution/radar.py:649 permitted_for: zero callers outside their definitions (grep)
  - backend/van_gateway/reasoning/calibration.py RelationshipCalibrationEngine constructed at understanding/api.py:95; .calibrate() never called (grep)
  - backend/van_gateway/proactive/autonomy.py DomainTrustService/ProactivePolicyService read only inside understanding/api.py routes (api.py:334,347); orchestrator.py and action/service.py never consult them
  - Producers are real: mission/service.py:180,295,310,313 → learning/feed.py writes learning_outcomes, execution_strategies, intent_nodes, decision_fingerprints, symbiotic_growth; scheduled auto_demote/mark_stale mutate the stores (app.py:670-682)
- **Dependent symptoms:**
  - Symbiotic loop link 'learn/update → improve future behaviour' is broken for the owner-agent runtime (trading has its own capsule_health read-back which works)
  - /v1/understanding shows learned data the system does not use
- **Repository fix required:** Consume strategies_for in orchestrator (attach permitted strategies to canonical_context or a runtime route Hermes calls), consult DomainTrust/ProactivePolicy in action/service.authorize for autonomy ceilings, and call calibrate() on owner corrections.
- **External qualification required:** None.
- **Acceptance criteria:** A mission whose strategy was promoted changes the next same-intent command's canonical_context (or a Hermes-readable route); test_learning_records_and_bounds extended with a read-back assertion.

### GAP-F-009 — Scoped internal-control credentials are not honoured by six routers (fail-closed 503 for scoped-only deployments)

- **Priority:** P2  
- **Status:** CONTRADICTORY_IMPLEMENTATION  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits c193d47 — auth/control_scopes.py require_scoped_internal in 6 routers; test_scoped_internal_control_reaches_routers.py  
- **Affected requirements:** REQ-SEC-02  
- **Subsystem:** gateway auth / routers  
- **Root cause:** RC-D (two authority checks for one rule)
- **Evidence:**
  - backend/van_gateway/app.py:1248-1333 middleware uses control_authority.permits(token, scope) (scoped credentials, P0-SEC-001)
  - runtime_api.py:221-224, mission/api.py:137-139, understanding/api.py:116-118, automation/api.py:227-229, automation/health.py:127-129, browser/api.py:162-164 each call verify_internal_control(settings.internal_control_token, token) - legacy token only; constructors receive settings but not control_authority
  - Reproduced: VAN_INTERNAL_CONTROL_TOKEN='' + VAN_INTERNAL_CONTROL_SCOPED_TOKENS='runtime:…' → GET /v1/runtime/status 503 internal_control_token_unconfigured; GET /v1/automation/health 503
  - backend/tests/test_control_scopes.py always sets the legacy token, so the gap is untested
- **Dependent symptoms:**
  - Operators must keep one shared legacy token, defeating least-privilege separation
- **Repository fix required:** Inject ControlAuthority into the six router classes and replace _require_internal with a scope-aware check identical to app.py require_internal_control; add a scoped-only test.
- **External qualification required:** None.
- **Acceptance criteria:** Scoped-only configuration reaches /v1/runtime/status, /v1/missions POST, /v1/automation/*, /v1/browser/* mutation, /v1/understanding/observe with the correct scope and is refused with the wrong one.

### GAP-F-010 — Android does not consume the gateway's structured degraded state

- **Priority:** P3  
- **Status:** PARTIAL_IMPLEMENTATION  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 5498a6f — degraded/GatewayDegradedMapping.kt; DegradedModeStore.applyGatewayHealth bound via DegradedBridge in VanApplication.onCreate; Settings reconciled list; GatewayDegradedMappingTest (12)  
- **Affected requirements:** REQ-RES-04, REQ-AND-14  
- **Subsystem:** Android degraded / gateway degraded  
- **Root cause:** RC-D
- **Evidence:**
  - android VanApplication.kt:537-558 reads only health.ok and health.hermes.degraded; GET /v1/degraded never called from Android (grep)
  - android degraded/DegradedMode.kt:47-66 vocabulary (hermes, gateway, overlay, queue, notifications, voice, wake_word, biometric, google) has no mapping from backend DegradedCode (TRADING_LEDGER_UNAVAILABLE, STORAGE_PROBLEM, AUTOMATION_*, BROWSER_*, ...)
- **Dependent symptoms:**
  - Backend faults collapse into 'gateway/hermes broken' with canned text
- **Repository fix required:** Map /health.degraded[] (still_works/will_not_do/restore_action) into DegradedSubsystem entries; render in DegradedPanel.
- **External qualification required:** None.
- **Acceptance criteria:** Setting TRADING_LEDGER_UNAVAILABLE on the gateway shows a trading-specific degraded row on the device (JVM test on the mapper).

### GAP-F-011 — The conversational surface never receives the completed answer; completion is visible only in Activity/Missions

- **Priority:** P3  
- **Status:** PARTIAL_IMPLEMENTATION  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 5498a6f — command/work/ConversationReducer.kt; VanCommandController.pollUnfinishedCommands (4 s); VanGatewayClient.commandStatus; context_gaps as 'VAN did not know'; control/VanSpokenAnswer.kt → VoiceEdge.speak; ConversationReducerTest (8)  
- **Affected requirements:** REQ-UX-03, REQ-HER-05  
- **Subsystem:** Android chat / gateway command status  
- **Root cause:** RC-F (UI coherence)
- **Evidence:**
  - android control/VanCommandController.kt:319-378 recordResponse stores the synchronous dispatch response (status 'accepted', message) as the VAN message; no polling of GET /v1/commands/{id} anywhere in android/app/src/main (grep 'commands/' → none)
  - backend/van_gateway/app.py:1655-1713 GET /v1/commands/{id} returns status/sentence/final_outcome, not the Hermes summary text
  - backend/van_gateway/mission/service.py:695-720 owner-visible mission events (with summary) reach the device via events bus → session WS/SSE (session/api.py:255-330) → events/VanEventStreamStore → Activity module; final_outcome appears in MissionsModule.kt:146
- **Dependent symptoms:**
  - Owner asks in Chat, must open Activity/Missions to read the result; spoken response is 'working on it' semantics only
- **Repository fix required:** Subscribe the chat conversation to mission events for its command_id (or poll /v1/commands/{id}) and append the final_outcome/summary as a VAN message; speak it when finished.
- **External qualification required:** None.
- **Acceptance criteria:** After a mission_result COMPLETED callback, the chat thread shows the summary without navigating away.

### GAP-F-012 — Embodiment gestures and three durable states are declared and rendered but never produced by runtime

- **Priority:** P3  
- **Status:** UI_ONLY  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 17f4fba, 3d845bc — visual/VanEmbodimentReducer.kt + VanEmbodimentProducers.kt + VanMotionMap.kt; trading/bridge.py trading.trade.closed producer; visual-preview VanEmbodimentCoverageTest  
- **Affected requirements:** REQ-EMB-03, REQ-EMB-04  
- **Subsystem:** Android visual  
- **Root cause:** RC-F
- **Evidence:**
  - android visual/RiveContract.kt:7-53 VanFiniteAction (14: HELLO_WAVE, ACK_NOD, POINT_*, CELEBRATE, CAUTION, CONFIRM, SHRUG, PRESENT_CARD, OPEN_PANEL, CLOSE_PANEL) rendered by visual/VanScene.kt:156-361; grep -rln VanFiniteAction android → only tests and visual-preview; VanLiveVisualState.action() has no production caller
  - VanDurableState.URGENT: VanLiveVisualState.urgent() never called; WAITING and SLEEPING never assigned (only referenced in BrowserVisualState.NEVER_PROPOSED)
- **Dependent symptoms:**
  - Canonical intent (audit brief §2) lists these actions/states as required behaviours; in the shipped app they cannot play
- **Repository fix required:** Produce actions from real transitions: HELLO_WAVE on first pairing/session open, ACK_NOD on command accepted, CONFIRM on VERIFIED_SUCCESS, CAUTION on WAITING_FOR_OWNER, SHRUG on UNVERIFIABLE, PRESENT_CARD on attention URGENT_INTERRUPT; set URGENT from attention disposition URGENT_INTERRUPT, WAITING from mission WAITING_EXTERNAL, SLEEPING from quiet hours.
- **External qualification required:** None.
- **Acceptance criteria:** JVM test on VanPresenceReducer maps each listed runtime signal to the action/state; reachability test lists no unproduced VanFiniteAction.

### GAP-F-013 — Speech output: sherpa-onnx TTS preference had no synthesizer; lip-sync/runtime path was incomplete

- **Priority:** P3
- **Audit-time status:** TEST_ONLY
- **Current closure (2026-09-22):** **FIXED_AND_EVIDENCED (repository) / DEVICE+EXTERNAL_ARTEFACT qualification pending**
- **Affected requirements:** REQ-VOI-03, REQ-VOI-04
- **Subsystem:** Android voice / gateway voice
- **Root cause:** RC-G (design artefact not wired)
- **Repository evidence now:**
  - `backend/van_gateway/voice/speech_cues.py` provides the production speech cue clock and the device consumes cue timing.
  - `android/.../voice/SherpaLocalTtsRuntime.kt` creates sherpa-onnx `OfflineTts`, synthesizes locally and plays VAN-owned PCM through `AudioTrack`.
  - The sherpa path emits measured PCM RMS frames, supports barge-in/stop and is released with the voice runtime.
  - `LocalTtsRouter` selects SHERPA_ONNX only when both the admitted LOCAL_TTS asset bundle and runtime self-test are ready; Android offline TTS remains the fallback.
  - `TtsOutputManager` executes the engine the router selected; JVM contracts assert sherpa preference/fallback semantics.
- **External qualification required:** Deploy the checksum-pinned local voice bundle and `voice/tts/runtime.json` to the owner S24; measure synthesis latency, offline speech, barge-in, RMS/viseme output and owner acceptance (QUAL-VOI-01/02).
- **Acceptance criteria:** Repository path is met. Live promotion requires the device receipt; absence of the bundle remains a truthful degraded state, not a repository gap.

### GAP-F-014 — Rive asset absent; silent Canvas fallback with no owner-visible notice

- **Priority:** P4  
- **Status:** EXTERNALLY_BLOCKED_REPOSITORY_COMPLETE  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 17f4fba, 5498a6f — visual/VanRendererStatus.kt via DegradedBridge.rendererStatus; Settings 'Character' row from DegradedBridge.lastRendererStatus  
- **Affected requirements:** REQ-EMB-05  
- **Subsystem:** Android visual / visual-authority  
- **Root cause:** External artefact (docs/EXTERNAL_GATES.md 'Artist .riv')
- **Evidence:**
  - find . -iname '*.riv' → none; android/app/build.gradle.kts:251 rive-android:9.6.5 present
  - android visual/VanVisualRuntime.kt:54-69 decide() → OWNER_ART/CANVAS on ASSET_MISSING; VanVisualRuntime.describe() (lines 71-80, doc-comment: reason is 'surfaced in diagnostics') has zero callers in android/app/src/main - the diagnostic is dead code
- **Dependent symptoms:**
  - Owner cannot tell whether the authored character is installed
- **Repository fix required:** Surface VanVisualRuntime.describe() in Settings/Systems as 'Character: Canvas fallback (Rive asset not installed)'.
- **External qualification required:** Authored van.riv from the Rive editor (QUAL-EMB-01).
- **Acceptance criteria:** Systems module shows the active renderer and reason.

### GAP-F-015 — Contradiction: AGENTS.md says Hermes may submit memory candidates; the MCP shim deliberately exposes no such tool

- **Priority:** P3  
- **Status:** CONTRADICTORY_IMPLEMENTATION  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits b78cbf4 — AGENTS.md, skills and Hermes README were reconciled to the expanded shim; PR #59 now pins an exact 51-tool shim/registration/REQUIRED_TOOLS set  
- **Affected requirements:** REQ-MEM-02, REQ-COH-02  
- **Subsystem:** hermes profile docs / MCP shim  
- **Root cause:** RC-A
- **Evidence:**
  - hermes/profile/van/AGENTS.md:12 'It may query canonical context, submit inferred/model-derived memory candidates'
  - hermes/mcp/owner_runtime_stdio.mjs:8 'Canonical owner-context admission is intentionally NOT exposed' and no tool for /v1/runtime/context/facts; backend/van_gateway/runtime_api.py:295-312 route exists with INFERRED/MODEL_DERIVED gate
- **Dependent symptoms:**
  - Dependent symptom of GAP-F-001
- **Repository fix required:** Decide one: add the INFERRED-only candidate tool to the shim, or amend AGENTS.md:12 and the runtime route's docstring.
- **External qualification required:** None.
- **Acceptance criteria:** AGENTS.md and TOOLS list agree; test_owner_runtime_mcp_contract asserts the decided state.

### GAP-F-016 — Interactive browser stream grant returns HTTP 200 with an empty signal_url when the signing key is set but the signal URL is not

- **Priority:** P3  
- **Status:** OPEN_GAP  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 1b6e44e — interactive_api.py mint_stream_grant → 503 BROWSER_STREAM_UNCONFIGURED without a stream host  
- **Affected requirements:** REQ-RES-05, REQ-BRW-04  
- **Subsystem:** gateway browser interactive api  
- **Root cause:** RC-D
- **Evidence:**
  - backend/van_gateway/app.py:521-529,831-870 interactive routers mount when browser_stream_signing_key_file is set
  - backend/van_gateway/browser/interactive_api.py:283 mint_stream_grant returns settings.browser_stream_signal_url unguarded
- **Dependent symptoms:**
  - Device would negotiate against an empty endpoint and report a transport error rather than a configuration error
- **Repository fix required:** Refuse (503 BROWSER_STREAM_UNCONFIGURED) when signal_url is empty; mount gate on both settings.
- **External qualification required:** Browser Stream Host (QUAL-BRW-03).
- **Acceptance criteria:** Test: signing key set, signal_url empty → 503.

### GAP-F-017 — Backend dependency set is floating (>=) while the trading VM is exact-pinned

- **Priority:** P3  
- **Status:** OPEN_GAP  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 1b6e44e — backend/requirements.lock; installers and CI install from the lock  
- **Affected requirements:** REQ-DET-03  
- **Subsystem:** backend/requirements.txt / deploy  
- **Root cause:** Determinism
- **Evidence:**
  - backend/requirements.txt: 10 of 11 lines use >= (fastapi, uvicorn, pydantic, httpx, cryptography, pytest, pytest-asyncio, aiosqlite, python-multipart, pydantic-settings); only playwright==1.63.0 exact
  - deploy/van-trading-core/requirements-vm.txt exact pins (fastapi==0.141.1, uvicorn==0.53.0, httpx==0.28.1, psycopg==3.2.9, temporalio==1.33.0)
  - tools/runtime/install_van_gateway_service.sh installs from backend/requirements.txt
- **Dependent symptoms:**
  - Two gateway installs from the same SHA can differ; CI and the certified host can diverge
- **Repository fix required:** Add a lock file (pip-compile/uv lock) consumed by CI and install_van_gateway_service.sh; record the lock hash in release metadata.
- **External qualification required:** None.
- **Acceptance criteria:** Contract test asserts every backend requirement is exact-pinned or locked.

### GAP-F-018 — require_device_binding defaults False with no release-time gate forcing it on

- **Priority:** P3  
- **Status:** OPEN_GAP  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 1b6e44e — config.py van_env + assert_production_safe(); tools/runtime/qualify_gateway_host.sh  
- **Affected requirements:** REQ-SEC-03  
- **Subsystem:** gateway config / qualification  
- **Root cause:** Determinism/security hardening
- **Evidence:**
  - backend/van_gateway/config.py:198-204 require_device_binding=False documented as 'mid-migration'
  - deploy/van-trading-core/qualify.sh and tools/ci/production_acceptance.py do not check it
- **Dependent symptoms:**
  - A production gateway can accept token-only mutations from an unbound device
- **Repository fix required:** Add a qualification check (qualify.sh / production_acceptance row) that fails unless VAN_REQUIRE_DEVICE_BINDING=true on release hosts.
- **External qualification required:** None.
- **Acceptance criteria:** qualify.sh RED when the flag is false on a release host.

### GAP-F-019 — Every derived context requirement is non-blocking; missing owner facts never block a consequential command

- **Priority:** P3  
- **Status:** PARTIAL_IMPLEMENTATION  
- **Closure (2026-09-22):** SUPERSEDED_BY_BETTER_IMPLEMENTATION — commits 528366b — Commands no longer block on missing owner context; context_gaps computed, returned in CommandResult, shown to the owner and passed to Hermes in canonical_context. Blocking a safety action on an unknown fact was the wrong contract.  
- **Affected requirements:** REQ-COG-02  
- **Subsystem:** gateway command/context_requirements  
- **Root cause:** RC-C
- **Evidence:**
  - backend/van_gateway/command/context_requirements.py:74,85,96,105 blocking=False for timezone, project predicates, action-family predicates and named people
- **Dependent symptoms:**
  - Dependent on GAP-F-001: with an empty kernel, blocking=True would deny everything; the design is therefore coupled to the missing producer
- **Repository fix required:** After GAP-F-001, make action-family requirements for trading./message. blocking=True with an owner-visible MISSING explanation.
- **External qualification required:** None.
- **Acceptance criteria:** A trading-family command with MISSING mandate facts returns needs_you with the missing requirement named.

### GAP-F-020 — Dead or orphaned production symbols

- **Priority:** P4  
- **Status:** IMPLEMENTED_NOT_REACHABLE  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits c193d47, 1b6e44e, b78cbf4 — _scrubbed() on every Google read; instruments wired or deleted; owner_approved removed; input_protocol retained (stream host caller)  
- **Affected requirements:** REQ-COH-05  
- **Subsystem:** gateway  
- **Root cause:** Coherence hygiene
- **Evidence:**
  - tools/audit/entrypoint_reach.py: van_gateway.browser.input_protocol never imported from app/orchestrator/runtime_api
  - tools/audit/reachability.py: observability/instruments.py set_browser_sessions_active, record_browser_connect, record_browser_input_dispatch, record_agent_grant and session/models.py store_dumps have no reference
  - backend/van_gateway/google/service.py:314-318 scrub_for_prompt called only from tests
  - backend/van_gateway/runtime_api.py:83 ActionBeginBody.owner_approved never read (by design; misleading)
- **Dependent symptoms:**
  - False confidence that scrubbing/telemetry is active
- **Repository fix required:** Wire or delete each; deprecate the dead request field.
- **External qualification required:** None.
- **Acceptance criteria:** reachability.py reports 0 NO_REFERENCE; scrub_for_prompt has a production call site or is removed.

### GAP-F-021 — Loopback defaults for Hermes and public base URLs have no fail-closed check

- **Priority:** P4  
- **Status:** OPEN_GAP  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 1b6e44e — production config refuses loopback/empty secrets  
- **Affected requirements:** REQ-DET-04  
- **Subsystem:** gateway config  
- **Root cause:** Determinism
- **Evidence:**
  - backend/van_gateway/config.py:14 hermes_base_url http://127.0.0.1:8642, :41 van_public_base_url http://127.0.0.1:8787; unlike ingress_token, no startup refusal when defaults are used off-host
- **Dependent symptoms:**
  - A misconfigured host silently talks to localhost
- **Repository fix required:** Require explicit values in the systemd env file (installer) and log/refuse defaults when VAN_ENV=production.
- **External qualification required:** None.
- **Acceptance criteria:** Installer fails without explicit VAN_HERMES_BASE_URL.

### GAP-F-022 — Whole-tree pytest collection collides on a duplicate test basename

- **Priority:** P4  
- **Status:** OPEN_GAP  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 1b6e44e — tests/contracts/__init__.py; root collection no longer collides  
- **Affected requirements:** REQ-TST-01  
- **Subsystem:** tests  
- **Root cause:** Test hygiene
- **Evidence:**
  - tests/contracts/test_owner_device_provisioning.py vs backend/tests/test_owner_device_provisioning.py → 'import file mismatch' when collected together (reproduced); CI avoids it by running per directory
- **Dependent symptoms:**
  - A whole-tree run reports 0 tests; auditors can misread this as a broken suite
- **Repository fix required:** Rename one file or add __init__.py/importmode=importlib in pytest.ini.
- **External qualification required:** None.
- **Acceptance criteria:** `pytest` from the repo root collects all suites.

### GAP-F-023 — Mutation harness is not in CI and there are no Android instrumentation tests

- **Priority:** P4  
- **Status:** PARTIAL_IMPLEMENTATION  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED (mutation, instrumentation job) / EXTERNALLY_GATED_REPOSITORY_COMPLETE (device sign-off) — commits 1b6e44e, a60b009 — van-ci.yml mutation job (non-blocking, report uploaded); android-instrumentation job on an API 31 emulator running src/androidTest CommandCentreLaunchTest + FloatingOverlayServiceTest (advisory; report uploaded). Real-device certification remains QUAL-AND-01.  
- **Affected requirements:** REQ-TST-02, REQ-TST-03  
- **Subsystem:** CI / android  
- **Root cause:** Test coverage
- **Evidence:**
  - tools/audit/mutation.py not referenced by .github/workflows/van-ci.yml
  - android/app/src/androidTest is empty; only 28 JVM test files (147 @Test)
- **Dependent symptoms:**
  - Overlay, permissions, wake pipeline, biometric prompt behaviour are certified only by device checklist
- **Repository fix required:** Schedule mutation.py as a non-blocking CI job; add a minimal androidTest set (overlay service start, share intake, notification listener) run on CI emulator.
- **External qualification required:** Emulator/device (QUAL-AND-01).
- **Acceptance criteria:** CI shows both jobs.

### GAP-F-024 — Google connect/revoke and Google actions have no owner-device surface

- **Priority:** P3  
- **Status:** BACKEND_ONLY  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits c193d47, 5498a6f — POST /v1/google/owner-revoke (device-proofed); test_google_owner_revoke_and_scrub.py; Connected screen Revoke Google with confirm  
- **Affected requirements:** REQ-GOO-05, REQ-AND-12  
- **Subsystem:** Android / gateway google  
- **Root cause:** RC-B
- **Evidence:**
  - android: only GET /v1/google/mesh (VanGatewayClient.kt:310) rendered as read-only text in AdminModules.kt:37-92; no connect/revoke call
  - backend/van_gateway/app.py:2100-2113 /v1/google/connect and /revoke are internal-control routes; OAuth is completed by tools/google/authorize_workspace_oauth.py on the host
  - Google actions are reachable only through Hermes shim tools; the owner cannot directly ask the phone to draft/send (design: Hermes-mediated)
- **Dependent symptoms:**
  - Owner cannot revoke Google from the phone when a token is compromised; Flow 2 depends on Hermes calling google_calendar_agenda
- **Repository fix required:** Add a device-authenticated POST /v1/google/revoke (owner-device scope, device-proofed) and a Connections module action; keep connect on the host.
- **External qualification required:** None.
- **Acceptance criteria:** Revoke from the phone sets google_connections status revoked and /v1/google/status reports disconnected.

### GAP-F-025 — Two definitions of Google readiness

- **Priority:** P3  
- **Status:** CONTRADICTORY_IMPLEMENTATION  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 1b6e44e — google/mesh.py EXECUTION_READY_STATES single predicate  
- **Affected requirements:** REQ-GOO-04, REQ-COH-02  
- **Subsystem:** gateway google mesh / capability readiness  
- **Root cause:** RC-D
- **Evidence:**
  - backend/van_gateway/google/mesh.py:290 USABLE_STATES = {READY, CONFIGURED}
  - backend/van_gateway/capability/readiness.py:44-67 is_ready requires READY only (rule 'CONFIGURED is not READY', docs/EXTERNAL_GATES.md)
- **Dependent symptoms:**
  - The router may plan a job on a CONFIGURED capability that the readiness surface reports not ready
- **Repository fix required:** Make the router use GoogleMeshReadiness (or document CONFIGURED as plan-only, never execute).
- **External qualification required:** None.
- **Acceptance criteria:** One predicate; test asserts CONFIGURED capabilities cannot be executed.

### GAP-F-026 — Temporal execution medium was routed but had no executor

- **Priority:** P4
- **Audit-time status:** STUB_OR_PLACEHOLDER
- **Current closure (2026-09-22):** **FIXED_AND_EVIDENCED (repository) / EXTERNAL live runtime pending**
- **Affected requirements:** REQ-AUT-04
- **Subsystem:** gateway automation router / van-trading-core durable runtime
- **Root cause:** The phase-11 stack lock had been treated as permission to leave the selected medium unimplemented.
- **Repository evidence now:**
  - `automation/router.py` still deterministically selects TEMPORAL for `critical_durable`, but reports whether the bridge is actually configured.
  - `automation/temporal_bridge.py` exposes scoped start/status/signal routes and fails closed when the deployment bridge is absent.
  - `deploy/van-trading-core/temporal/workflows.py` implements `VanDurableWorkflow` with replay-safe state, checkpoints, signals, durable waits and terminal outcomes.
  - `deploy/van-trading-core/temporal/runtime.py` runs a Temporal client/worker plus a private token-authenticated bridge and writes token-free lifecycle evidence.
  - `vati-temporal.service`, bootstrap and `qualify.sh` stage/qualify the runtime; `temporalio==1.33.0` is pinned.
  - Hermes exposes `temporal_start`, `temporal_status` and `temporal_signal`; the fixed MCP allowlist contract includes them.
- **Authority constraint:** Temporal owns durable coordination only and explicitly does **not** execute live orders or grant owner/trading authority.
- **External qualification required:** Supply and operate a real Temporal server address, enable `vati-temporal.service`, then record start → restart/recovery → checkpoint → terminal-result evidence (QUAL-AUT-02).
- **Acceptance criteria:** Repository executor exists and fails closed without its host. Live promotion requires the external Temporal canary.

### GAP-F-027 — Overlay state persisted in plain SharedPreferences

- **Priority:** P4  
- **Status:** OPEN_GAP  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits 5498a6f, b46ca65 — OverlayStateStore and browser session store on EncryptedSharedPreferences; tests/contracts/test_android_storage_policy.py explains the three remaining non-sensitive plain writers  
- **Affected requirements:** REQ-AND-05  
- **Subsystem:** Android overlay  
- **Root cause:** Consistency
- **Evidence:**
  - android overlay/OverlayStateStore.kt uses SharedPreferences MODE_PRIVATE (position, presentation, dock, running flag); every other store uses EncryptedSharedPreferences/Keystore
- **Dependent symptoms:**
  - None security-relevant (no secrets)
- **Repository fix required:** Migrate to EncryptedSharedPreferences for uniform policy.
- **External qualification required:** None.
- **Acceptance criteria:** No plain SharedPreferences writers remain (JVM contract test).

### GAP-F-028 — No proactive initiation path: VAN never opens an attention item or mission without an owner command or an external event

- **Priority:** P2  
- **Status:** PARTIAL_IMPLEMENTATION  
- **Closure (2026-09-22):** FIXED_AND_EVIDENCED — commits b952b40 — proactive/followups.py ProactiveFollowUpJob + scheduler job proactive.follow_ups; owner-disableable; test_proactive_followups.py  
- **Affected requirements:** REQ-SYM-06, REQ-SYM-11  
- **Subsystem:** gateway proactive / scheduler  
- **Root cause:** RC-C
- **Evidence:**
  - backend/van_gateway/proactive/autonomy.py:295 ProactivePolicyService.may_create() is the gate for VAN starting a mission unprompted; it has no caller outside its module and tests. No OpsScheduler job (app.py:729-754: reminders.fire_due, missions.expire_overdue, ops.retention, ops.pki_scan, ops.backup, ops.backup_drill, learning.auto_demote, understanding.mark_stale_intents) or route initiates proactive work; understanding/api.py:98 only reads .policies()
  - Reactive producers exist: reminder sweep → attention; notification ingest → attention; browser escalation → decisions
- **Dependent symptoms:**
  - 'Anticipate useful follow-ups' (audit brief §8) has no engine; VAN is reactive
- **Repository fix required:** Add a bounded proactive job: stale intents / unresolved attention / expired missions → FOLLOW_UP attention items under ProactivePolicy ceilings, never executing actions.
- **External qualification required:** None.
- **Acceptance criteria:** A mission left WAITING_FOR_OWNER > N hours yields a FOLLOW_UP attention item produced by the proactive job.

---

## Post-closure product reconciliation — 2026-09-22

The phrase “zero repository gaps” in the original Fable closure referred only to its 28-item
register. A follow-up owner/product review correctly identified additional omissions that were
not represented by those 28 IDs. They are now tracked explicitly rather than hidden by that
phrase:

| ID | Product omission discovered after Fable closure | Repository disposition | Remaining live gate |
|---|---|---|---|
| PROD-F-001 | Attention snooze gesture had no backend mutation route | **FIXED_AND_EVIDENCED** — durable `AttentionEngine.snooze`, POST route, Android client + swipe caller, route test | Device UX acceptance |
| PROD-F-002 | Keyboard/full-screen obstruction policy had no producer | **FIXED_AND_EVIDENCED** — `VanObstructionAccessibilityService`, manifest/config, overlay consumer/repositioning, onboarding + Settings state | Owner grants Accessibility permission; S24 behavior check |
| PROD-F-003 | Trading History lacked an equity/R curve model | **FIXED_AND_EVIDENCED** — VATI server read model emits cumulative R/P&L curves; Android parses and renders them | Live trading history data |
| PROD-F-004 | Local sherpa TTS was classified but not implemented | **FIXED_AND_EVIDENCED (repository)** — `OfflineTts` + VAN-owned PCM path | Voice bundle + S24 qualification (QUAL-VOI-02) |
| PROD-F-005 | Temporal was named as a durable medium but had no executor | **FIXED_AND_EVIDENCED (repository)** — bridge, workflow, worker, service, bootstrap, qualifier, Hermes tools | Real Temporal server + live recovery canary (QUAL-AUT-02) |

These product rows are also enforced by `tools/audit/fable_anti_gap_check.py` so a future
closure cannot regress them without CI evidence.

