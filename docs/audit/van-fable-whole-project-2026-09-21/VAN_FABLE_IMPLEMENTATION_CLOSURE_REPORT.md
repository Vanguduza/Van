# VAN — Fable implementation closure report

Branch: `claude/van-fable-forensic-audit-ds8g0o`. Audited base: `0067d55071342b963293d0724f5a1604d233d105` (origin/main). Last code commit: `100d898`; the closure HEAD is the commit that adds this report (the branch tip at closure). Date: 2026-09-22.

This report closes the remediation mission that consumed `VAN_FABLE_WHOLE_PROJECT_AUDIT.md`, `VAN_CANONICAL_GAP_REGISTER.md` (28 gaps), `VAN_REQUIREMENT_TRACEABILITY_MATRIX.md` (119 requirements), `VAN_RUNTIME_QUALIFICATION_MATRIX.md` (33 live gates) and `VAN_SYMBIOTIC_INTEGRATION_AUDIT.md`. Every statement below points at a commit, a file or a test that a reader can run. Nothing is marked closed on the strength of a description.

> **Post-Fable reconciliation — PR #59.** This report now carries a current-state addendum rather
> than treating the original Fable closure as immutable product truth. Audit-time facts remain
> identifiable as such; current repository claims are reconciled against the post-Fable branch.
> Live/device/provider/artist claims still require receipts and are not promoted by code alone.

Status vocabulary for this report: **FIXED_AND_EVIDENCED**, **SUPERSEDED_BY_BETTER_IMPLEMENTATION**, **DELIBERATELY_REMOVED_CANON_UPDATED**, **EXTERNALLY_GATED_REPOSITORY_COMPLETE**. No other status is used for a gap.

---

## 1. Audit findings received

| Source | Received as | Verified against HEAD before work |
|---|---|---|
| Gap register | 28 gaps (P1×5, P2×5, P3×11, P4×7, P0×0), 8 root causes RC-A…RC-H | Each gap's evidence lines re-read at `0067d55`; all 28 reproduced. |
| Traceability matrix | 119 REQs, 41 not INTEGRATED_AND_EVIDENCED | Re-derived per gap; REQ status column drives §12. |
| Qualification matrix | 33 live gates, none passable in-repo | Unchanged in kind; §11 lists what remains after this mission. |
| Symbiotic audit | Owner→VAN→Hermes→VATI loop broken at RC-A (Hermes tool surface), RC-B (gateway write producers), RC-C (learning read-back) | All three root causes closed in §5. |
| Advisory (trading, UI) | Trading intelligence recommendations; UI verdict "generic text cards" (122 inline hex, 142 sizes <12sp, no charts/gestures/adaptivity) | Trading in §4, UI in §6–§8. |

---

## 2. Changes implemented, one-to-one against the register

Commit key: c193d47 (authority/degraded/revoke) · b78cbf4 (Hermes surface) · b952b40 (learning/proactive) · 3311fc4 (design system) · 1b6e44e (determinism) · 17f4fba (embodiment) · 528366b (typed actions) · 3d845bc (trading intelligence) · 5498a6f (Android IA) · b46ca65 (overlay motion/storage) · 81805c9 (trading UI + halt wiring) · a60b009/2cf03d0 (instrumentation) · b5783dc (anti-gap checker).

