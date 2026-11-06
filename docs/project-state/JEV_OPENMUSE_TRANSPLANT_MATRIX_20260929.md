# Jev × OpenMuse transplant matrix — 2026-09-29 (Programme B, Subagent G)

Source (reference only, never merged wholesale):
`origin/gpt/jev-control-centre-20260925` @ `f3df7a10e12fc76d25f958e9f19cb0b25c798168`.
Merge-base with the OpenMuse convergence head `a8d3f1930ad9`: `be49e8e734181f99733742119912d810a49d0a3b`.
Target: branch `gpt/jev-openmuse-convergence-r1-van-20260929-g-converge` (base `a16f7cb`).

Derivation of the file list and of the 13 overlaps (re-runnable):

```
git diff --name-only be49e8e7 f3df7a10 | sort > jev.txt    # 50 files
git diff --name-only be49e8e7 a8d3f193 | sort > om.txt     # 197 files
comm -12 jev.txt om.txt                                  # 13 overlaps
git diff be49e8e7 f3df7a10 -- . ':!backend/van_gateway/understanding' ':!hermes/profile/van/config.yaml' \
  | git apply -3 --check   # conflicts: app.py, degraded/registry.py, models.py, runtime_api.py
```

## Invariants every row must preserve

- **One Jev (B0).** VAN is a *client* of the single DDS `dial-jev` service (`127.0.0.1:6791`).
  VAN adds no Jev daemon, router, ledger, credential plane, Chromium or browser session.
- **Jev is evidence, never authority.** SHADOW/ADVISORY (`apply_effect=false`) changes nothing;
  every consumer keeps its exact non-Jev path when Jev is absent, bypassed or failing.
- **OpenMuse contracts win on conflict**: Browser Control Agent / Browser Harness, typed
  `ComputerInteractionFabric` (no `EXECUTE` primitive), documents, PDFs, conversations,
  artifacts, goals/watches, computer worker, owner-facing surfaces, browser control-lease
  security boundaries (owner touch wins, generation fence).
- **VATI stays sole trading authority**: Jev `van.trading.*` output is subordinate annotation
  inside an active cognition run; no Jev or browser path reaches order entry, sizing or risk.

## Disposition key

TRANSPLANT = carried semantically unchanged · ADAPT = carried with a deliberate change ·
MANUAL_MERGE = overlap with OpenMuse, reconciled by hand · DROP = not carried ·
SUPERSEDED = OpenMuse already provides it.

## Matrix (50 files)

