# VAN — Fable-managed whole-project functionality, completeness, determinism, coherence and symbiotic-integration audit

| | |
|---|---|
| Repository | `Vanguduza/Van` |
| Branch | `claude/van-fable-forensic-audit-ds8g0o` |
| HEAD audited | `0067d55071342b963293d0724f5a1604d233d105` (`chore: remove one-time VAN runtime branch prune workflow`) |
| Working tree at start | clean (`git status --porcelain` empty) |
| Date | 2026-09-21 |
| Declared version | `0.5.0-dev` (VERSION, hermes/VERSION, Android versionName agree) |
| Manager | Fable (final classification, reconciliation, personal inspection of authority/architecture paths) |
| Workers | 12 bounded Sonnet agents (gateway auth, Hermes path, Android core, Android voice/visual, cognition/memory, trading/VATI, browser/automation, Google, resilience, test evidence, reachability/config/coherence, adversarial anti-gap) |
| Companion artifacts | `VAN_REQUIREMENT_TRACEABILITY_MATRIX.md` (119 requirements), `VAN_CANONICAL_GAP_REGISTER.md` (+`.json`, 28 gaps), `VAN_RUNTIME_QUALIFICATION_MATRIX.md` (33 gates), `VAN_EXECUTION_PATH_EVIDENCE.md` (15 flows), `VAN_SYMBIOTIC_INTEGRATION_AUDIT.md` |

No production code was modified. Only this directory was added.

> **Historical audit snapshot — not current repository truth.** The findings below describe
> audited commit `0067d55` before remediation. References such as the 30-tool Hermes shim,
> absent memory producer/invoker, floating backend pins, and missing product paths are retained
> as forensic provenance. Current repository state is represented by
> `VAN_FABLE_IMPLEMENTATION_CLOSURE_REPORT.md`, `VAN_REQUIREMENT_TRACEABILITY_MATRIX.md`
> and `VAN_RUNTIME_QUALIFICATION_MATRIX.md`.

---

## 1. Executive summary

**Repository completeness.** VAN is a large, unusually well-guarded codebase: a 78k-line FastAPI gateway with 56 SQLite tables and 28 ordered migrations, a 48k-line Kotlin/Compose Android app, a 29k-line deterministic trading system (VATI) with a Hermes commander, browser/automation fabric, and a Hermes profile pack. Every test suite is green at this commit (backend 1595, contracts 365, services 116, hermes/policy/scenarios 88, trading 1143; 5 environment-gated skips, 0 xfail) and every static truth gate the repository runs in CI passes (maturity gate, authority map, ledger reconcile, production acceptance, red-team register, trading architecture guardrails, Rev 5.1 harness, Kotlin reachability). There are no TODO/FIXME/NotImplemented markers in production code.

**Functional reachability.** Of 119 canonical requirements traced, **58 are integrated and evidenced**, **15 are repository-complete behind an external gate**, **3 need only live certification**, and **43 have a repository-side defect** (22 partial, 7 implemented-but-unreachable, 5 open, 3 backend-only, 3 contradictory, 2 UI-only, 1 deliberate stub).

**Integrated product behaviour.** The authority model is coherent and correctly enforced: one middleware choke point, device-bound principals, biometric ECDSA approvals that no field can forge, hash-chained audit, missions that cannot self-assert success, a Risk Authority that is provably the only sizing path, and no Android→provider bypass. What is *not* coherent is the **Hermes tool surface**: the 30-tool MCP shim is narrower than the authority model, the canonical docs and the Hermes skills. Hermes cannot read trading state, cannot start browser or automation work, cannot propose memory, and cannot execute the one typed trading action (halt) the resolver knows.

**Determinism.** Deployment is pinned to an exact certified SHA with a clean-tree check (Trading Core); model selection is pinned; migrations are ordered; idempotency and nonces are transaction-atomic; release builds fail closed without HTTPS/keystore/trust anchor. Residual nondeterminism: floating backend dependency pins, loopback URL defaults with no fail-closed check, `require_device_binding` default off with no release gate.