| Gap | Title (short) | Closure status | Evidence (commit · file · test) |
|---|---|---|---|
| GAP-F-001 | Owner memory has no gateway write producer | FIXED_AND_EVIDENCED | 528366b `command/local_executors.py` (memory.remember, memory.decision.record → OwnerFactAuthor, CANONICAL_OWNER) · `verification/production.py` owner-fact-readback verifier · `backend/tests/test_local_typed_actions.py` (VERIFIED_SUCCESS only via re-read) · b78cbf4 shim `context_fact_candidate`/`context_edge_candidate` · 5498a6f Memory screen (`memory/MemoryRoute.kt`). |
| GAP-F-002 | Reminders unreachable from command path | FIXED_AND_EVIDENCED | 528366b `reminder.create` executor + resolver ("remind me to X at/in/on Y"), migration 29 `reminders.source` · reminder-readback verifier · b78cbf4 `reminder_create` tool → `POST /v1/runtime/reminders` (source=hermes) · 5498a6f Home "Upcoming" panel from `GET /v1/reminders`. |
| GAP-F-003 | Hermes cannot read trading state | FIXED_AND_EVIDENCED | b78cbf4 `/v1/runtime/trading/{status,portfolio,positions,risk,market-state,trade/{id}}` + trading tools · 3d845bc commander `positions`/`assessment` (read-only) · PR #59 exact shim/registration contract now pins **51 tools**. |
| GAP-F-004 | Cognition invoker is a stub advertising a model hierarchy | FIXED_AND_EVIDENCED (repo) / live QUAL-TRD-05 | 3d845bc `trading/vati/cognition/invokers.py` (NullInvoker, HttpJsonInvoker, HermesRunInvoker from session config); read model reports the actual invoker or `MODEL_INVOKER_UNCONFIGURED` · `trading/tests/test_active_trade_e2e.py`. |
| GAP-F-005 | trading.halt is dispatched to Hermes instead of executed | FIXED_AND_EVIDENCED | 528366b `TradingHaltExecutor` (owner-halt OwnerAuthority token in `client_context.owner_halt_authority_ref`, A4 biometric proof unchanged) · `test_local_typed_actions.py::test_trading_halt_*` · 81805c9 Android halt: `trading/TradingHaltAuthority.kt` signs the owner-halt grant under biometrics, `client_context.owner_halt_authority_ref` threaded through `VanCommandController` → `VanGatewayClient.dispatchCommand`, second biometric on the gateway's A4 challenge. |
| GAP-F-006 | Browser/automation have no Hermes initiator | FIXED_AND_EVIDENCED | b78cbf4 shim `browser_task_create/assignment_run/task_status/task_evidence`, `automation_route/execute/run_status`; AGENTS.md and skills made truthful. |
| GAP-F-007 | Degraded catalog incomplete (KeyError on unknown code) | FIXED_AND_EVIDENCED | c193d47 `degraded/registry.py` 9 codes, tolerant `snapshot()` · `backend/tests/test_degraded_catalog_is_exhaustive.py`. |
| GAP-F-008 | Learning is write-only (no read-back into decisions) | FIXED_AND_EVIDENCED | b952b40 `learning/feed.py strategies_for`, `understanding/api.py` calibration wiring, `proactive/autonomy.py` ActionAutonomyGate consulted by ActionRuntime for HERMES_AGENT/SYSTEM mutating actions · 528366b `canonical_context.permitted_strategies` · `test_learning_read_back.py`, `test_action_runtime_autonomy.py`. |
| GAP-F-009 | Internal control tokens not scope-checked at routers | FIXED_AND_EVIDENCED | c193d47 `auth/control_scopes.py require_scoped_internal` in 6 routers · `test_scoped_internal_control_reaches_routers.py`. |
| GAP-F-010 | `/health.degraded[]` never mapped on device | FIXED_AND_EVIDENCED | 5498a6f `degraded/GatewayDegradedMapping.kt`, `DegradedModeStore.applyGatewayHealth`, bound through `DegradedBridge` in `VanApplication.onCreate`; Settings shows one reconciled list · `android/verification/.../degraded/GatewayDegradedMappingTest.kt` (12). |
| GAP-F-011 | Chat never learns a command's final outcome | FIXED_AND_EVIDENCED | 5498a6f `command/work/ConversationReducer.kt`, `VanCommandController.pollUnfinishedCommands` (4 s), `VanGatewayClient.commandStatus`, `context_gaps` rendered as "VAN did not know", spoken completion via `control/VanSpokenAnswer.kt` → `VoiceEdge.speak(SpeechSegment)` · `ConversationReducerTest.kt` (8). |
| GAP-F-012 | Embodiment gestures/URGENT have no runtime producers | FIXED_AND_EVIDENCED | 17f4fba `visual/VanEmbodimentReducer.kt`, `VanEmbodimentProducers.kt`, `VanMotionMap.kt` (every state and gesture bound to a runtime signal, DNA §6) · 3d845bc `trading/bridge.py` publishes `trading.trade.closed` · `visual-preview` `VanEmbodimentCoverageTest` (no unbound state). |
| GAP-F-013 | TTS engine preference lied; local sherpa synthesizer was missing | FIXED_AND_EVIDENCED (repository) / DEVICE+EXTERNAL_ARTEFACT qualification | Production SpeechCueClock + device cue consumer remain; PR #59 adds `SherpaLocalTtsRuntime` (`OfflineTts` → VAN-owned `AudioTrack` PCM, measured RMS, barge-in), routes selected SHERPA_ONNX through `TtsOutputManager`, and retains Android offline fallback. Live bundle/S24 measurement remains QUAL-VOI-02. |
| GAP-F-014 | Rive renderer failure invisible to owner | FIXED_AND_EVIDENCED | 17f4fba `visual/VanRendererStatus.kt` via `DegradedBridge.rendererStatus` · 5498a6f Settings "Character" row reads `DegradedBridge.lastRendererStatus`. |
| GAP-F-015 | AGENTS.md contradicts the tool surface | FIXED_AND_EVIDENCED | Hermes docs/profile were reconciled to the expanded allowlist; PR #59 contract-tests exact equality between shim, registration and **51 REQUIRED_TOOLS**. |
| GAP-F-016 | Stream grant minted without a configured stream host | FIXED_AND_EVIDENCED | 1b6e44e `interactive_api.py` 503 `BROWSER_STREAM_UNCONFIGURED`. |
| GAP-F-017 | No pinned backend requirements | FIXED_AND_EVIDENCED | 1b6e44e `backend/requirements.lock`; installers use the lock. |
| GAP-F-018 | Device binding can be silently disabled in production | FIXED_AND_EVIDENCED | 1b6e44e `config.py van_env` + `assert_production_safe()`, `tools/runtime/qualify_gateway_host.sh`. |
| GAP-F-019 | Missing owner context blocks commands | SUPERSEDED_BY_BETTER_IMPLEMENTATION | 528366b: commands never block on missing memory; `context_gaps` are computed, returned in `CommandResult`, shown to the owner and passed to Hermes in `canonical_context`. Blocking a safety action on an unknown fact was the wrong contract; the audit's acceptance ("owner sees what VAN did not know") is met. |
| GAP-F-020 | Dead code (scrub, instruments, owner_approved) | FIXED_AND_EVIDENCED | c193d47 `_scrubbed()` on every Google read · 1b6e44e instruments wired or deleted · b78cbf4 `owner_approved` removed; `input_protocol` retained deliberately (stream host caller). |
| GAP-F-021 | Loopback defaults reach production | FIXED_AND_EVIDENCED | 1b6e44e config validator refuses loopback/empty secrets when `van_env=production`. |
| GAP-F-022 | Root pytest collection collision | FIXED_AND_EVIDENCED | 1b6e44e `tests/contracts/__init__.py`. |
| GAP-F-023 | Mutation harness not in CI; no androidTest | FIXED_AND_EVIDENCED (mutation) / EXTERNALLY_GATED_REPOSITORY_COMPLETE (instrumentation) | 1b6e44e `van-ci.yml` `mutation` job (non-blocking, report uploaded). Instrumentation: a60b009/2cf03d0 `src/androidTest` CommandCentreLaunchTest (primary destinations, every destination renders offline, `van://` deep link) + FloatingOverlayServiceTest (appops grant, start/stop), run by the `android-instrumentation` emulator job (advisory, report + screenshots uploaded). Real-device sign-off stays QUAL-AND-01. |
| GAP-F-024 | Owner cannot revoke Google from the device | FIXED_AND_EVIDENCED | c193d47 `POST /v1/google/owner-revoke` (device-proofed) · `test_google_owner_revoke_and_scrub.py` · 5498a6f Connected screen "Revoke Google" with confirm dialog. |
| GAP-F-025 | Two Google readiness predicates disagree | FIXED_AND_EVIDENCED | 1b6e44e `google/mesh.py EXECUTION_READY_STATES`, single predicate. |
| GAP-F-026 | Temporal routed but not built | FIXED_AND_EVIDENCED (repository) / PENDING_LIVE | PR #59 adds scoped gateway bridge/API, `VanDurableWorkflow`, Hermes `temporal_start/status/signal`, a loopback-only self-hosted Temporal 1.32.0 + isolated PostgreSQL stack, hardened server/worker systemd units, complete-bootstrap default and live qualifier. A restart/recovery canary remains QUAL-AUT-02. |
| GAP-F-027 | Overlay state in plain SharedPreferences | FIXED_AND_EVIDENCED | 5498a6f `OverlayStateStore` → EncryptedSharedPreferences · b46ca65 browser session store encrypted · `tests/contracts/test_android_storage_policy.py` (every plain writer encrypted or explained by name). |
| GAP-F-028 | Proactive follow-ups never scheduled | FIXED_AND_EVIDENCED | b952b40 `proactive/followups.py` + scheduler job `proactive.follow_ups`, owner-disableable · `test_proactive_followups.py`. |