| # | File | Responsibility | OpenMuse equivalent / conflict | Disposition | Reason |
|---|---|---|---|---|---|
| 1 | android/…/command/CommandCentreActivity.kt | NavHost: register Jev screen | **Overlap.** OpenMuse added dev graph, assets, documents, threads, convergence routes | MANUAL_MERGE | Add one `composable(VanRoute.SETTINGS_JEV)`; every OpenMuse composable kept byte-identical |
| 2 | android/…/command/jev/JevControlRoute.kt | Jev Control Centre root/tabs, owner command submission | none | ADAPT | Titled **Jev Intelligence**; states it is the same `dial-jev` the Browser & Automation lane consults; owner controls still go through signed A4 commands |
| 3 | android/…/command/jev/JevControlScreens.kt | Global/project control panels | none | TRANSPLANT | Depends only on design components present on head (verified) |
| 4 | android/…/command/jev/JevEvidenceScreens.kt | Evaluation proposals/reviews/candidates | none | TRANSPLANT | Read-only projection |
| 5 | android/…/command/jev/JevModels.kt | Pure-Kotlin read models (org.json) | none | TRANSPLANT | JVM-verifiable module |
| 6 | android/…/command/jev/JevModuleScreens.kt | Module detail/lifecycle | none | TRANSPLANT | — |
| 7 | android/…/command/jev/JevOverviewScreens.kt | Service overview | none | TRANSPLANT | — |
| 8 | android/…/command/jev/JevRepository.kt | Gateway → model mapping | none | TRANSPLANT | — |
| 9 | android/…/command/nav/VanRoute.kt | Typed routes | **Overlap.** OpenMuse added WORK_ASSETS/DOCUMENT/THREAD + DEV_TEMPLATES | MANUAL_MERGE | Jev route becomes `settings/jev` (child of Settings) instead of Jev's top-level `jev`→HOME, so DNA §4 stays at eight destinations; all OpenMuse templates kept |
| 10 | android/…/command/settings/SettingsRoute.kt | Link into Jev screen | not changed by OpenMuse | TRANSPLANT | Link text renamed "Jev Intelligence" |
| 11 | android/…/gateway/VanGatewayClient.kt | `/v1/jev/*` read calls | **Overlap.** OpenMuse added documents/threads/assets/browser-session calls | MANUAL_MERGE | Jev read methods appended + `browserInteractionRouter()`; no OpenMuse method changed |
| 12 | android/verification/build.gradle.kts | JVM verification source set | **Overlap.** OpenMuse added its own pure-Kotlin files | MANUAL_MERGE | `JevModels.kt` appended to the include list |
| 13 | android/verification/…/jev/JevModelsTest.kt | JVM tests of JevModels | none | TRANSPLANT | — |
| 14 | backend/tests/test_jev_attention_integration.py | Attention SHADOW/ACTIVE semantics | none | TRANSPLANT | — |
| 15 | backend/tests/test_jev_control.py | Resolver/executor/read-back of Jev A4 controls | none | TRANSPLANT | — |
| 16 | backend/tests/test_jev_critic_integration.py | Raise-only critic | none | TRANSPLANT | — |
| 17 | backend/van_gateway/action/registry.py | `jev.module.transition`, `jev.global.control` A4 owner-device actions | **Overlap.** OpenMuse added document/browser/computer actions | MANUAL_MERGE | Two A4 `OWNER_DEVICE`-only, `no_stale_replay` entries inserted before `secret.exfiltrate`; no OpenMuse action touched |
| 18 | backend/van_gateway/app.py | Construct advisor/projection; wire into attention, runtime, orchestrator, verifier registry | **Overlap (3-way conflict).** OpenMuse rewired browser/computer/documents/goals | MANUAL_MERGE | Jev objects constructed next to `degraded`; OpenMuse wiring untouched; Understanding API wiring **not** carried (row 34); interaction router exposed read-only at `/v1/browser/interaction-router` |
| 19 | backend/van_gateway/attention/engine.py | Optional Jev attention-field annotation | **Overlap** (OpenMuse scorer/candidate changes) | MANUAL_MERGE | Jev block applied before the OpenMuse scorer call; scorer, payload keys and dedupe untouched; SHADOW changes nothing |
| 20 | backend/van_gateway/authority/descriptor.py | Reversibility of the two Jev actions | **Overlap** (OpenMuse reversibility rows) | MANUAL_MERGE | Two rows added; approval gate unchanged |
| 21 | backend/van_gateway/command/local_executors.py | A4 Jev executors with independent read-back | not changed by OpenMuse | TRANSPLANT | — |
| 22 | backend/van_gateway/command/resolver.py | Exact typed Jev control grammar | not changed by OpenMuse | TRANSPLANT | — |
| 23 | backend/van_gateway/command/success_contracts.py | `jev-readback` success contract | not changed by OpenMuse | TRANSPLANT | — |
| 24 | backend/van_gateway/config.py | `jev_*` settings (one base URL) | **Overlap** (OpenMuse browser/documents settings) | MANUAL_MERGE | One `jev_base_url` (single service); settings block added, no OpenMuse setting altered |
| 25 | backend/van_gateway/degraded/registry.py | `JEV_UNAVAILABLE` catalog entry | **Overlap (conflict)** with OpenMuse browser/computer entries | MANUAL_MERGE | Entry appended; states VAN core and browser lanes continue |
| 26 | backend/van_gateway/jev/__init__.py | Package doc | none | TRANSPLANT | Doc adds the one-Jev rule |
| 27 | backend/van_gateway/jev/advisor.py | Consumer-scoped judgment client | none | ADAPT | Adds `browser_state` (RAISE_ONLY evidence only), `propose_action` (B1 transport, never executes) and `rank_fabric_operations` (ORDER_ONLY over caller ids); same single base URL |
| 28 | backend/van_gateway/jev/api.py | Read-only owner projection `/v1/jev/*` | none | TRANSPLANT | No mutation routes |
| 29 | backend/van_gateway/jev/client.py | Projection/control client | none | TRANSPLANT | — |
| 30 | backend/van_gateway/models.py | `DegradedCode.JEV_UNAVAILABLE` | **Overlap (conflict)** with new OpenMuse codes | MANUAL_MERGE | One enum member appended |
| 31 | backend/van_gateway/orchestrator.py | Pass Jev client to local executors | not changed by OpenMuse | TRANSPLANT | — |
| 32 | backend/van_gateway/reasoning/kernel.py | Raise-only Jev critic | not changed by OpenMuse | TRANSPLANT | Default `jev_advisor=None` keeps every other caller no-Jev |
| 33 | backend/van_gateway/runtime_api.py | Kernel gets advisor | **Overlap (conflict)** with OpenMuse runtime additions | MANUAL_MERGE | Keyword param added; OpenMuse constructor args kept |
| 34 | backend/van_gateway/understanding/api.py | Understanding kernel gets advisor | Programme A ownership | DROP | `backend/van_gateway/understanding/**` belongs to Programme A. The kernel's `jev_advisor` defaults to `None`, so `/v1/understanding` keeps the exact non-Jev path. Hand-off: Programme A may wire it later |
| 35 | backend/van_gateway/verification/production.py | `jev-readback` verifier (optional) | not changed by OpenMuse | TRANSPLANT | Kept out of `WIRED_MISSION_STRATEGIES` |
| 36 | docs/VAN_EXPERT_TRADING_TERMINAL_M0_SEMANTIC_CLOSURE_REV_1.md | Trading-terminal authority closure | none | TRANSPLANT | Document; Jev listed as subordinate everywhere |
| 37 | docs/VAN_EXPERT_TRADING_TERMINAL_UX_BLUEPRINT_REV_1_1.md | Trading-terminal UX blueprint | none | TRANSPLANT | Document only |
| 38 | hermes/mcp/README.md | `dial_jev` MCP server description | **Overlap** (OpenMuse MCP sections) | MANUAL_MERGE | Section inserted; no bounded tool list widened |
| 39 | hermes/profile/van/SOUL.md | Optional Jev System-1 guidance | not changed by OpenMuse | TRANSPLANT | — |
| 40 | hermes/profile/van/config.yaml | Register skill + `dial_jev` MCP | not changed by OpenMuse | ADAPT | Source commit introduced a UTF-8 BOM and mojibake (`â€”`) on line 1; that corruption is **not** carried |
| 41 | hermes/skills/browser-intelligence/SKILL.md | `van.browser.state.v1` usage | OpenMuse Browser Control Agent / Stagehand lanes | ADAPT | Adds the B5 router order and B1 rules; `van.browser.state.v1` flags stay non-authoritative |
| 42 | hermes/skills/jev-management/SKILL.md | Jev lifecycle/evaluation skill | none | TRANSPLANT | — |
| 43 | hermes/skills/trading-intelligence/SKILL.md | Subordinate Jev trading judgments + Live Analyst | not changed by OpenMuse | TRANSPLANT | — |
| 44 | tests/hermes/test_profile_layout.py | Skill list | not changed by OpenMuse | TRANSPLANT | — |
| 45 | tools/hermes/doctor_van_profile.sh | Skill list | not changed by OpenMuse | TRANSPLANT | — |
| 46 | tools/hermes/install_van_profile.sh | Skill list | not changed by OpenMuse | TRANSPLANT | — |
| 47 | tools/runtime/configure_jev_gateway.sh | Install server-side Jev token files | none | TRANSPLANT | Points at the one `dial-jev`; starts no service |
| 48 | trading/tests/test_cognition_invokers.py | Prompt carries the Jev boundary | not changed by OpenMuse | TRANSPLANT | — |
| 49 | trading/tests/test_jev_architecture_boundary.py | Jev absent from deterministic VATI | none | ADAPT | Extended: no Jev/browser module reaches broker/risk/sizing; browser package imports nothing from VATI execution |
| 50 | trading/vati/cognition/invokers.py | Prompt text for subordinate Jev | not changed by OpenMuse | TRANSPLANT | — |