**Symbiotic intelligence.** The observe→…→learn loop is designed end to end and eight of ten links are implemented, but it **does not close**: owner memory has no conversational producer (the kernel is asked on every command and is always empty), learning stores are write-only for the owner-agent runtime, and there is no proactive initiation. VAN today is a governed reactive executor with a real attention engine, not yet a persistent extension of the owner.

**Runtime qualification.** 33 external/runtime gates; 5 live-certified with token-free receipts (Workspace OAuth, Stitch, Antigravity, exact-SHA Trading Core deployment, loopback gateway); 19 pending live proof; 4 blocked on repository gaps; 5 device/owner-deployment/artefact. The gateway→Hermes run contract (`POST /p/van/v1/runs`), the shim invocation and the `mission_result` callback have **never been observed live**.

**Remaining coding gaps: 28** (0 P0, 5 P1, 5 P2, 11 P3, 7 P4). **External gates: 33.**

**Another implementation pass is required** before VAN can perform its intended mission. Priority order: memory/reminder producers (GAP-F-001/002), Hermes tool surface for trading reads, browser/automation initiation and halt execution (GAP-F-003/006/005), learning read-back and proactive job (GAP-F-008/028), health catalog and scoped-token coherence (GAP-F-007/009).

---

## 2. Methodology

1. Recorded repository state; read `PROJECT_CANONICAL_STATE.json`, `README.md`, `docs/EXTERNAL_GATES.md`, prior closure artifacts (`docs/audit/van-whole-project-2026-09-21/21_GAP_REGISTER.json`, `evidence/van-system-audit/*`) and treated them as hypotheses only.
2. Built the subsystem inventory (route table across 10 routers = 196 routes; 209-component ledger; Android manifest components) and launched 11 bounded read-only workers in parallel, each required to return scope / evidence / proven / suspected / false-positives / uncertainty.
3. Personally traced the authority and architecture seams: the orchestrator dispatch payload, the Hermes bridge contract, the MCP shim tool list, memory producers, the reminder path, the trading halt executor, the VATI cognition invoker, the mission→owner result path, and the degraded catalog.
4. Reproduced two findings against the real application (`create_app()` under ASGI): `/health` 500 on `OWNER_CONTEXT_UNAVAILABLE`, and scoped-only internal credentials refused with 503.
5. Ran every test suite the way CI runs them (per directory) and every CI static gate.
6. Ran a 12th adversarial worker against the manager's 13 preliminary claims and five hunts; all 13 confirmed (one wording refined), one additional dead diagnostic found.
7. Classified every requirement and gap personally; workers proposed, Fable decided.

Chain applied to every capability: requirement → implementation → instantiation → registration → production caller → authority boundary → data/control flow → executor → observable result → persistence/audit → failure handling → recovery → tests/evidence.

---

## 3. Architecture discovered from code

```
Owner S24 (android/app)                       dial-hermes-control host
 ┌──────────────────────────────┐             ┌──────────────────────────────────────────────┐
 │ FloatingOverlayService       │  HTTPS      │ van-gateway (FastAPI, 127.0.0.1:8787)         │
 │ Command Centre (17 modules)  │ ─────────▶  │  middleware: ingress + device token + HMAC    │
 │ WakeListener → SpeechRecog.  │  WSS/SSE    │  orchestrator → idempotency → nonce → resolve │
 │ NotificationListener/Share   │ ◀─────────  │  → trust → mission → A4 → snapshot → seal     │
 │ EncryptedCommandQueue        │             │  → HermesBridge POST /p/van/v1/runs ──────────┼──▶ Hermes profile van (external, Sonnet 5)
 │ VanHermesSessionManager (WS) │             │  runtime_api /v1/runtime/* ◀─── MCP shim ◀────┼─── owner_runtime_stdio.mjs (30 tools)
 │ Trading/Browser activities   │             │  mission/verification/events → device stream  │
 └──────────────────────────────┘             │  google/* → googleapis (Workspace OAuth vault) │
                                              │  browser/*, automation/* (flags off, no caller)│
                                              │  trading/* read models ← VATI ledger          │
                                              └──────────────────────────────────────────────┘
 van-trading-core VM: vati-session@ (DecisionCycle → RiskAuthority → ExecutionRouter → MT5/Deriv/cTrader/paper),
   vati-commander (mTLS, HMAC principals; Hermes tools: status/ledger/services/backtest/halt/doctor/accounts),
   vati-mt5-pull, vati-calendar.timer, Supabase/Postgres ledger, browser harness + stagehand workers, n8n stack
 Browser Stream Host (deploy/van-browser-stream): not provisioned anywhere
```