Fable's original 28-gap register remains fully dispositioned. Post-closure review then found five additional product omissions that were not represented by those IDs; PR #59 implements all five repository paths and records their remaining device/live gates explicitly. Register JSON/MD preserve `status_at_audit` while adding the post-closure reconciliation.

---

## 3. Architecture before / after

**Before (0067d55).** The gateway received typed commands and forwarded every mutating one to Hermes, including the four actions it already owned the storage for (owner facts, decisions, reminders, trading halt). Hermes had 30 tools, and the missing memory/trading/browser/automation producers described by the audit prevented the symbiotic loop from closing. Internal control tokens were minted with scopes that no router checked. Learning wrote strategies that nothing read. The Android app was one activity with a hand-rolled module switch, Material cards and 464 design-lint violations; embodiment states existed with no producers.

**After.**

```
Owner device (Compose host, VAN design system)
  ├─ NavHost: Home · Attention · Work · Trading · Memory  (+ Projects · Connected · Settings)
  ├─ Embodiment reducer ← runtime signals (command state, trading events, degraded, speech cues)
  └─ VanGatewayClient (device token + HMAC v3 + A4 ECDSA)  ──►  Gateway
Gateway (FastAPI)
  ├─ CommandOrchestrator ──► LOCAL_EXECUTORS (memory / decision / reminder / trading.halt)
  │        │                    └─ ActionRuntime begin → verify(read-back) → mission VERIFIED_SUCCESS
  │        └─ everything else ──► Hermes run (canonical_context + context_gaps + permitted_strategies)
  ├─ OwnerRuntimeApi (scoped internal token, ControlScope.RUNTIME) ◄── Hermes MCP shim (51 tools, exact-set contract)
  ├─ Learning: calibrate() ← owner corrections; strategies_for() → canonical_context; AutonomyGate
  ├─ Proactive follow-ups (scheduler) · TradingEventBridge (trading.trade.closed → device events)
  └─ Degraded registry (9 codes) → /health.degraded[] → device DegradedModeStore
VATI (trading)
  ├─ cognition invokers (Null/HttpJson/HermesRun) · thesis lifecycle · scale policy · news ingress
  ├─ RiskAuthority (sole sizing gate) · ExecutionRouter (sole submit) · multipliers ≤ 1
  └─ read models: positions / events / potential / history / assessment → gateway → device + Hermes
```