Counts: TRANSPLANT 31 · ADAPT 5 · MANUAL_MERGE 13 · DROP 1 · SUPERSEDED 0 (= 50).

## New in this unit (not from the Jev branch)

| File | Purpose |
|---|---|
| `backend/van_gateway/browser/interaction_router.py` | B5 router + B1 VAN-side validator |
| `backend/tests/test_browser_interaction_router.py` | Router, B1, lease preemption, outage tests |
| `backend/tests/test_one_jev_system.py` | Fails on a second Jev service/daemon/browser session |
| `backend/tests/test_jev_no_generic_executor.py` | No `execute` primitive reachable from Jev output |
| `android/…/command/modules/BrowserModules.kt` (OpenMuse file, additive) | Browser & Automation "Interaction lanes" card reading `/v1/browser/interaction-router`; a read failure never blanks the page |
| `GET /v1/browser/interaction-router` (in `app.py`) | Read-only lane status; behind the global ingress/device auth middleware |

## Semantic reconciliation of the 13 overlaps

1. **CommandCentreActivity.kt** — Jev appears as one additional destination under Settings;
   Browser & Automation (`work/browser`) is unchanged and its sessions/tasks/escalations/policy
   children stay. Jev Intelligence and the router status both read the one `dial-jev`.
2. **VanRoute.kt** — `SETTINGS_JEV = "settings/jev"`; `PRIMARY + MORE` stays 8.
3. **VanGatewayClient.kt** — additive read calls only.
4. **verification/build.gradle.kts** — additive include.
5. **action/registry.py** — two A4 owner-device actions; OpenMuse action set unchanged.
6. **app.py** — Jev advisor/projection constructed once and injected; the interaction router
   is built over the *existing* `ControlLeaseService` (no new lease model, no new session) and
   its default eligibility denies everything, so the Jev lane is never taken until the parent
   wires Subagent F's classifier.
7. **attention/engine.py** — Jev annotation precedes the unchanged OpenMuse scorer.
8. **authority/descriptor.py** — two reversibility rows.
9. **config.py** — one base URL; three server-side token files.
10. **degraded/registry.py** — `JEV_UNAVAILABLE` appended.
11. **models.py** — enum member appended.
12. **runtime_api.py** — keyword pass-through into the reasoning kernel.
13. **hermes/mcp/README.md** — `dial_jev` section inserted before the trading section.