Authority planes as implemented: **Android** = owner intent, approvals, presentation (no execution authority; verified no direct provider calls). **Gateway** = authentication, principal binding, typed resolution, context sealing, authority records, verification, audit. **Hermes** = reasoning and execution through a fixed tool allowlist; reports lifecycle, never success. **VATI** = exclusive sizing/execution authority (`risk/authority.py` → `execution/router.py:226` single `submit` caller); Hermes may only propose and cannot even read positions. **Browser/automation fabric** = actuation without authority; complete but uninitiated.

---

## 4. Functionality findings

### 4.1 Gateway authority (INTEGRATED_AND_EVIDENCED, with two coherence defects)
- One choke point `require_ingress_auth` (app.py:1248-1333); `control_scope_for` (1056-1125) classifies every route; unauthenticated allowlist is exactly pair/bootstrap/trading-OAuth-callback.
- Principal cannot be spoofed: `principal_type`, `requested_by`, `device_id`, nonce, expiry and trust are inside the HMAC canonical string and re-checked for equality (orchestrator.py:180-210); `client_context` is forwarded as non-authoritative.
- A4 approvals are ECDSA-P256 over a server-minted challenge, consumed once under `BEGIN IMMEDIATE`; `OwnerApprovalProof` has no boolean; `ActionBeginBody.owner_approved` is ignored (verified by test and code).
- Defects: six routers check only the legacy token (GAP-F-009, reproduced); `require_device_binding` defaults off with no release gate (GAP-F-018).

### 4.2 Hermes integration (INTEGRATED in-process; RUNTIME_CERTIFICATION_REQUIRED live)
- Outbound: `HermesBridge.create_run` posts `{profile, input, metadata}` to `/p/van/v1/runs` with `canonical_context` (snapshot id, digest, fact_ids, refs), typed resolution and sealed authority flags. No retry; offline → degraded; dispatch error → idempotency FAILED (resend allowed).
- Inbound: 35 `/v1/runtime/*` routes; `POST /missions/result` projects lifecycle onto the mission; VERIFIED_SUCCESS is structurally unreachable without a verifier record. Proven by `test_command_execution_result`.
- The shim maps 30 tools 1:1 to real routes and is contract-tested by running Node. It contains **no** tool for memory candidates, reminders, attention, trading reads, browser assignments, automation, or trading halt. `hermes/mcp/README.md:10` documents a `van-gateway` MCP server that does not exist.
- `session/*` (`VanHermesSession`) is the owner-device↔gateway transport, not a Hermes protocol; the name misleads.
- Live: profile installed and a model turn certified 2026-09-15; no receipt for the run API, the shim invocation, or the callback.