Invariants preserved and re-tested: VATI never bypassed (halt goes through `TradingService.halt` with an OwnerAuthority token; no sizing outside RiskAuthority; guardrail suite green); Hermes never bypassed for open-ended work (only the four owned typed actions execute locally); every gateway write is device-proofed or scope-checked; every mission reaches VERIFIED_SUCCESS only through an independent verifier.

---

## 4. Trading intelligence

Implemented in 3d845bc under unchanged invariants:

- **Cognition invokers** (`cognition/invokers.py`): the read model names the real invoker; output containing order fields is refused.
- **Trade thesis lifecycle** (`lifecycle/thesis.py`, `trade_health.py`): thesis sealed at approval; per-cycle assessment INTACT / STRONGER / WEAKER / INVALIDATED / OVEREXTENDED / RISKIER / ASYMMETRIC, persisted on change.
- **Adaptive position proposals** (`lifecycle/scale_policy.py`): HOLD / ADD / REDUCE / MOVE_PROTECTION / PARTIAL_TAKE / EXIT; ADD never exceeds originally approved risk; every delta goes through RiskAuthority and the router.
- **News and event impact** (`events/news_ingress.py`, `vati news-ingest`): trust-stated headline ingress → EventImpactAssessment → reduce-only event-risk multiplier and thesis input.
- **Decision-quality × outcome attribution** (`cognition/attribution.py`, `learning/episodes.py`): four quadrants, Lesson records, capsule health from decision quality only, `lessons_for()` attached to candidates.
- **Read models** (`readmodels/active.py`) exposed at `/v1/trading/{positions,events,potential,history,assessment}` (owner device) and `/v1/runtime/trading/*` (Hermes), plus commander read-only views.
- **Owner-visible outcomes**: `trading/bridge.py` publishes each closed trade with its quadrant as a device event; the embodiment reacts (DNA §6).

