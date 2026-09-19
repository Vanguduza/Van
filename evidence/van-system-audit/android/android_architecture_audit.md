# VAN Android Audit (READ-ONLY)
Repo: /home/user/Van | branch claude/van-system-audit-ysgtcd | HEAD dff38a0
Scope: android/app/src/main (excl. visual/ and voice/ except wiring), build.gradle.kts, src/test,
tests/contracts/test_android_dashboard_navigation.py, android/README.md

## 0. File inventory + line counts (source of truth for "god file" claims)
   204 android/app/src/main/java/com/dial/van/VanApplication.kt
  1238 android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt
   332 android/app/src/main/java/com/dial/van/control/VanCommandController.kt
    65 android/app/src/main/java/com/dial/van/degraded/DegradedMode.kt
    95 android/app/src/main/java/com/dial/van/degraded/DegradedModeStore.kt
    69 android/app/src/main/java/com/dial/van/gateway/QueueReplayer.kt
   535 android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt
   197 android/app/src/main/java/com/dial/van/mission/MissionModels.kt
   174 android/app/src/main/java/com/dial/van/mission/MissionRepository.kt
   110 android/app/src/main/java/com/dial/van/notification/NotificationPolicy.kt
    69 android/app/src/main/java/com/dial/van/notification/VanNotificationListenerService.kt
   168 android/app/src/main/java/com/dial/van/onboarding/OnboardingActivity.kt
  1031 android/app/src/main/java/com/dial/van/overlay/FloatingOverlayService.kt
    20 android/app/src/main/java/com/dial/van/overlay/OverlayRecoveryReceiver.kt
    99 android/app/src/main/java/com/dial/van/overlay/OverlayStateStore.kt
    48 android/app/src/main/java/com/dial/van/overlay/OverlayTheme.kt
   165 android/app/src/main/java/com/dial/van/overlay/VanMinimizedAvatar.kt
    47 android/app/src/main/java/com/dial/van/overlay/VanOverlayChrome.kt
   138 android/app/src/main/java/com/dial/van/overlay/VanOverlayInteraction.kt
    91 android/app/src/main/java/com/dial/van/queue/CommandQueueModels.kt
   206 android/app/src/main/java/com/dial/van/queue/EncryptedCommandQueue.kt
   117 android/app/src/main/java/com/dial/van/security/BiometricGate.kt
    82 android/app/src/main/java/com/dial/van/security/OwnerApprovalKeyManager.kt
   101 android/app/src/main/java/com/dial/van/share/ShareIntentReceiver.kt
   128 android/app/src/main/java/com/dial/van/trading/AccountOnboarding.kt
    94 android/app/src/main/java/com/dial/van/trading/ChartGeometry.kt
   170 android/app/src/main/java/com/dial/van/trading/TradeBook.kt
   159 android/app/src/main/java/com/dial/van/trading/TradingCommandCentreActivity.kt
   191 android/app/src/main/java/com/dial/van/trading/TradingModels.kt
    26 android/app/src/main/java/com/dial/van/trading/TradingRepository.kt
   270 android/app/src/main/java/com/dial/van/trading/ui/AccountOnboardingScreen.kt
    91 android/app/src/main/java/com/dial/van/trading/ui/TradeChartCanvas.kt
   131 android/app/src/main/java/com/dial/van/trading/ui/TradingComponents.kt
   485 android/app/src/main/java/com/dial/van/trading/ui/TradingScreens.kt
  7146 total
  162 android/app/build.gradle.kts
  108 android/app/src/main/AndroidManifest.xml
  105 android/README.md
   57 tests/contracts/test_android_dashboard_navigation.py
  432 total
   39 android/app/src/test/java/com/dial/van/degraded/DegradedModeStoreTest.kt
  175 android/app/src/test/java/com/dial/van/mission/MissionSurfaceTest.kt
  100 android/app/src/test/java/com/dial/van/overlay/VanOverlayChromeTest.kt
   62 android/app/src/test/java/com/dial/van/overlay/VanOverlayInteractionTest.kt
   92 android/app/src/test/java/com/dial/van/queue/EncryptedCommandQueueLogicTest.kt
   60 android/app/src/test/java/com/dial/van/trading/AccountOnboardingTest.kt
   60 android/app/src/test/java/com/dial/van/trading/ChartGeometryTest.kt
   98 android/app/src/test/java/com/dial/van/trading/TradeBookTest.kt
   73 android/app/src/test/java/com/dial/van/trading/TradingModelsTest.kt
   89 android/app/src/test/java/com/dial/van/visual/RiveContractTest.kt
   63 android/app/src/test/java/com/dial/van/visual/VanAuraEnvelopeTest.kt
   99 android/app/src/test/java/com/dial/van/visual/VanCharacterMotionTest.kt
   18 android/app/src/test/java/com/dial/van/visual/VanCharacterOpacityTest.kt
   39 android/app/src/test/java/com/dial/van/visual/VanEffectPolicyTest.kt
  112 android/app/src/test/java/com/dial/van/visual/VanFieldGeometryTest.kt
   72 android/app/src/test/java/com/dial/van/visual/VanFieldRev3Test.kt
  133 android/app/src/test/java/com/dial/van/visual/VanPresenceFrameTest.kt
  128 android/app/src/test/java/com/dial/van/visual/VanPresenceTest.kt
  214 android/app/src/test/java/com/dial/van/visual/VanSceneIdentityTest.kt
   58 android/app/src/test/java/com/dial/van/visual/VanVisualRuntimeTest.kt
   66 android/app/src/test/java/com/dial/van/visual/VanWindFieldMotionTest.kt
   61 android/app/src/test/java/com/dial/van/voice/VoiceRecognitionPolicyTest.kt
   76 android/app/src/test/java/com/dial/van/voice/VoiceSecondPassTest.kt
   86 android/app/src/test/java/com/dial/van/voice/WakeRuntimeTest.kt
 2073 total

## 1. Manifest inventory — Activities / Services / Receivers
AndroidManifest.xml is 108 lines total. Components:

| Component | Type | Manifest line | Exported | Purpose | Composables hosted |
|---|---|---|---|---|---|
| `.onboarding.OnboardingActivity` | Activity (LAUNCHER) | AndroidManifest.xml:28-36 | true | Sole launcher entry; permission/consent walkthrough | `OnboardingScreen` (in OnboardingActivity.kt) |
| `.command.CommandCentreActivity` | Activity, singleTop | AndroidManifest.xml:38-42 | **true (no intent-filter, still exported)** | The main dashboard | `CommandCentreScreen` + 13 module composables |
| `.trading.TradingCommandCentreActivity` | Activity | AndroidManifest.xml:44-48 | false | Trading command center, label "Van Trading" | `TradingCommandCentre` + screens from trading/ui |
| `.overlay.FloatingOverlayService` | Service, FGS specialUse | AndroidManifest.xml:50-57 | false | Persistent floating VAN avatar/HUD (1031 lines) | Compose-in-window overlay chrome |
| `.notification.VanNotificationListenerService` | Service | AndroidManifest.xml:59-66 | true (BIND_NOTIFICATION_LISTENER_SERVICE) | Reads all device notifications | none |
| `.overlay.OverlayRecoveryReceiver` | Receiver | AndroidManifest.xml:68-75 | false | BOOT_COMPLETED / MY_PACKAGE_REPLACED → restart overlay | none |
| `.share.ShareIntentReceiver` | Receiver | AndroidManifest.xml:77-105 | true | ACTION_SEND / SEND_MULTIPLE for text, image, application/* | none |

Permissions requested (lines 4-12): FOREGROUND_SERVICE, FOREGROUND_SERVICE_SPECIAL_USE,
POST_NOTIFICATIONS, RECORD_AUDIO, USE_BIOMETRIC, SYSTEM_ALERT_WINDOW, INTERNET, VIBRATE,
RECEIVE_BOOT_COMPLETED. **No BIND_NOTIFICATION_LISTENER_SERVICE runtime handling seen in scope;
no POST-N runtime request in onboarding audited below.**

### DEFECT-A1 (HIGH): ShareIntentReceiver is a BroadcastReceiver bound to ACTION_SEND
AndroidManifest.xml:77-105 declares `<receiver>` with `ACTION_SEND`/`SEND_MULTIPLE`
`CATEGORY_DEFAULT` intent-filters. Android delivers share sheet intents to **Activities**
(`startActivity`), never to manifest-registered BroadcastReceivers. This component will NOT
appear in the system share sheet and will never be invoked by sharing. "Share to VAN" is
therefore non-functional as declared.

### DEFECT-A2 (MEDIUM): CommandCentreActivity `android:exported="true"` with no intent-filter
AndroidManifest.xml:40. The dashboard — which renders decisions, gateway URL, device id,
browser policy and A4 approval UI — is launchable by any app on the device via explicit
component name. No permission guards it.

### God-file check (line counts, verified by `wc -l`)
- `command/CommandCentreActivity.kt` — **1238 lines**, single file, 13 module composables +
  5 shared UI helpers + 2 JSON extension helpers, all `private` in one file. This IS a
  monolithic god-file: no ViewModel, no repository, no navigation library. Every screen
  does its own `LaunchedEffect { app.gatewayClient.x() }` into local `remember` state.
- `trading/TradingCommandCentreActivity.kt` — **159 lines** (not a god file; it delegates to
  `trading/ui/TradingScreens.kt` at 485 lines).
- `overlay/FloatingOverlayService.kt` — **1031 lines** (the second monolith; out of primary
  scope but in the same pattern).

## 2. Information architecture of the main dashboard (CommandCentreActivity)

Structure (CommandCentreActivity.kt:68-225):
- `private enum class CommandModule` (line 68-88) with 13 entries. Only FOUR are reachable from
  the top tab strip (`primaryModules`, line 165-170): **Home, Chat, Tasks, Activity**.
- The tab strip is 4 `Button`s in a `Row` (line 177-202), 10sp text, `contentPadding` 5dp —
  they are NOT Material tabs and NOT a NavigationBar.
- Everything else is reached by tapping an `AdminActionCard` on the Home scroll (line 251-320).
- `when(selected)` (line 204-223) swaps the body. There is no NavHost, no back stack: a
  manual `BackHandler` (line 154-163) maps the 4 browser sub-pages up to BROWSER_AUTOMATION and
  everything else to OVERVIEW.

Navigation depth: **max 3** (Home → Browser & Automation → Browser Tasks). All other modules
are depth 2. Home itself is one long `LazyColumn` of 10 cards (line 251-320).

Home ("Overview") card list, in order, with the exact owner-visible subtitle string:
| # | Card title | Subtitle (verbatim) | line |
|---|---|---|---|
| 1 | VAN presence card | "Hermes / gateway reachable" / "Hermes / gateway not confirmed" | 269-272 |
| 2 | Chat | "Issue an owner instruction through the signed gateway" | 280 |
| 3 | Decisions | "N open decision(s) returned by the gateway" / "Loading authoritative decisions…" | 284-286 |
| 4 | Projects | "N registered project context(s)" / "Loading project registry…" | 291-293 |
| 5 | Tasks | "Inspect local queued and dispatched owner work" | 297 |
| 6 | Browser & Automation | "Runtime summary, owner escalations, browser tasks, managed sessions and governed policy" | 302 |
| 7 | Systems | "Hermes, gateway and Google mesh health" | 307 |
| 8 | Connections | "Gateway enrollment, device pairing and secure transport state" | 310 |
| 9 | Settings | "Floating VAN and owner-facing runtime controls" | 313 |
| 10 | Trading | "Open the read-first VATI trading command center" | 316 |

### Verdict: engineering control panel, not a personal assistant
Owner-visible strings that are internal/engineering vocabulary, all on screen:
- **Raw enum name rendered directly to the owner**: `CommandCentreActivity.kt:1214`
  `Text(it.name, color = statusColor(it), fontSize = 9.sp)` — the owner literally reads
  `LOCAL_DRAFT`, `SUBMITTING`, `APPROVAL_REQUIRED`, `ACCEPTED`, `IN_FLIGHT`, `SUCCEEDED`,
  `FAILED`, `CANCELLED`, `EXPIRED` (VanCommandController.kt:28-38) at 9sp under each bubble.
- "This action is **A4**. Approval signs the gateway-issued one-time **challenge** with the
  paired device key after **BIOMETRIC_STRONG** authentication." — line 295-298.
- Button label "**Approve A4 action**" — line 304.
- "A4 privileged commands remain **fail-closed** …" — line 1115.
- "the command **HMAC** credential are active" — line 1081.
- "Reason: ${esc.optString("**reason_code**")}" — line 749.
- "Current: ${esc.optString("**current_scope_json**").take(300)}" — line 751, dumping raw JSON.
- "Requested extension: ${esc.optString("**requested_scope_delta_json**").take(300)}" — line 752.
- Raw browser task line: "${status} • ${strategy} • ${**autonomy_tier**}" — line 831.
- "State reason: ${**error_code**}" — line 837.
- Evidence rows: "${kind} • ${**source_trust**} • ${**injection_assessment**}" — line 853.
- "Truth ${truth_sha.take(12)} • repo ${**repo_sha**.take(12)}" — line 555.
- "Registry: ${**registry_version**}" / "Principal: ${raw JSONObject.toString().take(260)}" — line 1015-1016.
- "**Degraded**: ${h.optJSONArray("degraded")?.toString()}" — raw JSON array — line 1005.
- "Policy ${**policy_version**} • max **autonomy tier** ${max_autonomy_tier}" — line 705, 942.
- "Session **leases** required: true/false", "**Mutation default deny**: true/false",
  "**Download default deny**: true/false" — lines 943-945, printing Kotlin booleans.
- "Event": `Text(event.optString("event_type"))` + `payload.toString().take(360)` — raw JSON
  blob as the owner's Activity feed — lines 598-603.
- Sections headed "Owner **escalations**", "Policy & **capabilities**", "**Truth**" button.
- The whole app calls its own explanatory footnotes `TruthMessage` (line 1175).

There is **no** greeting, no name, no time-of-day, no agenda, no "here's what I did", no
summary in ordinary English. Every module is a CRUD view over a gateway JSON endpoint.
Closest thing to a personal-assistant affordance is the Chat module's message list.

## 3. Networking — VanGatewayClient.kt (535 lines)

Transport: raw `java.net.HttpURLConnection`. No OkHttp, no Retrofit, no interceptors, no
connection pooling configuration, no certificate pinning.

### Base URL policy
- `baseUrl` from EncryptedSharedPreferences, else `BuildConfig.VAN_GATEWAY_BASE_URL`
  (VanGatewayClient.kt:41-63).
- `normalizeGatewayBaseUrl` (line 65-75) **requires https**, except `http://127.0.0.1` /
  `http://localhost` when `BuildConfig.DEBUG`. Release builds `check(BuildConfig.DEBUG)` and
  crash if no URL is injected (line 59-61). This is genuinely sound.

### Auth headers (only one scheme)
`applyIngressAuth` (line 497-502) sets exactly two headers on every authenticated call:
`X-Van-Ingress-Token` and `X-Van-Device-Token`. Both `error(...)` (throw) if unset. There is
**no** Authorization header, no bearer, no mTLS.

### HMAC signing — real, and only on POST /v1/commands
`dispatchCommand` (line 340-429): builds a 19-field `|`-joined canonical string (line 365-385)
covering v2, command_id, idempotency_key, device_id, issued_at, action_class, project_id,
turn_id, origin_channel, principal_type, requested_by, expires_at, nonce, capsule rev+hash,
speech_evidence_ref, no_stale_replay, context_trust, text — then `hmacSha256` with
`Mac.getInstance("HmacSHA256")` over the stored device secret (line 463-468). Real HMAC-SHA256,
hex encoded. `signature_version: 2`.
- **Note**: the canonical field separator is a literal `|` with no length-prefixing or escaping
  (line 385). Any field containing `|` (notably the free-text `text`, which is last so it is
  partially protected) could in principle shift the canonicalisation; `text` being last
  mitigates the classic attack but `project_id`, `turn_id`, `speech_evidence_ref` are not escaped.

### Complete endpoint inventory called from Android
POST: `/v1/devices/pair` (118, unauthenticated by design), `/v1/commands` (421),
`/v1/decisions/{id}/resolve` (186), `/v1/trading/accounts/action` (167),
`/v1/missions/{id}/cancel` (264), `/v1/missions/{id}/message` (271),
`/v1/understanding/{id}/confirm|correct|reject` (288, 293, 301),
`/v1/understanding/adaptation/{id}/revert|confirm` (306, 310),
`/v1/permissions/{id}/revoke` (319).
GET: `/health` (135), `/v1/google/mesh` (137), `/v1/briefing` (139), `/v1/trading/trades` (142),
`/v1/trading/portfolio` (145), `/v1/trading/accounts` (147), `/v1/trading/market-state` (150),
`/v1/trading/risk` (153), `/v1/trading/trades/{id}` (156), `/v1/trading/bars` (160),
`/v1/decisions` (182), `/v1/projects` (193), `/v1/projects/{id}/truth` (197), `/v1/attention` (201),
`/v1/browser/status|tasks|escalations|policy` (205-217), `/v1/browser/tasks/{id}/evidence` (221),
`/v1/missions` (233), `/v1/missions/{id}` (237), `/v1/missions/{id}/activity` (241),
`/v1/missions/{id}/evidence` (245), `/v1/needs-you` (250), `/v1/activity` (255),
`/v1/capabilities/status` (259), `/v1/understanding` (283), `/v1/permissions` (315),
`/v1/autonomy` (322), `/v1/technology-radar` (325), `/v1/eval` (329), `/v1/events` (333).
= 10 POST + 30 GET methods.

**Of those 40 methods, only 14 are ever called from a UI/app class.** Verified call sites
(grep over android/app/src/main excluding gateway/): health, decisions, projects, projectTruth,
resolveDecision, events(0), browserStatus/Tasks/Escalations/Policy/Evidence, googleMesh,
pairThisDevice, dispatchCommand, tradingTrades, tradingAccountAction (+ the trading reads via
TradingRepository). **Never called anywhere: `missions()`, `mission()`, `missionActivity()`,
`missionEvidence()`, `needsYou()`, `activityFeed()`, `capabilityStatus()`, `understanding()`
and its 5 mutators, `permissions()`, `revokePermission()`, `autonomy()`, `technologyRadar()`,
`evalReport()`, `briefing()`, `attention()`, `cancelMission()`, `messageMission()`.**

### Retry: NONE
There is no retry, no backoff, no rate limiting, no circuit breaker anywhere in
VanGatewayClient.kt. Every failure throws `GatewayHttpException` (line 535) straight to the
caller, where a Compose `runCatching{}.onFailure{ error = it.message }` puts the raw exception
message on screen (e.g. `gateway_http_503: {...}`).
The only "retry" in the whole app is the 60s health loop (VanApplication.kt:97-104) and
`QueueReplayer.replayAsync()` which is called **exactly once**, at `onCreate`
(VanApplication.kt:78). Nothing re-triggers a replay when connectivity returns — there is no
`ConnectivityManager` / `NetworkCallback` registration anywhere in the module (grep confirms
zero hits for ConnectivityManager/NetworkCallback/WorkManager).

### Timeouts
connect 15s / read 60s for POST (line 484-485), connect 15s / read 30s for GET (line 508-509),
connect 15s / read 90s for the trading account action (line 172-173).

### Polling intervals
- `/health` every **60 000 ms** — VanApplication.kt:199 `GATEWAY_HEALTH_INTERVAL_MS = 60_000L`,
  loop at VanApplication.kt:97-104. This runs forever on `Dispatchers.Default` for the whole
  process lifetime, including when no Activity is visible and the screen is off.
- `/v1/events` — **not polled at all**. The single call site is
  `CommandCentreActivity.kt:580`, `app.gatewayClient.events(0)` inside a `LaunchedEffect(Unit)`
  in `ActivityModule`, i.e. once per entry into the Activity tab, always `after_seq = 0`. The
  cursor is never advanced, never persisted.
- Confirms the other auditors: no SSE, no WebSocket, no FCM. grep for
  `EventSource|WebSocket|FirebaseMessaging|sse` in android/app/src/main → zero hits.

## 4. Command path — owner input → gateway → UI

Path (all verified):
1. Typed: `ChatModule` OutlinedTextField → `Send` → `app.commandController.submitText(text,
   VanCommandSource.CHAT)` — CommandCentreActivity.kt:330-336.
2. Spoken: `VoiceInputManager` → `VanApplication.onFinalResult` → same `submitText(..., VOICE,
   turnId, speechEvidenceRef)` — VanApplication.kt:154-167. (Voice button at
   CommandCentreActivity.kt:337 calls `app.voiceSession.beginOwnerTurn()`.)
3. `VanCommandController.submit` (VanCommandController.kt:127-167) appends an OWNER bubble with
   status `LOCAL_DRAFT`, sets `submitting = true`, then one-shot `gateway.dispatchCommand(...)`.
4. `recordResponse` (line 244-308) maps the wire status to one of 9 `VanCommandStatus` and
   appends a VAN bubble.
5. `CommandMessageBubble` (line 1185-1218) renders the text plus **the raw enum name** at 9sp.

### What the owner sees per lifecycle state
| Concept | Implemented? | What the owner sees | Evidence |
|---|---|---|---|
| heard | partial | voice partial text goes to `voiceUi.partial` (overlay only), not into Chat | VanApplication.kt:149-152 |
| understood | **no such state** | — | VanCommandStatus has no equivalent |
| planned | **no such state** | — | — |
| authorized | yes (A4 only) | amber card "Owner approval required" + resolved_action_id + "Approve A4 action" | CommandCentreActivity.kt:279-316 |
| submitted | yes | own bubble text "Dispatching through VAN gateway…" while `submitting` | line 340-342 |
| executing | **collapsed** | wire `executing`/`verifying`/`submitted`/`accepted` all map to `ACCEPTED` | VanCommandController.kt:248 |
| verified | yes, if the gateway returns it in the HTTP response | "The requested postcondition has been verified." | line 287-288 |
| failed | yes | "The command was rejected, failed, or could not be verified." / "Command dispatch failed: <raw exception>" | line 289-290, 316 |

### Honest, but permanently frozen
The default response text is **"Hermes accepted the command. Completion has not been confirmed
yet."** (VanCommandController.kt:283-284). That is honest — there is no optimistic "Done".
`publishCommandVisualStatus` (VanGatewayClient.kt:432-461) is careful for the same reason and
its comment says so: "Map protocol truth to presence **without inventing task completion**".

### DEFECT-B1 (CRITICAL): a completion can never arrive
`recordResponse` is the only writer of message status, and it is only called from the single
synchronous `dispatchCommand` HTTP response (VanCommandController.kt:162, 221). There is:
- no polling of `/v1/commands/{id}`, no such client method at all;
- no polling of `/v1/events` — the only call is `events(0)` in `ActivityModule`'s
  `LaunchedEffect(Unit)` (CommandCentreActivity.kt:580), and its result is **never joined back
  to conversation messages** (it is rendered as a separate raw-JSON list);
- no `after_seq` cursor persisted anywhere (always literal `0`);
- no SSE/WebSocket/FCM (grep: zero hits).

Therefore every long-running command is displayed as `ACCEPTED` **forever**, for the whole
process lifetime, and the conversation itself is in-memory only (`MutableStateFlow` in a class
held by `VanApplication`) — it is lost on process death and never persisted. The app is honest
about not knowing, and then structurally incapable of ever finding out.

### DEFECT-B2 (HIGH): the Chat history is not durable and not restored
`VanConversationState.messages` lives in `VanCommandController._state`
(VanCommandController.kt:86). Nothing writes it to disk. Process death = total history loss,
including any pending A4 approval (`pendingA4Approval`, line 79), whose challenge then expires
silently.

### DEFECT-B3 (MEDIUM): unknown gateway statuses default to ACCEPTED
`else -> VanCommandStatus.ACCEPTED` (VanCommandController.kt:255). A status string the client
does not recognise is optimistically shown as accepted rather than unknown.

## 5. Mission surfaces — CONFIRMED: no Compose screen consumes them
- `mission/MissionModels.kt` (197 lines) and `mission/MissionRepository.kt` (174 lines) contain
  a genuinely good owner-language layer: `ownerReadableStatus` produces "Waiting for you",
  "Working: fetching", "Done, and checked", "Finished, but Van could not confirm it worked",
  "Partly done" (asserted in MissionSurfaceTest.kt:42-60).
- **`MissionRepository` is never constructed.** `grep -rn "MissionRepository(" android/` returns
  exactly one hit: its own declaration at MissionRepository.kt:20. No Activity, Service,
  Composable or `VanApplication` field references it.
- `VanApplication` (VanApplication.kt:34-57) declares 12 lateinit singletons; `MissionRepository`
  is not among them.
- The gateway client methods it wraps (`missions`, `needsYou`, `activityFeed`, `understanding`,
  `permissions`, `capabilityStatus`) are called nowhere else either.
- The only consumer is `android/app/src/test/java/com/dial/van/mission/MissionSurfaceTest.kt`
  (175 lines), which tests `MissionParsing` against hand-built `JSONObject`s.

**Verdict: the matrix claim is correct. Mission surfaces = IMPLEMENTED_BUT_ISOLATED (model +
repository + tests exist and are good; zero UI).** The dashboard's "Home", "Tasks" and
"Activity" tabs do NOT use them — they use `/v1/decisions`, the local queue, and raw
`/v1/events` JSON respectively.

## 7. Degraded / offline

`DegradedMode` declares 8 subsystems (DegradedMode.kt:48-63): hermes, gateway, overlay, queue,
notifications, voice, biometric, google.

Real signals exist for only **3**:
- `gateway` — VanApplication.kt:109 (health OK) / 136 (health threw) and QueueReplayer.kt:29,61,64.
- `hermes` — VanApplication.kt:112/118, derived from `health.ok` and `health.hermes.degraded`.
- `google` — VanApplication.kt:128 `applyGoogleMesh(...)` from `health.google_mesh`.

`overlay`, `queue`, `notifications`, `voice`, `biometric` are **hardcoded `WORKING` at
DegradedMode.kt:51-55 and never written again** (grep for `markBroken|markWorking` outside the
store returns only gateway/hermes/google). The app therefore claims the notification listener,
the offline queue, voice I/O and the biometric gate are healthy even when the listener is not
enabled, no biometric is enrolled, and the queue is full of failed items.

Initial state (DegradedMode.healthy(), line 38-46) starts with `google = BROKEN` and
`active = true`, reason "Awaiting Google mesh evidence" — so the app boots into degraded mode
by construction.

`markWorking` (DegradedModeStore.kt:78-94) clears a subsystem but leaves `reason` stale when
another subsystem is still broken (line 90: `if (stillBroken) mode.reason`), so the banner can
name a subsystem that recovered.

**No false-"completed" path found.** `QueueReplayer.replayNow` (QueueReplayer.kt:47-60) removes
a queued command on `accepted|denied|degraded|approval_required|conflict|expired|
rejected_untrusted` and never synthesises a success. The command path is likewise honest (§4).

### DEFECT-C1 (HIGH): the offline queue drains once per process start, and only then
`queueReplayer.replayAsync()` is called at VanApplication.kt:78 and nowhere else. No
`ConnectivityManager.NetworkCallback`, no `WorkManager`, no periodic retry, no trigger when
`/health` recovers (the health loop at VanApplication.kt:97-104 does not call the replayer). A
command queued while offline sits encrypted on disk until the app process is restarted, and
then expires after 24h (`DEFAULT_TTL_MS`, EncryptedCommandQueue.kt:196).

### DEFECT-C2 (HIGH): degraded state is not shown as a list to the owner
`degradedModeStore.state` is collected in CommandCentreActivity.kt:139 and 246 only to compute
`VanPresence.cue(...)` — an avatar headline and glass tint. There is no screen listing the 8
subsystems, their detail strings or their `RestoreAction`. `RestoreAction` (DegradedMode.kt:10-18)
has 7 values and **not one of them is ever rendered or acted on** in any in-scope file.

### DEFECT-C3 (MEDIUM): nothing enqueues owner commands when offline
`VanCommandController.submit` calls `gateway.dispatchCommand` directly and on failure writes a
SYSTEM "Command dispatch failed" bubble (VanCommandController.kt:310-324). It **never** falls
back to `commandQueue.enqueue`. The only producers for the encrypted queue are the notification
listener and the share receiver. So the "offline queue" does not hold owner commands at all.

## 6. Trading UI — the strongest surface in the app

Files: `TradingCommandCentreActivity.kt` (159), `trading/ui/TradingScreens.kt` (485),
`trading/ui/TradingComponents.kt` (131), `trading/ui/TradeChartCanvas.kt` (91),
`trading/ui/AccountOnboardingScreen.kt` (270), `TradingModels.kt` (191), `TradeBook.kt` (170),
`TradingRepository.kt` (26), `ChartGeometry.kt` (94), `AccountOnboarding.kt` (128).

### Navigation — the only real navigation in the app
Actual `androidx.navigation.compose.NavHost` (TradingCommandCentreActivity.kt:96-106) with 7
routes: `overview`, `trades/{view}`, `trade/{id}`, `instrument/{symbol}`, `risk`, `accounts`,
`accounts/add`; plus a Material3 `NavigationBar` with 5 items (line 118-144). Deep link via
`EXTRA_ROUTE` (line 73, 108-110). The overlay deep-links into it
(FloatingOverlayService.kt:539-541).

### Feature matrix
| Feature | Present | Evidence |
|---|---|---|
| Multi-account | yes | `PortfolioSummary.accounts`, `AccountsScreen` TradingScreens.kt:471-485 |
| Account switching | **partial** | scope chips exist only on Overview (`var scope` TradingScreens.kt:75, 91-94). Trades, Risk, Instrument and the chart ignore account scope entirely — there is no shared scope state |
| Positions | yes | `open_positions` → `TradeView.CURRENT`, TradesScreen 246-261; `RiskView.positions` 435-443 |
| History | yes | `TradeView.PAST`, empty copy "No closed trades in the ledger yet." TradeBook.kt:22 |
| Potential trades | yes | `TradeView.POTENTIAL`, TradingScreens.kt:145-149 |
| Alerts | **ABSENT** | grep "alert" in trading/ → zero hits. No alert model, no alert UI, no notification of a trade event |
| Risk | yes, detailed | RiskScreen 400-453: heat, drawdown, day/week P&L, consecutive losses, concentration bars, position risk, mandate limits |
| Charts | yes | `TradeChartCanvas` 91 lines, candlesticks + grid + zones + dashed levels + entry/exit markers + time ticks, driven by pure `ChartGeometry.build` |
| Chat | **no trading chat** | `nav.openChat` is `startActivity(Intent(this, CommandCentreActivity::class.java))` — TradingCommandCentreActivity.kt:88 and 133 |
| Execution status | absent **by design** | "nothing here can place, size, modify or cancel a trade" (TradingScreens.kt:259, header comment lines 60-63) |

### Data source: LIVE GATEWAY, no fixtures — verified
`grep -rniE "TODO|FIXME|placeholder|stub|fixture|sample|demo|mock|hardcod|dummy|fake"` over
`android/app/src/main/java/com/dial/van` excluding visual/ and voice/ returns **no fabricated
data**. Every match is either a doc comment saying there are no fixtures, the word "demo" as a
broker account *mode* (AccountOnboarding.kt:118-125, a real Deriv demo-account concept), or a
number-formatting helper. Confirmed: `TradingRepository` (26 lines) is a thin
`Loaded<Loading|Ready|Unavailable>` wrapper over `VanGatewayClient.trading*` — on failure it
returns `Loaded.Unavailable("Gateway unreachable: …")` (TradingRepository.kt:16) and renders
that reason as amber text (TradingComponents.kt:126). No cache, no last-known-good, no fallback.
Server side confirms the endpoints exist: `backend/van_gateway/app.py:770-783+`
(`/v1/trading/status|trades|portfolio|…`).

### Data-honesty design (genuinely good)
- `SafetyIdentity` LIVE/DEMO/PAPER/READ ONLY/UNKNOWN with the word, not just colour
  (TradingModels.kt:29-34; comment at TradingComponents.kt:79 "Never colour alone").
- `DataState` LIVE/DELAYED/STALE/OFFLINE/SIMULATED/NO DATA/UNKNOWN (TradingModels.kt:37-42),
  worst-wins headline (`overallDataState`, line 74).
- `BarSeries.isSimulated` → renders a "SIMULATED DATA" chip (TradingModels.kt:142,
  TradingScreens.kt:352).
- Kill-switch surfaced loudly (TradingScreens.kt:409, 235).
- `Money` keeps the gateway's raw string alongside the Double (TradingModels.kt:44-48).
This is the one part of the app that reads as a designed product.

### Trading defects
- **DEFECT-D1 (HIGH): "Ask Van about $symbol →" loses all context.** TradingScreens.kt:392,
  314, 208 call `nav.openChat()`, which is
  `startActivity(Intent(this, CommandCentreActivity::class.java))` with **no extras**
  (TradingCommandCentreActivity.kt:88). The owner lands in an empty global chat; the symbol,
  trade id and account are dropped. `CommandCentreActivity` only reads `EXTRA_MODULE`
  (CommandCentreActivity.kt:95), so it does not even open the Chat tab.
- **DEFECT-D2 (MEDIUM): unformatted float caps.** TradingScreens.kt:412, 413, 424 do
  `"cap ${(it.toDoubleOrNull() ?: 0.0) * 100}%"` with no `String.format`. A mandate cap of
  `0.02` renders as **"cap 2.0000000000000004%"**.
- **DEFECT-D3 (MEDIUM): raw ledger keys shown to the owner.** Mandate limits are printed as
  `"$k = $v"` in monospace — `max_open_stop_risk = 0.06` (TradingScreens.kt:446); multipliers
  the same (line 318); market `features` map keys used verbatim as tile labels (line 374).
- **DEFECT-D4 (MEDIUM): a CLI instruction in the mobile UI.** TradingScreens.kt:283 empty state
  reads: "Levels below are from the ledger; import history with **`python -m vati lake …`** to
  see the chart."
- **DEFECT-D5 (MEDIUM): chart text is in raw pixels.** `Paint().apply { textSize = 26f }` /
  `24f` (TradeChartCanvas.kt:41-42) — not `sp`, not density-scaled. On a 3x display these are
  ~8.7dp and ~8dp, and they ignore the system font-size setting entirely.
- **DEFECT-D6 (MEDIUM): the chart is inert.** No pan, no zoom, no crosshair, no tap-to-read.
  `maxVisible` is fixed at 120/150/300 in code (TradingScreens.kt:284, 356).
- **DEFECT-D7 (LOW): repository rebuilt on every presence change.**
  `remember(cue.durableState) { ScreenEnv(TradingRepository(...), …) }`
  (TradingCommandCentreActivity.kt:81) — a Van mood change re-creates the whole env.
- **DEFECT-D8 (MEDIUM): no auto-refresh.** Every trading screen refreshes only on
  `LaunchedEffect(tick)` with a manual `RefreshAction` (TradingScreens.kt:66). Live P&L, floating
  positions and market state are static until the owner taps an 18dp icon.

## 8. Notifications

### VanNotificationListenerService (69 lines)
Parses only `android.title` and `android.text` from `sbn.notification.extras`
(VanNotificationListenerService.kt:36-38). It does **not** read `EXTRA_BIG_TEXT`,
`EXTRA_TEXT_LINES`, actions, or the `Notification.MessagingStyle` history.

Pipeline: policy check → quiet-hours check → `SecretRedactor.redact` → SHA-256 dedup hash →
`app.commandQueue.enqueue(kind = CONTEXT_INGEST, sensitivity = NORMAL, idempotencyKey =
"notif:$hash")` (line 55-62). Payload carries `package`, redacted `title`/`body`, `posted_at`,
`priority`, `untrusted_content: true` (line 45-53).

Redaction (`SecretRedactor`, NotificationPolicy.kt:93-109): OTP-near-keyword regex, standalone
6-digit in <120-char messages, `api_key|token|secret|password|bearer <value>` and PEM private
keys. Reasonable, but purely regex; it will not catch alphanumeric codes, magic links or
`Your code is 4821` when the message is ≥120 chars and the keyword is not within the lookahead.

### DEFECT-E1 (CRITICAL): notification text is dispatched as an owner COMMAND
`QueueReplayer.replayNow` (QueueReplayer.kt:33-45) drains **every** queued item — including
`CONTEXT_INGEST` — and sends it via `gateway.dispatchCommand(text = payload.optString("text",
payload.toString()), actionClass = payload.optString("action_class", "A1"), …)`. A notification
payload has no `text` key, so **the entire JSON blob is sent as the `text` of a signed owner
command**, with `originChannel` defaulting to `"UI"` (VanGatewayClient.kt:351) and
`principal_type = "OWNER_DEVICE"`, `context_trust = "CONVERSATION"` (line 362-364). The
`untrusted_content: true` marker is inside the free-text body, not a protocol field. Any app
that can post a notification can therefore put attacker-chosen text into a device-HMAC-signed
owner command envelope. There is no separate `/v1/context` ingest endpoint and no
`CommandKind` branch in the replayer.

### DEFECT-E2 (HIGH): no owner-facing notification UI at all
`NotificationPolicyStore.setPolicy` and `setQuietHours` (NotificationPolicy.kt:40, 50) are
**never called** — grep over `android/app/src/main` finds no call site. There is no per-app
policy screen, no quiet-hours picker, no list of what was captured, no way to review or delete
ingested notifications. Policy is permanently `NORMAL` and quiet hours permanently disabled
(defaults at line 36, 45).

### DEFECT-E3 (MEDIUM): dedup cache is in-memory only
`recentHashes` is a `ConcurrentHashMap` on the store instance (NotificationPolicy.kt:33) with a
60s window. It is lost on process death, so the same notification re-enqueues after a restart —
except the queue's own `findByIdempotencyKey` (EncryptedCommandQueue.kt:51-54) catches it while
the entry still exists.

## 9. Security — real crypto, not placeholder

| Component | Verdict | Evidence |
|---|---|---|
| `OwnerApprovalKeyManager` (82 lines) | **REAL** | EC `secp256r1` keypair generated **in AndroidKeyStore** (`KeyPairGenerator.getInstance(EC, "AndroidKeyStore")`, line 28), `PURPOSE_SIGN`, `DIGEST_SHA256`, `setUserAuthenticationRequired(true)` (line 35), `setInvalidatedByBiometricEnrollment(true)` (line 36), `setUserAuthenticationParameters(0, AUTH_BIOMETRIC_STRONG)` on R+ (line 39-42) — i.e. **per-use** biometric auth. `SHA256withECDSA` (line 78). Public key exported as PEM at pairing (line 52-59) |
| `BiometricGate` (117 lines) | **REAL** | `prompt.authenticate(promptInfo, BiometricPrompt.CryptoObject(signature))` (line 104-107). The challenge is signed **inside** `onAuthenticationSucceeded` using `result.cryptoObject.signature` (line 84-88) and throws if absent. `BIOMETRIC_STRONG` only (line 114). Prompt success alone is not accepted as authority |
| `EncryptedCommandQueue` (206 lines) | **REAL** | AndroidKeyStore AES-256-GCM key (`setRandomizedEncryptionRequired(true)`, line 167), `AES/GCM/NoPadding`, 12-byte IV prepended, 128-bit tag (line 179-193), blobs stored base64 in `EncryptedSharedPreferences` (AES256_SIV keys / AES256_GCM values, line 34-40) |
| Gateway HMAC | **REAL** | `Mac.getInstance("HmacSHA256")` over the 19-field canonical string, VanGatewayClient.kt:365-386, 463-468 |
| Credential storage | **REAL** | device secret / ingress / device-access tokens only in `EncryptedSharedPreferences` (VanGatewayClient.kt:32-38); pairing response tokens are stripped before being handed back to the UI (line 130-131) |
| HTTPS enforcement | **REAL** | `normalizeGatewayBaseUrl` line 65-75 + release-build Gradle gate (build.gradle.kts:71-93) |

### Security defects
- **DEFECT-F1 (HIGH): `BiometricGate.requestA4Approval` (BiometricGate.kt:22-53) is the
  *weak* variant** — it takes no `CryptoObject` and calls `onApproved()` on any successful
  prompt. It is used for **trading account and credential changes**
  (AccountOnboardingScreen.kt:26). Those are A4-class operations protected only by a UI prompt,
  while the *command* path correctly uses the crypto-bound `requestA4CommandApproval`.
- **DEFECT-F2 (MEDIUM): no certificate pinning.** Plain `HttpURLConnection` with platform trust,
  no `NetworkSecurityConfig` XML (no `res/xml/` directory exists), so any user-installed CA on
  the device can MITM the owner-authority channel below the HMAC layer.
- **DEFECT-F3 (MEDIUM): HMAC canonical string is `|`-joined without escaping**
  (VanGatewayClient.kt:365-385). `text` is last, which blunts the classic attack, but
  `project_id`, `turn_id` and `speech_evidence_ref` are unescaped mid-string fields.
- **DEFECT-F4 (LOW): `OwnerApprovalKeyManager.reset()`** (line 70-74) deletes the enrolled key
  with no re-pairing flow; it is never called from any UI.
- **DEFECT-F5 (MEDIUM):** `CommandCentreActivity` is `exported="true"` (AndroidManifest.xml:40)
  and `ShareIntentReceiver` is `exported="true"` (line 79) with no signature permission.

## 10. State restoration, orientation, tablet, accessibility, theming, UX states

### State restoration / orientation — ABSENT
- `grep -rn "rememberSaveable|onSaveInstanceState|ViewModel\b|configChanges"` over
  `android/app/src/main` + AndroidManifest.xml → **zero hits**. Not a single `rememberSaveable`,
  no ViewModel, no `android:configChanges` on any Activity.
- Consequence, all reset on every rotation / dark-mode toggle / font-size change /
  multi-window resize:
  - selected dashboard module (`var selected by remember`, CommandCentreActivity.kt:138)
  - the chat draft the owner is typing (`var draft by remember`, line 247)
  - every module's fetched data + error (`remember { mutableStateOf(...) }` at lines 235-238,
    349-350, 524-526, 573-574, 617-621, 721-723, 804-806, 872-873, 920-921, 977-979, 1027-1030)
  - onboarding step (`remember { mutableIntStateOf(0) }`, OnboardingActivity.kt:80) — rotating
    mid-onboarding sends the owner back to step 0
  - trading `scope`, `view`, `tf`, `tick` (TradingScreens.kt:72-75, 247-249, 330-335)
- Every `LaunchedEffect(Unit)` re-fires on recomposition after recreate, so every rotation is
  also a fresh round of network calls.
- The conversation itself is lost on process death (see DEFECT-B2).

### Tablet / large screen — ABSENT
No `WindowSizeClass`, no `androidx.window` dependency (build.gradle.kts:126-161), no
`res/layout-sw600dp` or any alternate resource qualifier — `res/` contains only
`drawable/`, `drawable-nodpi/`, `mipmap-anydpi-v26/`, `values/`. Every screen is a single
`fillMaxSize()` LazyColumn with 14dp horizontal padding, so on a tablet it is one stretched
column. `resizeableActivity` is not declared.

### Accessibility — effectively ABSENT
- **Four** `contentDescription`s exist in the entire app: FloatingOverlayService.kt:279 and
  :701, TradingScreens.kt:66, TradingCommandCentreActivity.kt:138. **`CommandCentreActivity.kt`
  (1238 lines) has zero.** So does every trading screen body, `TradeChartCanvas` (an entire
  candlestick chart is a blank `Canvas` to TalkBack) and `AccountOnboardingScreen`.
- **Touch targets below the 48dp minimum:**
  - `RefreshAction`: `Modifier.size(18.dp).clickable(...)` — an **18dp** tap target
    (TradingScreens.kt:66).
  - `TabRowChips`: `padding(horizontal = 12.dp, vertical = 6.dp)` around 12sp text ≈ **~29dp**
    tall (TradingComponents.kt:94).
  - Primary dashboard tabs: `contentPadding = PaddingValues(horizontal = 5.dp, vertical = 5.dp)`
    with 10sp text (CommandCentreActivity.kt:190, 200).
  - Bare clickable `Text`s with no role and no padding: "Ask Van →" (TradingScreens.kt:212, 314,
    392), "+ Add account" (line 476), "Done →" (AccountOnboardingScreen.kt:42).
- **Font sizes** are pervasively 9sp–12sp (e.g. CommandCentreActivity.kt:855 `fontSize = 9.sp`,
  :1209/:1214 9-10sp; FloatingOverlayService.kt:559 `8.sp`) with `maxLines = 1/2`, so raising the
  system font scale truncates rather than reflows.
- No `Modifier.semantics`, no `stateDescription`, no heading semantics, no focus order, no live
  region for the "Dispatching…" status.
- `android:supportsRtl="true"` is declared (AndroidManifest.xml:25) but every string is a
  hard-coded Kotlin literal, so RTL locales get LTR English.

### Dark mode — no choice, and the system setting is ignored
`MaterialTheme(colorScheme = darkColorScheme(...))` is hard-coded at CommandCentreActivity.kt:98,
TradingCommandCentreActivity.kt:75 and OnboardingActivity.kt:49. Zero hits for
`isSystemInDarkTheme`, `lightColorScheme` or dynamic colour. `themes.xml` (7 lines) hard-codes
`#111820` for status bar, nav bar and window background; there is no `values-night/`. The app is
dark-only by construction — defensible as a design choice, but it means the owner's system
theme preference has no effect, and `Theme.Van` inherits from the **deprecated framework**
`android:Theme.Material.NoActionBar`, not a MaterialComponents/AppCompat theme.

### Loading / empty / error states — present, and the best-designed thing outside trading
- Dashboard: `TruthMessage(...)` renders all three, per module — e.g.
  "Loading decisions…" / "No open decisions returned by the gateway." / error in amber
  (CommandCentreActivity.kt:446-448); the same triple exists for projects (540-542), activity
  (592-594), browser tasks (823-825), escalations (740-742), sessions (887-890), policy (935-936).
- Trading: `LoadedBox` gives a spinner + "Reading the ledger…", an amber `Unavailable` reason,
  and `EmptyState(text, hint)` with view-specific empty copy (TradingComponents.kt:115-129,
  TradeBook.kt:22-25).
- **Gap:** errors are raw. `error = it.message` surfaces strings like
  `gateway_http_401: {"detail":...}` (GatewayHttpException, VanGatewayClient.kt:535) and
  `ingress_token_unconfigured` / `not_enrolled` (line 498-499, 358-359) straight to the owner,
  with no retry button on most modules and no guidance.

### DEFECT-G1 (CRITICAL): onboarding never pairs the device
`OnboardingFlow` (OnboardingActivity.kt:101-153) has 5 steps: overlay permission, POST_NOTIFICATIONS,
notification-listener settings, microphone, biometric — then "Enter Command Centre". **There is
no gateway-pairing step.** Pairing lives only inside `ConnectionsModule`
(CommandCentreActivity.kt:1026-1093), which is buried at Home → Connections and only appears when
`!app.gatewayClient.isPaired()`. A first-run owner therefore lands on a dashboard where every
card fails with `ingress_token_unconfigured` (VanGatewayClient.kt:498) and nothing tells them
why or where to go.

### DEFECT-G2 (MEDIUM): onboarding advances on intent launch, not on grant
Steps 0 and 2 do `context.startActivity(settingsIntent); step.intValue++`
(OnboardingActivity.kt:106-114, 130-133) — the step advances immediately, before the owner has
granted anything. Nothing re-checks `Settings.canDrawOverlays` or the enabled-listener list, and
`FloatingOverlayService.start(this)` is called unconditionally at line 52.

### DEFECT-G3 (LOW): onboarding text is developer-facing
"Van will restore overlay position after process death (**START_STICKY + persisted state**)"
— OnboardingActivity.kt:148. Also "Hermes profile van owns agent execution" at line 99.

## 11. Tests

### Local unit tests: 24 files, 2 073 lines, 129 `@Test` methods
| Area | Files | @Test |
|---|---|---|
| visual/ (out of scope) | 12 | 68 |
| voice/ (out of scope) | 3 | 18 |
| trading/ | 4 (AccountOnboardingTest, ChartGeometryTest, TradeBookTest, TradingModelsTest) | 16 |
| mission/ | 1 (MissionSurfaceTest, 175 lines) | 11 |
| overlay/ | 2 | 9 |
| queue/ | 1 (EncryptedCommandQueueLogicTest, 92 lines — pure `QueuedCommand` logic, no Keystore) | 5 |
| degraded/ | 1 (DegradedModeStoreTest, 39 lines) | 2 |

**Zero tests exist for:** `CommandCentreActivity` (1238 lines), `VanCommandController`,
`VanGatewayClient`, `QueueReplayer`, `VanApplication`, `NotificationPolicy` / `SecretRedactor`,
`VanNotificationListenerService`, `ShareIntentReceiver`, `BiometricGate`,
`OwnerApprovalKeyManager`, `OnboardingActivity`, `TradingRepository`,
`TradingCommandCentreActivity`, every Composable in the app.

### Instrumentation / UI / screenshot tests: NONE
- `android/app/src/` contains only `main/` and `test/` — **there is no `androidTest/` source
  set** (`find android -type d -name androidTest` → empty).
- `testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"` is declared
  (build.gradle.kts:30) but no instrumentation dependency is present: `androidTest` gets only
  `androidTestImplementation(composeBom)` (line 129) — no espresso, no
  `androidx.compose.ui:ui-test-junit4`, no `androidx.test:runner`.
- `grep -rln "createComposeRule|AndroidJUnit4|espresso|ActivityScenario|Paparazzi|Roborazzi|screenshot"`
  over `android/` matches exactly one file, and it is
  `android/visual-preview/src/main/kotlin/com/dial/van/preview/VanPreviewSheets.kt` — a
  **separate JVM/AWT module** that renders the avatar art, not the app's screens.
- **Not one line of Compose UI in this app has ever been rendered by a test.**

### `tests/contracts/test_android_dashboard_navigation.py` (57 lines) — a grep, not a test
It `read_text()`s `CommandCentreActivity.kt` and `TradingScreens.kt` and asserts on **substrings
of the Kotlin source**: `assert "horizontalScroll" not in text` (line 10),
`assert 'AdminActionCard("Connections"' in text` (line 22),
`assert "TradeChartCanvas(" not in overview` (line 55). It verifies that certain identifiers do
or do not appear in a file. It executes no Kotlin, renders nothing, and would pass against code
that never compiles. It is a lint rule wearing a test's name.

## 12. Everything stubbed / TODO / placeholder / hardcoded (file:line)

There are **no `TODO`/`FIXME`/`STUB` markers** in the in-scope Kotlin — the gaps are silent.
The inventory of dead, hardcoded or unreachable code:

| # | Item | file:line |
|---|---|---|
| 1 | `MissionRepository` — never constructed | mission/MissionRepository.kt:20 |
| 2 | 18 `VanGatewayClient` methods never called (missions ×4, needsYou, activityFeed, capabilityStatus, understanding ×5, permissions ×2, autonomy, technologyRadar, evalReport, briefing, attention, cancelMission, messageMission) | VanGatewayClient.kt:139, 200, 231-329 |
| 3 | 5 `DegradedMode` subsystems hardcoded `WORKING`, never updated (overlay, queue, notifications, voice, biometric) | degraded/DegradedMode.kt:51-55 |
| 4 | All 7 `RestoreAction` values — never rendered, never acted on | degraded/DegradedMode.kt:10-18 |
| 5 | `NotificationPolicyStore.setPolicy` — no call site | notification/NotificationPolicy.kt:40 |
| 6 | `NotificationPolicyStore.setQuietHours` — no call site | notification/NotificationPolicy.kt:50 |
| 7 | `OwnerApprovalKeyManager.reset()` — no call site | security/OwnerApprovalKeyManager.kt:70 |
| 8 | `BiometricGate.canAuthenticate()` never surfaced — owner is only told "Biometric hardware unavailable" at the moment of approval | security/BiometricGate.kt:16, 29 |
| 9 | `ProjectsModule.truthSummary` — populated only by a manual "Truth" tap, lost on rotation | CommandCentreActivity.kt:525, 559 |
| 10 | `ActivityModule` hardcodes `after_seq = 0`; cursor never advances or persists | CommandCentreActivity.kt:580 |
| 11 | `VanOwnerCommand.approvalToken` — "Deprecated compatibility field; it never grants A4 authority" | control/VanCommandController.kt:55-56 |
| 12 | `VanCommandStatus.SUBMITTING` and `CANCELLED` are declared but never produced by `recordResponse` | control/VanCommandController.kt:30, 36 vs 246-256 |
| 13 | `PortfolioSummary.exposureBySymbol` / `otherCurrencyAccounts` parsed but never rendered | TradingModels.kt:70, 85-86 |
| 14 | `AccountsScreen(onVerify:)` parameter — declared, never passed | trading/ui/TradingScreens.kt:471 |
| 15 | Hardcoded debug gateway `"http://127.0.0.1:8787"` | gateway/VanGatewayClient.kt:62 |
| 16 | Hardcoded 60s health interval, no backoff, no config | VanApplication.kt:199 |
| 17 | Hardcoded 24h queue TTL | queue/EncryptedCommandQueue.kt:196 |
| 18 | Hardcoded `chunked(2)` feature-tile grid, hardcoded `maxVisible` 120/150/300, hardcoded timeframes `listOf("M15","H1","H4","D1")` | TradingScreens.kt:373, 284, 356, 343 |
| 19 | Hardcoded default aliases `"deriv_demo"`, `"ctrader_demo"` in text fields | trading/ui/AccountOnboardingScreen.kt:160, 208 |
| 20 | Hardcoded `SECRET_MARKERS` list | share/ShareIntentReceiver.kt:99 |
| 21 | Only 3 strings in `strings.xml`; every other UI string is a Kotlin literal | res/values/strings.xml:3-5 |
| 22 | `android/README.md` is stale: claims `targetSdk`/`compileSdk` **34** (actual: 36, build.gradle.kts:20, 25); its architecture list omits `trading/`, `mission/`, `control/`, `gateway/` and names a non-existent "Attention" module | android/README.md:14, 44-54 |
| 23 | `ShareIntentReceiver` is a BroadcastReceiver on `ACTION_SEND` — never invoked by the share sheet | AndroidManifest.xml:77-105, share/ShareIntentReceiver.kt:21 |

## 13. Classification

Scale: ABSENT / STUB / SIMULATED / PARTIAL / IMPLEMENTED_BUT_ISOLATED / INTEGRATED / E2E_VERIFIED

| Area | Classification | Justification |
|---|---|---|
| **Overall app** | **PARTIAL** | Real code, real crypto, real gateway reads, no fabricated data anywhere. But one launcher Activity, one god-file dashboard, no ViewModels, no state restoration, no push, no instrumentation test, and first-run pairing is missing from onboarding (DEFECT-G1). |
| **Dashboard IA** | **PARTIAL** (engineering console, not an assistant) | 13 modules in a 1238-line file, 4 tabs + card drill-down, depth ≤3, hand-rolled `when`/`BackHandler` instead of navigation. Every label is protocol vocabulary; raw enum names rendered to the owner at CommandCentreActivity.kt:1214. |
| **Command path** | **PARTIAL** (honest, then terminally frozen) | Typed and voice converge on one signed controller; A4 is cryptographically gated; the app refuses to claim completion ("Completion has not been confirmed yet.", VanCommandController.kt:284). But `recordResponse` is only ever driven by the one HTTP response, so a completion can **never** arrive (DEFECT-B1), and history is in-memory only (DEFECT-B2). |
| **Trading UI** | **INTEGRATED** | Real NavHost with 7 routes, 6 screens + onboarding, live gateway reads via `TradingRepository`, genuine candlestick chart, LIVE/DEMO and LIVE/DELAYED/STALE/SIMULATED honesty chips, kill-switch surfacing, zero fixtures. Short of E2E_VERIFIED only because no UI test exists and account scope is not shared across screens. |
| **Mission surfaces** | **IMPLEMENTED_BUT_ISOLATED** | 371 lines of models + repository with excellent owner-language ("Waiting for you", "Finished, but Van could not confirm it worked") and 11 passing unit tests — consumed by **no** Composable, no Activity, no Application field. Confirms the matrix. |
| **Networking** | **PARTIAL** | Real HMAC-SHA256 v2 envelope, real HTTPS enforcement, real encrypted credential storage, 40 typed endpoints. But raw `HttpURLConnection`, **no retry, no backoff, no connectivity awareness, no push/SSE**, `/v1/events` fetched once with a frozen cursor, and 18 of 40 endpoints are dead code. |
| **Offline** | **STUB** | `EncryptedCommandQueue` is real AES-GCM/Keystore crypto, but the owner's own commands never enter it (DEFECT-C3), and the replayer runs exactly once per process start with no network trigger (DEFECT-C1). "Offline support" is a storage primitive with no lifecycle. |
| **Degraded mode** | **PARTIAL** | 3 of 8 subsystems driven by real `/health` signals; 5 permanently claim WORKING (DEFECT-C2/#3). No degraded screen, no restore actions surfaced. No false-completed path — the honesty invariant holds. |
| **Notifications** | **PARTIAL, and unsafe** | Listener + redaction + dedup + quiet-hours logic are real, but there is **no owner UI whatsoever** (DEFECT-E2) and the replayer feeds captured notification JSON into signed owner commands (DEFECT-E1, critical). |
| **Security** | **INTEGRATED** | Keystore EC P-256 with per-use BIOMETRIC_STRONG, `CryptoObject`-bound challenge signing, AES-GCM queue, HMAC v2 envelope, HTTPS gate in Gradle. Real, not placeholder. Held below E2E_VERIFIED by DEFECT-F1 (trading account changes use the non-crypto prompt), no cert pinning, and zero tests over any of it. |
| **Accessibility / adaptivity** | **ABSENT** | 4 contentDescriptions app-wide, 18dp touch targets, 8–10sp type, no rememberSaveable, no tablet layout, no light theme. |
| **Tests** | **PARTIAL (unit only)** | 129 unit tests over pure logic (mostly visual/voice), 0 instrumentation, 0 screenshot, 0 Compose UI tests; the one "Android dashboard" contract test is source-text grep. |

### The five things that most change what the owner experiences
1. **DEFECT-B1** — a completion can never reach the screen; every command is "accepted" forever.
2. **DEFECT-G1** — first run ends on a dashboard that cannot talk to the gateway, with no pairing step and no explanation.
3. **DEFECT-E1** — notification text is replayed into the signed owner-command channel.
4. **DEFECT-A1** — "share to VAN" is wired to a BroadcastReceiver and never fires.
5. **The dashboard speaks protocol, not English** — raw enums, `reason_code`, `current_scope_json`, `truth_sha`, A4, HMAC, `max_open_stop_risk = 0.06`, and `python -m vati lake …`.