### 4.3 Cognition, memory and context
- Kernel: 56 tables, epistemic tiers, validity windows, provenance, export/erase, lexical + graph retrieval (no embeddings), hot capsules, readiness, immutable snapshots. `compile_snapshot` is called on every command.
- **Producers:** CANONICAL_OWNER via `POST /v1/context/facts` — no Android caller; INFERRED via `/v1/runtime/context/facts` — no shim tool; PROJECT_TRUTH via `PUT /v1/projects/{id}/truth` — real (`tools/projects/sync_project_truth.py`). Hence the kernel is empty of owner facts in any deployment (GAP-F-001, P1).
- Every derived requirement is `blocking=False` (GAP-F-019).
- Deterministic critic and assumption ledger are real; the assumption gate is on the `/actions/begin` path (25 tests). The premises route has no caller.
- No model call anywhere in the gateway (verified by grep and by `test_cognition_is_real`).

### 4.4 Attention, notifications, reminders, briefing
- One engine (P2-COH-002 merge verified): `NotificationIntelligence.ingest_durable` → `AttentionScorer` (five dispositions) → `AttentionEngine.upsert` (dedupe, budget, snooze, ack) → `/v1/attention`, `/v1/briefing`, `attention.upserted` event. Device notifications and shares reach it through `/v1/context/ingest` as UNTRUSTED_EXTERNAL.
- Reminders: sweep, firing and briefing consumers are real; **no creation path exists in production** (GAP-F-002, P1).
- Decisions: producer is the browser boundary escalation only; Android resolves with `resolveDecision(id, bool)` (no biometric; escalations cannot widen past A3 by code).

### 4.5 Android embodiment
- Overlay service, drag/dock/presentation reducers, boot/replace recovery, foreground notification, encrypted queue (AES-GCM Keystore, `commit()`), kind-based replay routing, circuit breaker and jittered retry, real OkHttp WebSocket session with durable outbox, 17 Command Centre modules all rendering live gateway data (no fixtures found; no no-op buttons found in the five modules inspected).
- Visual state machine is real: producers are gateway response status, voice callbacks, browser stream state and degraded truth. Aura is semantic and clock-driven with reduced-motion and effect-budget paths.
- Not produced: all 14 `VanFiniteAction` gestures and the `URGENT`/`WAITING`/`SLEEPING` states (GAP-F-012). No `.riv` in the repository; Canvas fallback silent, `describe()` dead (GAP-F-014).
- Android never reads `/v1/degraded`; backend degraded codes are not mapped (GAP-F-010). Chat never receives completion (GAP-F-011). Overlay position stored unencrypted (GAP-F-027).

### 4.6 Voice
- Wake (sherpa-onnx two-stream KWS, checksum-pinned bundles, fail-closed → degraded `wake_word`), on-device `SpeechRecognizer`, local second-pass ASR, speaker similarity (support only), deterministic fusion, `submitText(source=VOICE)` → `/v1/commands`, re-arm only for wake-originated turns, barge-in marks segments INTERRUPTED. Backend `speech_stream.py` cursors/resumes segments.
- Output is Android `TextToSpeech` only; sherpa TTS preference is policy without engine; visemes are `frame % 10`; `SpeechCueClock` exists only in a test (GAP-F-013).

### 4.7 Trading / VATI
- Risk Authority is a 13-stage fail-closed gate with sealed decision hashes; `ExecutionRouter.execute` is the only `adapter.submit` caller (grep-verified across MT5, Deriv, paper; cTrader shares the same single caller); owner acts are ECDSA with act/subject binding, expiry and nonce; commander commands are allow-listed and `requested_by` is overridden by the verified HMAC principal; cognition contracts refuse order fields and run after the decision; calendar blackout wired; capsule_health learning read-back is real and bounded ≤ 1; MT5 Windows worker and signed pull protocol complete; gateway read models read the ledger directly; strategy promotion from Android is biometric- and owner-key-gated.
- Defects: no Hermes read path to positions (GAP-F-003, P1); shadow cognition has no invoker anywhere (GAP-F-004, P2); typed `trading.halt` has no executor and the owner has no halt surface (GAP-F-005, P1); no news path beyond the calendar.