Tests: trading suite 1273 passed; `test_active_trade_e2e.py` (thesis → adverse headline → REDUCE through the authority → close → quadrant + lesson → read models); guardrails OK; Rev 5.1 harness SPEC_CLOSED true, LIVE_ELIGIBLE false (live credentials remain an external gate).

---

## 5. Symbiosis (owner ↔ VAN ↔ Hermes ↔ VATI)

| Loop leg | Before | After |
|---|---|---|
| Owner → VAN memory | text to Hermes, never stored | gateway executes, verifies by re-read, Memory screen shows it, Hermes can read (`context_*` tools) and propose (`context_fact_candidate`) |
| Owner → reminders | unreachable | typed action + Hermes tool; Home "Upcoming" |
| Hermes → trading | blind | 6 read tools + assessment; no write path by design |
| Hermes → browser/automation | no initiator | 7 tools through the governed fabric |
| VATI → owner | ledger only | closed-trade events with quadrant; Trading screen read models |
| Learning → decisions | write-only | `permitted_strategies` in every canonical context; autonomy gate on agent-initiated mutations; owner corrections calibrate |
| VAN → owner (proactive) | never | scheduled follow-ups, disableable |

---

## 6. Android runtime, IA and UI redesign

**Design DNA** (`docs/design/VAN_PRODUCT_DESIGN_DNA.md`, 3311fc4): tokens, seven-state screen contract (LOADING / LIVE / STALE / OFFLINE / DEGRADED / EMPTY / DENIED), information architecture, embodiment binding map, gates V1–V8. Implemented as `com.dial.van.design` (VanTokens, DensityTier, MotionSpec, StatusSemantics, LiveBadgeFormat, chart axes, 22 components; catalogue in `docs/design/COMPONENT_CATALOGUE.md`). `tools/audit/android_design_lint.py` is a one-way ratchet: 464 baseline violations at the lint's birth → 181 at closure (all remaining entries are legacy screens reused as children: browser, speech, notification policy, onboarding, overlay), every new or rebuilt package at 0; no file may grow its count (`tests/contracts/test_android_design_lint.py`).

**Information architecture** (5498a6f): one NavHost; primary Home · Attention · Work · Trading · Memory; More → Projects · Connected · Settings; bottom bar at Regular density, rail at Wide; `van://` deep links; process-death-safe route restore. Legacy module switch and five text-card modules deleted; §20.15 reconfirmation panel preserved in Work.

**Screens and their data sources** — see §7.

**Trading UI** (81805c9): `trading/ui/TradingRoute.kt` hosts Overview / Positions / Potential / History / Accounts plus position detail, strategies and cognition, reachable from the Work NavHost and from the overlay's `TradingCommandCentreActivity` (kept for the overlay's `trade/{id}`/`trades/{view}` deep links). Positions use `PositionCard` (direction, exposure, R, protection, thesis state), detail uses `ThesisCard` + `EvidenceRow` + candlestick with `ChartAxes` ticks, potential trades use `FindingCard`, history tallies decision-quality × outcome quadrants with `HeatBar`, every list is bounded and every panel carries a `LiveBadge` with ledger staleness. Halt is an app-bar action behind `ApprovalSheet` with two biometric confirmations (§2 GAP-F-005). All trading files are design-lint clean.

**Deliberate absences (no fake gestures):** Attention "snooze" is not offered because the backend never routes `AttentionEngine.snooze`; Home's trade panel shows `Offline` rather than a placeholder when the assessment route is unreachable.

---

## 7. Live dashboards — data-source mapping

Every panel is bound to a gateway route and renders through the seven-state contract; there is no sample or placeholder data anywhere in the app (`tests/contracts/test_android_dashboard_navigation.py`, `test_owner_surfaces_are_reachable.py`).

| Screen / panel | Route(s) | Refresh | Empty / offline behaviour |
|---|---|---|---|
| Home · attention now | `GET /v1/attention`, `GET /v1/briefing` | on resume + event stream | EmptyState "Nothing needs you" / Offline badge |
| Home · active work | `GET /v1/missions` (RUNNING, WAITING) | event stream | EmptyState |
| Home · trade state | `GET /v1/trading/assessment` | 30 s while visible | `LiveBadge.Offline` (never a fake number) |
| Home · upcoming | `GET /v1/reminders` (due today) | on resume | EmptyState |
| Home · recent change | device event store (last 5) | SharedFlow | EmptyState |
| Attention | `GET /v1/attention`, `POST /v1/attention/{id}/ack`, decisions approve/refuse | event stream | quiet-hours banner from policy |
| Work · conversation | `POST /v1/commands`, `GET /v1/commands/{id}` (poll 4 s until final) | poll | context_gaps line; honest denied/degraded |
| Work · missions | `GET /v1/missions`, `GET /v1/missions/{id}/activity` | event stream | TimelineRail on expand |
| Trading · Overview | `GET /v1/trading/portfolio`, `/assessment`, `/positions`, `/events` | on resume + refresh action | Offline badge; bounded previews (5) route to sub-screens |
| Trading · Positions / detail | `GET /v1/trading/positions`, `/trades/{id}`, `/events`, `/market-state` | on resume + refresh | EmptyState "No open trades" vs "cannot see the ledger" kept distinct |
| Trading · Potential | `GET /v1/trading/potential` | on resume + refresh | EmptyState |
| Trading · History | `GET /v1/trading/history` (closed trades + authoritative cumulative R/P&L curves) | on resume + refresh | EmptyState when no history; Sparkline renders backend-owned curve data and never invents a series |
| Trading · Accounts / Strategies / Cognition | `GET /v1/trading/accounts`, `/strategies/promotion-candidates` (+ challenge/promote), `/cognition` | on resume | protocol unchanged; cognition names the real invoker or MODEL_INVOKER_UNCONFIGURED |
| Trading · halt | `POST /v1/commands` "halt trading" (A4) + `client_context.owner_halt_authority_ref` | on tap | HALT AUTHORITY / OWNER APPROVAL PENDING / outcome chips in the gateway's words |
| Memory | `GET /v1/context/memory`, `/conflicts`, `/history`, `/export`; `POST`/`DELETE /v1/context/facts` | on resume | EmptyState; conflicts panel |
| Projects | `GET /v1/projects`, `GET /v1/projects/{id}` | on resume | EmptyState |
| Connected | `GET /health` (hermes, knowledge), `GET /v1/google/planes`, `POST /v1/google/owner-revoke` | on resume | per-plane state |
| Settings | pairing/binding state, `DegradedBridge.lastRendererStatus`, `DegradedModeStore` (device + gateway) | live | restore actions where a device action exists; gateway actions as text |

---

## 8. Embodiment, aura and motion

- **Binding map** (DNA §6 → `visual/VanEmbodimentProducers.kt`): IDLE ← no work; LISTENING ← wake/voice input; THINKING ← command accepted, not final; WORKING ← mission RUNNING; NEEDS_YOU ← attention item / A4 pending; URGENT ← degraded HERMES_OFFLINE, halted trading, P1 attention; SPEAKING ← speech cue track; CELEBRATE / SETBACK ← `trading.trade.closed` quadrant; HELLO_WAVE ← first session of the day.
- **Aura** reacts to microphone amplitude (`VanAuraSpec.reactToVoiceAmplitude`) and to speech cue timing from the gateway (`voice/speech_cues.py`), not to frame counters.
- **Motion**: durations and easings from `design/MotionSpec.kt`; reduced-motion collapses every transition to 0 ms; overlay fling docking with velocity (`EdgeDocking.flingSnap`), docking feedback, presentation changes cross-fade through `AnimatedContent` (b46ca65); press scale 0.97 via `VanPressable`.
- **Coverage proof**: `visual-preview` `VanEmbodimentCoverageTest` fails if any state or gesture lacks a producer.
- **Obstruction producer**: `VanObstructionAccessibilityService` now supplies keyboard/full-screen window metadata to `FloatingOverlayService`; VAN repositions above the IME and pauses expensive animation for immersive full-screen use. The remaining Android Accessibility grant is a physical-device permission/acceptance gate, not missing code.

---

## 9. Tests — commands and results

All commands run from the repository root unless stated. Results are from the closure HEAD. The table preserves the original Fable closure receipts; PR #59 must independently pass current-head CI before merge, and its live/device rows are not inferred from these historical counts.