### 4.8 Browser and automation
- Real implementations: Harness service (headless Chromium + browser-harness 0.1.13), Stagehand 4.1.0 worker with secretref model key, `HybridBrowserWorker`, policy engine (deny-until-admitted domains, secret refusal, injection grading), boundary escalation with single-use scoped resume, n8n management client, dispatcher chain authorize→begin→grant→run→verify, mission binder, signed webhook ingress. All flags default off and every mutation route 503s when off.
- Defect: no production initiator — no Hermes tool, Android read-only, `/v1/automation/*` 13 routes without any caller (GAP-F-006, P1). Stream grant returns 200 with empty `signal_url` (GAP-F-016). Temporal routed but not built (GAP-F-026, deliberate).

### 4.9 Google
- Workspace: encrypted refresh vault, scope allowlist, real `googleapis` transport, mutations only via AUTHORIZED executions with digest and readback, internal-control scope on every mutating route, live READY canaries. Hermes reaches Google only through nine shim tools.
- Registry-only capabilities (Gemini family, Notebook personal, Mixboard, Stitch, Antigravity, Jules, Nano Banana, Veo, ADK/A2A) execute on Hermes with attestation evidence only; three have `executor: null`.
- Defects: two readiness predicates (GAP-F-025); `scrub_for_prompt` unused (GAP-F-020); no owner-device connect/revoke (GAP-F-024).

---

## 5. Determinism findings

| Area | Finding | Status |
|---|---|---|
| Deployment | `rebuild-van-trading-core.py` resolves one SHA; `bootstrap.sh` requires 40-hex `--commit-sha`, detached checkout + hard reset; `qualify.sh` RED unless HEAD == expected SHA and tree clean | INTEGRATED |
| Version traceability | `PROJECT_CANONICAL_STATE.json` required ancestors; `tools/release/generate_release_metadata.py`; 21_GAP_REGISTER pins PR #55 head + CI runs | INTEGRATED |
| Dependencies | VM exact-pinned; **backend floating `>=`**; Android digests pinned by contract test; CI actions pinned to major tags | PARTIAL (GAP-F-017) |
| Model selection | `anthropic/claude-sonnet-5` pinned; Gemini barred from overriding; no fallback logic in the gateway | INTEGRATED |
| Config precedence | pydantic-settings env + `.env`; tokens fail closed; **loopback URL defaults unguarded**; `require_device_binding` default off | PARTIAL (GAP-F-018/021) |
| Migrations | sorted, gated by `schema_migrations`, one commit each | INTEGRATED |
| Idempotency / replay | client key inside signed envelope + payload hash; atomic claim; stale lease 15 min; nonce single-use; session frame digest dedupe; epochs | INTEGRATED (Hermes-side dedupe external) |
| Endpoint discovery | build-time constant + signed connectivity manifest with compiled trust anchors; setter private | INTEGRATED |
| Feature flags | 10 flags all default off (automation, browser, VEKL, Obsidian, Notebook×2, Exa, backup…) | INTEGRATED |
| Test determinism | whole-tree pytest collection collides (duplicate basename) | GAP-F-022 |

---

## 6. Coherence findings (contradiction register)

| # | Contradiction | Evidence | Gap |
|---|---|---|---|
| CR-1 | AGENTS.md says Hermes may submit memory candidates; shim says admission is intentionally not exposed | AGENTS.md:12 vs owner_runtime_stdio.mjs:8 | GAP-F-015 |
| CR-2 | README/skills describe a `van-gateway` MCP server and browser/automation/trading-intelligence capabilities; no such tools exist | hermes/mcp/README.md:10; skills/trading-intelligence, browser-intelligence, automation-fabric | GAP-F-003/006 |
| CR-3 | Two internal-control checks (scoped middleware vs legacy router check) | app.py:1335 vs six `_require_internal` | GAP-F-009 |
| CR-4 | Two Google readiness predicates | mesh.py:290 vs capability/readiness.py:44-67 | GAP-F-025 |
| CR-5 | `DegradedCode` (35) vs `CATALOG` (26) | models.py vs degraded/registry.py | GAP-F-007 |
| CR-6 | Android degraded vocabulary vs gateway codes | DegradedMode.kt:47-66 | GAP-F-010 |
| CR-7 | Cognition read model advertises a model hierarchy while no invoker exists | trading/cognition.py:14 vs account_service.py:178 | GAP-F-004 |
| CR-8 | `VanHermesSession` name vs owner-device transport role | session/models.py:1-19 | documentation only |
| CR-9 | Rive contract lists gestures/states with no runtime producer | RiveContract.kt vs producers | GAP-F-012 |
| CR-10 | `LocalTtsRouter` prefers an engine that does not exist | LocalTtsRouter.kt:63-141 | GAP-F-013 |