| Suite | Command | Result |
|---|---|---|
| Backend gateway | `cd backend && PYTHONPATH=tests python -m pytest tests -q` | 1740 passed (local, 358 s; CI run 985 identical) |
| Trading (VATI) | `python -m pytest trading/tests -q` | 1273 passed, 2 skipped |
| Trading guardrails | CI step "Trading enhancement architecture guardrails" | OK (3d845bc, re-run in CI) |
| Rev 5.1 harness | `python trading/vati/certification/rev51_harness.py` | SPEC_CLOSED true · LIVE_ELIGIBLE false |
| Contract tests | `python -m pytest tests/contracts -q` | 399 passed, 1 skipped |
| Design lint | `python tools/audit/android_design_lint.py --baseline tools/audit/android_design_lint_baseline.json` | no new or grown violations; trading/command/memory/projects/design at 0 |
| Kotlin reachability | `python tools/audit/kotlin_reachability.py` (via contract test) | no unexplained unreachable or test-only Kotlin; scanner now sees generic composables |
| Maturity gate | `python tools/ci/maturity_gate.py` | PASSED (209/209 terminal; citations repointed from deleted files) |
| Anti-gap pass | `python tools/audit/fable_anti_gap_check.py` | 55/55 checks across 28 gaps (enforced by `tests/contracts/test_fable_anti_gap_check.py`) |
| Android JVM harness | `cd android/verification && ../gradlew test --console=plain` | BUILD SUCCESSFUL (nav model, conversation reducer, degraded mapping, memory/projects, trading read models, chart geometry, speech cues, embodiment) |
| Visual preview / embodiment coverage | `gradlew :visual-preview:test` | BUILD SUCCESSFUL (VanEmbodimentCoverageTest: every state and gesture has a producer) |
| Android app compile, unit tests, lint, debug APK, visual geometry | GitHub Actions `van-ci` job `android-and-visual-evidence` | success on run 990 (911cabb): `:app:testDebugUnitTest` 200 tests, `:app:assembleDebug`, `:app:lintDebug` clean, APK + `van-visual-evidence` uploaded |
| Mutation (non-blocking) | `van-ci` job `mutation` | success on run 990; report uploaded as `van-mutation-report` |
| Instrumentation (advisory) | `van-ci` job `android-instrumentation` (API 31 x86_64 emulator, pixel_6) | success on run 995 (100d898): 4/4 tests — CommandCentreLaunchTest ×3 (launch on Home, every primary destination + More sheet offline, `van://attention` deep link) and FloatingOverlayServiceTest (appops grant, foreground start/stop); artifacts `van-instrumentation-report` and `van-instrumentation-screenshots` uploaded on every run |

---

## 10. Visual verification

Two kinds of visual evidence exist, both produced by CI from the shipping code, neither drawn by hand:

1. **Embodiment geometry renders** — `van-ci` job `android-and-visual-evidence`, step "Render owner visual evidence from shipping geometry" (`:visual-preview:renderVanPreviews`), uploaded as the `van-visual-evidence` artifact on every green run (run 990 and later). These are the character/aura states rendered from `VanEmbodimentReducer`/`VanMotionMap` output, so every state in DNA §6 has a picture that came from the same code the app runs.
2. **On-device screenshots of the redesigned owner surface** — `van-ci` job `android-instrumentation` runs `CommandCentreLaunchTest` on an API 31 emulator with no gateway behind the app and captures Home, Attention, Work, Trading, Memory, the More sheet and the `van://attention` deep link to `<files>/screenshots/*.png`, uploaded as `van-instrumentation-screenshots`. What those images show is the seven-state contract doing its job offline: every panel in its OFFLINE or EMPTY state with a `LiveBadge`, no placeholder numbers, the design tokens applied (no Material cards, no raw hex, no sub-12sp text: `tools/audit/android_design_lint.py` at 0 for every rebuilt package). Run 995's `van-instrumentation-screenshots` artifact holds the PNGs (home, attention, work, trading, memory, more + sheet window, deeplink-attention), rendered by the API 31 emulator from the shipping APK.

What was not visually verified: LIVE states with a paired gateway and populated ledgers (needs the owner's host and credentials, §11), the Rive-rendered character on real hardware (QUAL-EMB-01), and the overlay on a physical device with the owner's permission grants (QUAL-AND-01). Those are the same external gates the audit named; nothing in this report claims them.

---

## 11. Remaining external gates (live qualification)

The repository now has executable paths for the product gaps found after the Fable pass. What
remains here is deliberately **live evidence**, not missing code:

- **Gateway/Android production path:** stable named HTTPS ingress, production release signing + trust anchor, owner-device provisioning and physical S24 acceptance (overlay, notification listener, biometric approval, Doze, process death/reboot/reconnect, shares, microphone/TTS and docking).
- **Hermes current-head requalification:** mount the exact **51-tool** `van_owner_runtime` surface and prove VAN command → gateway → Hermes run → MCP tool → `mission_result` → verification → owner-visible final result. Earlier profile/model receipts do not certify the changed interface.
- **Trading:** live feed provenance, demo broker fills, SHADOW and LIMITED_LIVE progression remain required. The cognition injection path is implemented; provider/Hermes credentials and a live shadow round-trip are deployment evidence.
- **Voice:** KWS/ASR/speaker assets and the new sherpa TTS bundle/config must be deployed to the S24 and measured. Repository code no longer treats sherpa as a fictional engine.
- **Temporal:** the repository now self-hosts a loopback-only single-node Temporal 1.32.0 server with isolated PostgreSQL by default, plus the durable worker/bridge. Deployment and a restart/recovery canary are still required before LIVE qualification.
- **Authored character:** the canonical `van.riv` remains an external artist/Character Forge artefact and needs checksum + contract + owner visual acceptance.
- **Google Workspace OAuth is already LIVE_CERTIFIED** in the qualification matrix. It is **not** an outstanding setup item; only periodic re-canary/token-rotation evidence remains.
- **Accessibility permission:** the obstruction producer is now implemented; the owner must grant the Android Accessibility permission and the behavior must be accepted on the physical S24.

---

## 12. Repository closure after the post-Fable product pass

The earlier sentence “zero repository gaps” was too broad: it meant only that the 28-item
Fable register had a disposition, while four ordinary product omissions and one deliberately
deferred runtime were still visible in the product itself. They are now first-class
`PROD-F-001..005` reconciliation rows and executable anti-gap checks:

- **PROD-F-001 Attention snooze:** durable engine mutation + backend route + Android caller.
- **PROD-F-002 obstruction awareness:** AccessibilityService window-metadata producer + overlay consumer/repositioning + onboarding/Settings state.
- **PROD-F-003 Trading History curves:** VATI server emits cumulative R/P&L series; Android renders only those live read-model values.
- **PROD-F-004 local sherpa TTS:** real OfflineTts synthesis/PCM/barge-in path; bundle/device qualification remains external.
- **PROD-F-005 Temporal:** durable workflow/worker/private bridge plus self-hosted loopback server/PostgreSQL, server+worker systemd supervision, bootstrap and qualification; only live deployment/restart-recovery evidence remains.

Accordingly, **no currently known code-path omission from the supplied review is being hidden
as “design-bounded.”** The remaining items in §11 are live/device/provider/artist evidence
gates and are not promoted without receipts.

---

## 13. Anti-gap pass

Method: for each of the 28 gaps, the audit's original evidence line was re-read against the closure tree and the artefact the closure claims was re-located by a check that can be run again (`tools/audit/fable_anti_gap_check.py`, which now covers the original 28 gaps **plus the five post-closure product rows**: executors, verifiers, routes, Hermes tools, producers, encrypted stores, CI jobs, canon statements). The checker is a contract test, so deleting any claimed artefact re-opens the gap in CI. Behavioural evidence is the suites named per gap in the checker's `SUITES` table and in §9.

Second pass, worker hand-offs: every "left for another worker" item in the worker reports was closed by the coordinator before this report — `DegradedBridge.bindGatewayHealth` and `VanSpokenAnswer` bound in `VanApplication`; `client_context` threaded for the halt authority; `ChartAxes` wired into `ChartGeometry`/`TradeChartCanvas`; reachability ledger entries for adopted components removed; findings.json citations repointed; CI template kept byte-identical; Material experimental opt-ins added where the compiler demanded them.

Third pass, new code against the mission's own rules: no screen holds sample data (`test_android_dashboard_navigation.py`, `test_owner_surfaces_are_reachable.py`); no plain preference writer is unexplained (`test_android_storage_policy.py`); no design component is test-only (`test_kotlin_reachability.py`); no trading write path exists outside VATI's authority (guardrails, `test_active_trade_e2e.py`); no Hermes bypass for open-ended work (only the four owned typed actions execute locally, `test_local_typed_actions.py`).