Verified **not** contradictory: owner-status vocabularies (total, CI-enforced mapping, 8 tests pass); attention engines (merged); mission/command/wire statuses (single projection); the two named blueprint docs (self-labelled plans/reviews, cited routes exist).

---

## 7. Resilience and security findings

- Fail-closed startup (migrate + secret rehydration unguarded → loud failure); WAL + busy timeout; per-job scheduler isolation with persisted due-times; backup/restore drill compares row counts, schema and audit tip; systemd restart on failure (no watchdog).
- All Hermes failure branches degrade visibly; no silent-success branch found. Recovery matrix (26 tests) covers restart mid-claim, restart after dispatch, connectivity loss after mutation, duplicate callbacks, process death awaiting approval, trading state change during approval — at the service layer only.
- **Defect:** `/health` and `/v1/degraded` return 500 while `OWNER_CONTEXT_UNAVAILABLE` is active (reproduced) → Android shows "gateway broken" during a context-store fault (GAP-F-007).
- Security review found no principal spoofing, no approval forgery, no secret logging (systematic redaction), no token in responses (pair echoes the shared ingress bearer by design with `no-store`), no biometric bypass, no trading risk bypass, no webhook acceptance without signature (unsigned → PROVIDER_UNSIGNED evidence only), immediate revocation. Residual: scoped-credential gap pushes operators toward one shared token (GAP-F-009); device binding off by default (GAP-F-018).

---

## 8. Testing findings

- 38 of 100 backend test files drive the real app through ASGI; only `hermes.health/create_run` are monkeypatched; no `unittest.mock` anywhere; hand-written fakes are confined to the LLM boundary and a hard-gated Google fake transport.
- Contract tests guard machine-readable registers with adversarial self-tests (checker must reject corrupted registers). The weakest is `test_reconstructed_gap_register.py` (arithmetic self-consistency of a hand-reconstructed document).
- CI builds, unit-tests, lints and uploads the debug APK (`if-no-files-found: error`), renders visual evidence, runs every Python suite and every truth gate; no `continue-on-error`.
- False-confidence risks: tests can pass while a feature is unreachable (the whole GAP-F-001/002/003/005/006 family is green); `test_speech_sync.py` tests a class that exists only inside itself; mutation harness not in CI; no instrumentation tests.

---

## 9. External gates

33 gates in `VAN_RUNTIME_QUALIFICATION_MATRIX.md`. Load-bearing ones: Hermes run API + shim invocation + callback (QUAL-HERMES-01/02), S24 device checklist (QUAL-AND-01), release signing + provisioning (QUAL-AND-02), named tunnel (QUAL-AND-03), voice bundles (QUAL-VOI-01), `.riv` (QUAL-EMB-01), Harness/Stagehand/n8n/stream host (QUAL-BRW-01..04, AUT-01), live feed + broker + owner key (QUAL-TRD-01..03), Gemini credits (QUAL-GOO-02).

---

## 10. Root-cause gaps

| Root cause | Statement | Dependent gaps |
|---|---|---|
| RC-A | Hermes tool surface narrower than the authority model and canonical docs | GAP-F-001 (part), 003, 005 (part), 006, 015 |
| RC-B | Gateway write surfaces with no owner-side producer | GAP-F-001, 002, 005, 024 |
| RC-C | Learning/calibration/proactive/requirement stores never consumed by a decision | GAP-F-008, 019, 028 |
| RC-D | Enum/catalog/predicate drift without exhaustiveness tests | GAP-F-007, 009, 010, 016, 025 |
| RC-E | External dependency declared in a comment with no injection point | GAP-F-004 |
| RC-F | UI surfaces do not consume runtime signals that exist | GAP-F-011, 012 |
| RC-G | Design artefacts left unwired | GAP-F-013, 020 |

Fixing RC-A and RC-B (five shim tools, two typed actions, one Android module, one executor) closes all five P1 gaps and two of the P3 gaps.

---

## 11. Final evidence-backed conclusion

**What can VAN actually do today (with valid credentials and infrastructure)?** Pair a device with restart-durable, revocable, HMAC-bound credentials; accept a typed or spoken owner command; classify, seal context and authority, open a durable mission and dispatch it to Hermes; let Hermes read Gmail/Calendar/Drive/Contacts/Tasks and knowledge providers, execute Google and Notebook mutations only through authorized, digest-bound, read-back-verified actions; reconcile the run into a verified/unverifiable/failed mission visible in Activity and Missions; capture notifications and shares as untrusted context into one attention engine with quiet hours and budget; brief the owner deterministically; show the trading book and promote strategies under biometric and owner-key authority; trade deterministically under the Risk Authority with a real post-trade learning multiplier; fail visibly when Hermes, Google or the ledger is unavailable.

**Which intended capabilities are genuinely reachable?** 58 of 119 (see §1) plus 15 repository-complete behind external gates.

**Present but disconnected?** Owner memory writers, reminder creation, trading reads for Hermes, browser assignments, automation routes, boundary escalation, trading halt execution, VATI shadow cognition, learned-strategy read-back, calibration, proactive policy, embodiment gestures/URGENT, stream grant guard, degraded catalog entries, scoped credentials in six routers.

**Unimplemented?** Conversational memory capture, reminder capture, news-to-thesis reasoning, proactive follow-up initiation, local TTS engine, instrumentation tests.

**Awaiting external qualification only?** Voice bundles, `.riv`, device checklist, release signing/provisioning, named tunnel, Harness/Stagehand/n8n/stream host, live feed/broker/owner key, Gemini credits, Notebook Enterprise plane, VEKL/Obsidian/Exa.

**One coherent authority model?** Yes — gateway seals authority, Hermes proposes, VATI sizes, Android approves — with two coherence defects in credential scoping and readiness predicates.

**Owner intent preserved across models/agents/sessions/executors?** Yes for missions, authority records and snapshots; no for owner facts (never written).

**Does memory affect future reasoning?** Mechanically yes (fact ids sealed into every dispatch); materially no (the kernel holds no owner facts).

**Do actions and outcomes feed back?** Trading: yes. Owner agent: recorded but never read.

**Can VAN observe, reason, delegate, act, reconcile and learn as one system?** Observe, delegate (Google/knowledge), act, reconcile: yes. Reason over trading/browser/automation: no. Learn: no.

**Persistent digital extension of the owner rather than a collection of integrations?** Not yet. The integration seams are correctly designed and governed, but the intelligence layer is disconnected from memory capture, from the trading and execution planes, and from its own learning stores.

**If VAN were installed on the target device with all external credentials/services valid, what exact remaining repository defects would prevent it from performing its intended mission?** The five P1 items plus one P2: GAP-F-001 (no memory producer), GAP-F-002 (no reminder producer), GAP-F-003 (Hermes cannot read trading state), GAP-F-005 (halt has no executor), GAP-F-006 (no browser/automation initiator), and — for operability under fault — GAP-F-007 (health 500). Everything else is refinement or live certification.
