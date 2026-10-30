# VAN owner feature and screen audit

Audited source: `12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af`. Date: 2026-10-07. The inventory is a static baseline of authoritative requirements, gateway contracts and Android call chains. It makes no live service, device, renderer-asset or deployment readiness claim. Narrow owner-authorized fixes after that baseline are recorded separately below.

The redesign needs a functional registry covering **42 owner features, 55 screen candidates and 165 unique referenced backend method/path contracts**. A route, client method, preview or animation does not establish an integrated owner capability. The candidate files declare required information, supported actions, authority boundaries and happy/error/loading/degraded/offline/stale/access/empty/cancelled acceptance for each feature and screen.

Machine-readable artifacts: [owner-feature-candidates.json](/workspace/van-audit/owner-feature-candidates.json) and [screen-candidates.json](/workspace/van-audit/screen-candidates.json). Their coverage labels describe baseline source coverage, not tested/live status.

## Authority and product requirements

- Authority map assigns one owner per invariant; ledgers cannot decide requirements: [docs/project-state/AUTHORITY_MAP.yaml:14](/workspace/Van/docs/project-state/AUTHORITY_MAP.yaml:14), [docs/project-state/AUTHORITY_MAP.yaml:35](/workspace/Van/docs/project-state/AUTHORITY_MAP.yaml:35).
- Product Design DNA owns Android information architecture and screen-state behavior. Eight primary/more destinations are Home, Attention, Work, Trading, Memory, Projects, Connected and Devices/Settings: [docs/design/VAN_PRODUCT_DESIGN_DNA.md:3](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:3), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:52](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:52).
- Finished Product Blueprint additionally requires mission history/proof, needs-you approvals, Google, share, browser/research, automation/development and learning/security projections. Every owner-visible work item binds one durable mission and retains command/run/evidence/verification identity: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:138](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:138), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:155](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:155), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1322](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1322).
- Security Policy owns the effective action taxonomy: safe local/read, bounded external read, bounded write, destructive/irreversible/send-as-owner with per-occurrence approval, prohibited. The illustrative floating UX A1–A4 list differs and must not become a new authority taxonomy: [docs/SECURITY_POLICY.md:62](/workspace/Van/docs/SECURITY_POLICY.md:62), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:734](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:734).
- Hermes remains the sole model-driven agent runtime. Android is an authenticated deterministic edge; UI controls may not become direct shell/SSH/credential/broker execution or mint authority: [docs/SECURITY_POLICY.md:16](/workspace/Van/docs/SECURITY_POLICY.md:16), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:718](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:718).
- External notifications, shares, pages, provider outputs and documents remain provenance-labelled DATA/CONTEXT. Device authenticity does not prove owner authorship of their content: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:257](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:257), [docs/SECURITY_POLICY.md:88](/workspace/Van/docs/SECURITY_POLICY.md:88).

## Cross-cutting acceptance contract

| State / boundary | Required owner behavior |
|---|---|
| Loading | Skeleton matching final content geometry; retained owner context; duplicate mutations guarded. |
| Content / happy | Live authoritative source, visible source age and links to real records/actions. Effect completion requires independent verification. |
| Empty | Truthful no-records explanation and one supported next action; never use empty for failed or refused data. |
| Error | Specific failure and supported retry; retain draft/action target and unaffected data. |
| Degraded | Name failed plane/subsystem, what still works, what VAN cannot do and applicable restore action. |
| Offline | Visible queue with command/turn identity and freshness/authority limits; no fabricated remote answer or duplicate replay. |
| Stale | Last-known authoritative data with age; cached state cannot confer fresh authority or fresh verified success. |
| Access | Pairing, device binding/proof, platform permission, capability, biometric and provider-consent denials are distinct with recovery. |
| Cancelled / expired / conflict / timeout | Distinct from failure and verified success; terminal actions disabled; no hidden new command on retry. |
| Result truth | accepted/in-flight ≠ verified-complete; decision selection ≠ command-bound approval; response received ≠ answer fully heard; gateway connected ≠ all providers healthy. |

DNA requires all seven screen states at every destination and source declaration at every live panel: [docs/design/VAN_PRODUCT_DESIGN_DNA.md:66](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:66). The current ScreenState type supports this, but screens must supply real age/offline/degraded inputs and malformed health must not silently become healthy: [android/app/src/main/java/com/dial/van/design/ScreenState.kt:16](/workspace/Van/android/app/src/main/java/com/dial/van/design/ScreenState.kt:16), [android/app/src/main/java/com/dial/van/design/ScreenState.kt:85](/workspace/Van/android/app/src/main/java/com/dial/van/design/ScreenState.kt:85), [android/app/src/main/java/com/dial/van/design/ScreenState.kt:127](/workspace/Van/android/app/src/main/java/com/dial/van/design/ScreenState.kt:127). Unified owner-work status and durable command lifecycle are required separately from screen state: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:602](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:602), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:747](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:747).

## Baseline gaps that affect owner control

1. **Mission deep links discard the requested mission.** `work/missions/{missionId}` renders generic WorkRoute without consuming the ID. Backstack persistence also records destination templates rather than concrete arguments. A redesign must preserve target identity across navigation/process recreation: [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:169](/workspace/Van/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:169), [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:245](/workspace/Van/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:245).
2. **Attention mutations discard failures and permit duplicate taps.** Acknowledge, snooze and decision resolution run with only success handling; failed owner choices remain visually unexplained: [android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:167](/workspace/Van/android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:167). Decision records also lack the full product-required risk/choices/evidence/expiry/project contract: [backend/van_gateway/decisions/service.py:21](/workspace/Van/backend/van_gateway/decisions/service.py:21), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:806](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:806).
3. **Voice input state has no UI consumer.** VoiceUi is produced, but the app does not display its partial transcript/errors or provide an end-turn control. Wake/ASR/TTS/runtime code is broader than the visible owner interaction: [android/app/src/main/java/com/dial/van/VanApplication.kt:710](/workspace/Van/android/app/src/main/java/com/dial/van/VanApplication.kt:710), [android/app/src/main/java/com/dial/van/command/work/WorkRoute.kt:140](/workspace/Van/android/app/src/main/java/com/dial/van/command/work/WorkRoute.kt:140), [android/app/src/main/java/com/dial/van/voice/VoiceInterfaces.kt:654](/workspace/Van/android/app/src/main/java/com/dial/van/voice/VoiceInterfaces.kt:654).
4. **New notification sources never enter the app-policy list.** At baseline the settings list reads explicit `policy_*` keys, while arrival never records a normal source; the UI nevertheless says arriving apps appear. This blocks normal discovery of per-app controls: [android/app/src/main/java/com/dial/van/notification/NotificationPolicy.kt:93](/workspace/Van/android/app/src/main/java/com/dial/van/notification/NotificationPolicy.kt:93), [android/app/src/main/java/com/dial/van/notification/VanNotificationListenerService.kt:21](/workspace/Van/android/app/src/main/java/com/dial/van/notification/VanNotificationListenerService.kt:21), [android/app/src/main/java/com/dial/van/command/modules/NotificationPolicyModule.kt:125](/workspace/Van/android/app/src/main/java/com/dial/van/command/modules/NotificationPolicyModule.kt:125).
5. **State wrappers often receive only loading/error/content.** Trading common conversion cannot emit degraded/offline/stale. Memory/Attention/Projects lack key real state inputs; optional context/truth errors can become default data. Retained content can hide refresh errors without a degraded cue: [android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt:34](/workspace/Van/android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt:34), [android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:68](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:68), [android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:72](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:72).
6. **Learning/security/reminder controls are backend-only or client-only.** Understanding confirmation/correction/rejection, adaptation review/reversal, standing permissions/revocation/autonomy, reminder management, full-memory erasure, context history and strategic rationale need owner workflows. Existing function names do not establish reachable UI: [android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt:883](/workspace/Van/android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt:883), [android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt:915](/workspace/Van/android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt:915), [android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt:1011](/workspace/Van/android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt:1011), [backend/van_gateway/app.py:2055](/workspace/Van/backend/van_gateway/app.py:2055), [backend/van_gateway/understanding/api.py:259](/workspace/Van/backend/van_gateway/understanding/api.py:259).
7. **Legacy trading links do not address the new inner routes.** Activity extras are ignored; overlay `trade/{id}`/`trades/{view}` paths differ from `positions/{id}`/`potential`/`history`: [android/app/src/main/java/com/dial/van/trading/TradingCommandCentreActivity.kt:17](/workspace/Van/android/app/src/main/java/com/dial/van/trading/TradingCommandCentreActivity.kt:17), [android/app/src/main/java/com/dial/van/trading/TradingCommandCentreActivity.kt:47](/workspace/Van/android/app/src/main/java/com/dial/van/trading/TradingCommandCentreActivity.kt:47), [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:68](/workspace/Van/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:68).
8. **Activity and some diagnostics still expose engineering payloads.** ActivityModule prints raw event type/JSON and 10sp text, contrary to the owner-language/12sp product contract. Use grouped mission activity/evidence and owner-facing sentences: [android/app/src/main/java/com/dial/van/command/modules/WorkModules.kt:108](/workspace/Van/android/app/src/main/java/com/dial/van/command/modules/WorkModules.kt:108), [backend/van_gateway/mission/api.py:259](/workspace/Van/backend/van_gateway/mission/api.py:259), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1340](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1340), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:32](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:32).
9. **Floating parity is incomplete.** Floating surfaces need attention/approval/task/voice state from shared repositories; they currently present conversation/chrome/trades and lack the complete attention/action lifecycle. Command polling belongs to an application-scoped owner work observer rather than only the composed Work screen: [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:601](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:601), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:850](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:850).

There are also stale comments that must not be treated as implementation truth: MissionRepository is constructed from Home/Work at this baseline, and trading positions/events/potential/history/assessment routes exist. The audit used execution/callsite declarations rather than those comments.

## Owner feature registry

`partial` means some code/call chain exists but functional/state gaps remain. `missing` means no complete reachable owner workflow was located, even if a backend/client contract exists. `external` identifies source implementation whose asset/runtime/device acceptance remains outside this passive audit. No registry label asserts live readiness.

| ID | Domain and owner goal | Required controls | Baseline |
|---|---|---|---|
| OF-HOME-001 | **Current state and briefing** — Know what needs attention now. | open a real mission/attention/project/trade destination; refresh | partial |
| OF-COMMAND-001 | **Unified owner command and conversation** — Instruct VAN once through text, voice or contextual control. | draft; submit; mic; retry using same identity when transport is ambiguous; cancel where supported | partial |
| OF-MISSION-001 | **Mission detail, activity and proof** — Inspect what VAN did and why completion is credible. | open mission; open evidence; read timeline | partial |
| OF-MISSION-002 | **Mission intervention** — Stop or add direction to the existing mission. | cancel active mission; message existing mission | partial |
| OF-ATTENTION-001 | **Attention triage** — Handle or defer items by urgency. | open; acknowledge; snooze | partial |
| OF-DECISION-001 | **Owner decisions and Needs You** — Understand why owner input is needed and record a choice. | inspect evidence; approve/select; reject; defer through supported attention controls; add instruction to bound mission | partial |
| OF-APPROVAL-001 | **Per-occurrence elevated action approval** — Approve the exact consequential effect deliberately. | inspect intent; approve with bound hardware-key biometric proof; reject/dismiss | partial |
| OF-REMINDER-001 | **Reminder lifecycle** — Create a timed reminder and manage it. | create using explicit/natural time; resolve; cancel; inspect upcoming | missing |
| OF-MEMORY-001 | **Owner facts CRUD** — Tell VAN a fact, correct it or make it forget. | state fact; correct via superseding statement; forget one fact | partial |
| OF-MEMORY-002 | **Full memory inspection and erasure** — Read everything VAN holds and control retention. | inspect export; forget a store; forget all owner-derived memory; inspect retention | partial |
| OF-MEMORY-003 | **History and conflict resolution** — See changed beliefs and unresolved contradictions. | open fact history; inspect each conflict side; state correction | partial |
| OF-LEARNING-001 | **Owner understanding and corrections** — Inspect and correct what VAN believes about the owner. | confirm; correct; reject | missing |
| OF-LEARNING-002 | **Adaptation review and rollback** — Approve or reverse learned changes. | confirm adaptation; revert adaptation | missing |
| OF-LEARNING-003 | **Goals, decisions and learned strategies** — Inspect continuity, conflicts and learning limits. | inspect goal conflict; review decision history; inspect evidence/eval | missing |
| OF-PROJECT-001 | **Project inventory and detail** — Know project health, current work and next decisions. | open project; open bound work/attention; context-bound command | partial |
| OF-PROJECT-002 | **Strategic rationale memory** — Remember why choices were made and rejected. | inspect rationale; record owner rationale | missing |
| OF-AUTHORITY-001 | **Permissions and autonomy** — Know and revoke what VAN may do unprompted. | inspect grant; revoke grant; inspect authority descriptor and readiness | missing |
| OF-GOOGLE-001 | **Google account planes and revocation** — Know which Google capabilities work and disconnect access. | inspect plane; disconnect owner Workspace OAuth; follow supported consent restoration | partial |
| OF-GOOGLE-002 | **Workspace owner operations** — Use mail, calendar, Drive, contacts and tasks through VAN. | search mail/Drive; draft mail; send only with fresh approval; read/insert/reschedule calendar; resolve contact; list tasks; invoke declared typed action | partial |
| OF-KNOWLEDGE-001 | **Research and knowledge providers** — Obtain citable knowledge with explicit provider readiness. | ask through command controller; inspect citations; inspect readiness; request declared notebook mutation | partial |
| OF-AUTOMATION-001 | **Automation and standing intents** — Inspect bounded automation and disable standing work. | request automation through controller; inspect run/evidence; disable standing intent through supported owner command | missing |
| OF-BROWSER-001 | **Browser task supervision and escalations** — Review browser work and intervene when it needs the owner. | inspect task evidence; resolve escalation decision; open live browser | partial |
| OF-BROWSER-002 | **Interactive native browser** — Browse the real remote Chromium session from the phone. | navigate/search; tabs; back/forward/reload; tap/swipe/fling/pinch/long press; open shortcut; suspend/end session | external |
| OF-BROWSER-003 | **Owner/Hermes takeover and page assistance** — Ask VAN about the visible page and keep immediate owner control. | take control by touch; delegate bounded work; ask about visible page; voice control | partial |
| OF-BROWSER-004 | **Downloads, uploads and clipboard** — Transfer files under explicit owner control. | inspect/save/open/delete supported downloads; explicit phone upload; policy-bound clipboard | partial |
| OF-VOICE-001 | **Wake, recognition, interruption and spoken result** — Use Hey Van and receive an audible safe answer. | start/end listening; stop speaking; barge in; correct/reissue; continue same mission; repeat cached answer | partial |
| OF-VOICE-002 | **Speech personalization** — Correct pronunciation/recognition and control adaptation. | capture correction; inspect/reset personal speech model when supported | partial |
| OF-OVERLAY-001 | **Floating assistant and contextual workboard** — Access current work and immediate controls while using other apps. | single tap board toggle; double tap Command Centre; long press quick controls; drag/dock; bottom-X dismiss; minimize/restore; context command/voice | partial |
| OF-NOTIFICATION-001 | **Notification capture and privacy policy** — Choose which apps VAN reads and when it interrupts. | set app policy; configure quiet hours; open Android listener permission; inspect generated attention | partial |
| OF-SHARE-001 | **Share to VAN** — Bring external text/images/files into context safely. | Android share intake; inspect imported context; explicit separate owner instruction | partial |
| OF-PROVISION-001 | **Owner device onboarding and identity** — Use the app only after a supported readiness journey. | apply signed provisioning payload; pair/bind; grant Android permissions; run readiness check; re-enroll through supported installer flow | partial |
| OF-SETTINGS-001 | **Settings, security and device readiness** — Adjust local preferences and restore degraded capability. | change supported local preference; open system permission settings; start/stop supported local services; perform explicit restore action | partial |
| OF-DIAGNOSTICS-001 | **Owner diagnostics and correlation** — Understand a failure and inspect safe evidence. | inspect trace/evidence; copy redacted diagnostic receipt; retry supported request | partial |
| OF-TRADING-001 | **Trading overview, portfolio and risk** — Know current market/trading health and exposure. | open position/account/risk/history detail; refresh | partial |
| OF-TRADING-002 | **Positions, charts, history and opportunity intelligence** — Inspect a trade rationale and its verified outcome. | open trade; pan/zoom/crosshair; inspect evidence/history/opportunity | partial |
| OF-TRADING-003 | **Trading account setup and controlled actions** — Connect/manage supported trading accounts securely. | request exact account challenge; perform supported signed account action; complete broker OAuth privately | partial |
| OF-TRADING-004 | **Strategy certificate promotion** — Promote only a currently validated strategy under owner authority. | inspect validation; biometric approve exact certificate; promote; verify authoritative readback | partial |
| OF-TRADING-005 | **Trading halt and ticket decisions** — See risk halt state and perform only permitted protection actions. | halt through supported signed owner command; inspect/confirm supported ticket with fresh proof | partial |
| OF-DEV-001 | **Development project hub and task control** — Inspect and steer bounded project work. | inspect project/task/evidence; submit only actions advertised by upstream contract; owner steer/pause/resume/cancel/retry where allowed | partial |
| OF-DEV-002 | **Workspace evidence and terminal views** — Inspect bounded implementation evidence without a second execution agent. | open workspace; inspect diff/log/evidence; invoke only supported upstream actions | partial |
| OF-ARTEMIS-001 | **ARTEMIS test console** — Open the governed Android test surface. | request device-proved console session; open governed embedded console | external |
| OF-EMBODIMENT-001 | **Functional Rive state projection** — Read VAN state through motion plus accessible information. | board gesture parity; reduced-motion mode; renderer diagnostic/acceptance | external |

## Endpoint, information and acceptance details

Every endpoint below is an exact backend method/path contract with source evidence. An internal runtime/control reference is a downstream implementation contract, not authorization to expose its credential or execute it directly from Android. The owner path uses the declared command, device proof, scoped grant and approval mechanism. Runtime/internal-control routes need safe owner read projections or controller-bound requests.

### OF-HOME-001 — Current state and briefing

Information: VAN activity; top attention; active work; upcoming reminders; recent verified changes; gateway/Hermes health; selected project; queue count.

Required actions: open a real mission/attention/project/trade destination; refresh.

Authority: [docs/design/VAN_PRODUCT_DESIGN_DNA.md:55](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:55), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:789](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:789).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /health` | [backend/van_gateway/app.py:1479](/workspace/Van/backend/van_gateway/app.py:1479) | outer_ingress_probe |
| `GET /v1/briefing` | [backend/van_gateway/app.py:1925](/workspace/Van/backend/van_gateway/app.py:1925) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/missions` | [backend/van_gateway/mission/api.py:188](/workspace/Van/backend/van_gateway/mission/api.py:188) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/attention` | [backend/van_gateway/app.py:2413](/workspace/Van/backend/van_gateway/app.py:2413) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/trading/assessment` | [backend/van_gateway/app.py:2736](/workspace/Van/backend/van_gateway/app.py:2736) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt:66](/workspace/Van/android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt:66), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:54](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:54), [android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt:92](/workspace/Van/android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt:92), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:34](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:34), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:60](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:60). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Aggregation must retain independent source failures and age; all meaningful rows must navigate to a concrete record.

Happy acceptance: Display a source-backed overview and open each highlighted record.

Error acceptance: A failed source is visible without erasing independent content.

### OF-COMMAND-001 — Unified owner command and conversation

Information: thread and selected project; delivery status; command/mission identity; owner-safe response; authority target and expected effect.

Required actions: draft; submit; mic; retry using same identity when transport is ambiguous; cancel where supported.

Authority: [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:637](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:637), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:689](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:689), [docs/SECURITY_POLICY.md:62](/workspace/Van/docs/SECURITY_POLICY.md:62), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:157](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:157).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/commands` | [backend/van_gateway/app.py:1702](/workspace/Van/backend/van_gateway/app.py:1702) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/commands/{command_id}` | [backend/van_gateway/app.py:1865](/workspace/Van/backend/van_gateway/app.py:1865) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

No dedicated current Android surface callsite located for this workflow; runtime/local code or declared client methods can still exist.

Baseline coverage: **partial**. Voice presentation is not consumed by UI; project-aware and module actions must preserve one controller/authority path.

Happy acceptance: A command becomes a durable mission; accepted/in-flight is displayed as pending, and only verified completion shows success.

Error acceptance: Refused, unknown, timed-out and conflicting replies remain distinct; no silent ACCEPTED fallback.

### OF-MISSION-001 — Mission detail, activity and proof

Information: goal/status; constraints; authority envelope in owner language; activities; execution identities; evidence refs; verification receipt.

Required actions: open mission; open evidence; read timeline.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:602](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:602), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:621](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:621), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:57).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/missions` | [backend/van_gateway/mission/api.py:188](/workspace/Van/backend/van_gateway/mission/api.py:188) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/missions/{mission_id}` | [backend/van_gateway/mission/api.py:196](/workspace/Van/backend/van_gateway/mission/api.py:196) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/missions/{mission_id}/activity` | [backend/van_gateway/mission/api.py:212](/workspace/Van/backend/van_gateway/mission/api.py:212) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/missions/{mission_id}/evidence` | [backend/van_gateway/mission/api.py:227](/workspace/Van/backend/van_gateway/mission/api.py:227) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/activity` | [backend/van_gateway/mission/api.py:259](/workspace/Van/backend/van_gateway/mission/api.py:259) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:34](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:34), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:60](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:60), [android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:74](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:74), [android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:69](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:69), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:62](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:62). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. mission/{missionId} deep link does not pass ID to WorkRoute at baseline; grouped activity endpoint exists but ActivityModule renders raw event payload JSON.

Happy acceptance: A link opens the named mission, persisted across recreation, with inspectable proof of completion.

Error acceptance: Unknown mission/evidence is visible; absent verification is not success.

### OF-MISSION-002 — Mission intervention

Information: current mission state; whether stopping is supported; instruction acknowledgment vs execution.

Required actions: cancel active mission; message existing mission.

Authority: [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:814](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:814), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:602](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:602).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/missions/{mission_id}/cancel` | [backend/van_gateway/mission/api.py:380](/workspace/Van/backend/van_gateway/mission/api.py:380) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/missions/{mission_id}/message` | [backend/van_gateway/mission/api.py:392](/workspace/Van/backend/van_gateway/mission/api.py:392) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:125](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:125), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:126](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:126). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. No pause/resume/retry mission API is declared here; do not manufacture these controls. A mission message records an event and does not itself transition execution.

Happy acceptance: Cancel reads back CANCELLED; a message appears on the same mission record.

Error acceptance: Transition conflict/unknown mission keeps the prior record and offers supported recovery.

### OF-ATTENTION-001 — Attention triage

Information: INFO/FOLLOW_UP/BLOCKER/URGENT; source/project; state; created/updated/snooze time; payload and destination.

Required actions: open; acknowledge; snooze.

Authority: [docs/design/VAN_PRODUCT_DESIGN_DNA.md:56](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:56), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:48](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:48), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:806](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:806).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/attention` | [backend/van_gateway/app.py:2413](/workspace/Van/backend/van_gateway/app.py:2413) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/attention/{item_id}/ack` | [backend/van_gateway/app.py:2417](/workspace/Van/backend/van_gateway/app.py:2417) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/attention/{item_id}/snooze` | [backend/van_gateway/app.py:2422](/workspace/Van/backend/van_gateway/app.py:2422) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:78](/workspace/Van/android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:78), [android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt:91](/workspace/Van/android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt:91), [android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:75](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:75), [android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:70](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:70), [android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:169](/workspace/Van/android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:169). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. AttentionRoute drops acknowledge/snooze mutation errors at baseline.

Happy acceptance: Successful ack/snooze is read back; urgency updates embodiment and appropriate interruption channels.

Error acceptance: Failed ack/snooze retains the actionable item and displays retryable error.

### OF-DECISION-001 — Owner decisions and Needs You

Information: origin/project; reason; available choices; risk/expected effect; evidence; expiry; current status; waiting missions.

Required actions: inspect evidence; approve/select; reject; defer through supported attention controls; add instruction to bound mission.

Authority: [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:806](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:806), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:629](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:629).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/needs-you` | [backend/van_gateway/mission/api.py:245](/workspace/Van/backend/van_gateway/mission/api.py:245) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/decisions` | [backend/van_gateway/app.py:1983](/workspace/Van/backend/van_gateway/app.py:1983) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/decisions/{decision_id}/resolve` | [backend/van_gateway/app.py:1987](/workspace/Van/backend/van_gateway/app.py:1987) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:33](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:33), [android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:79](/workspace/Van/android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:79), [android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:76](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:76), [android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:197](/workspace/Van/android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:197), [android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:204](/workspace/Van/android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:204). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Decision model only exposes title/body/source/hermes_ref/status/timestamps; project/action class/choices/evidence/expiry contracts are incomplete. Approve/reject failures are dropped in AttentionRoute; boolean decision approval is not cryptographic action authority.

Happy acceptance: The selected decision resolves authoritatively and associated attention is handled.

Error acceptance: Expired/stale/conflicting decision cannot silently approve a new action; refusal preserves context.

### OF-APPROVAL-001 — Per-occurrence elevated action approval

Information: target; action; risk; expected effect; intent digest; approval expiry; biometric availability.

Required actions: inspect intent; approve with bound hardware-key biometric proof; reject/dismiss.

Authority: [docs/SECURITY_POLICY.md:64](/workspace/Van/docs/SECURITY_POLICY.md:64), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:743](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:743), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:534](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:534).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/commands` | [backend/van_gateway/app.py:1702](/workspace/Van/backend/van_gateway/app.py:1702) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/authority` | [backend/van_gateway/mission/api.py:316](/workspace/Van/backend/van_gateway/mission/api.py:316) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

No dedicated current Android surface callsite located for this workflow; runtime/local code or declared client methods can still exist.

Baseline coverage: **partial**. UI must distinguish decision resolution from an exact command-bound, single-use approval; authority endpoint has no Android client method. Payment remains prohibited by default and never gains standing automation authority.

Happy acceptance: Only exact intent-bound approval authorizes the occurrence; no success before independent verification.

Error acceptance: Biometric cancellation, changed intent, replay, expiry and prohibited actions are explicit non-success states.

### OF-REMINDER-001 — Reminder lifecycle

Information: text; due time/timezone; project; owner/Hermes source; open/resolved/cancelled; follow-up chain.

Required actions: create using explicit/natural time; resolve; cancel; inspect upcoming.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:591](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:591), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:55](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:55).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/reminders` | [backend/van_gateway/app.py:1941](/workspace/Van/backend/van_gateway/app.py:1941) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/reminders/parse` | [backend/van_gateway/app.py:1962](/workspace/Van/backend/van_gateway/app.py:1962) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/reminders` | [backend/van_gateway/app.py:1945](/workspace/Van/backend/van_gateway/app.py:1945) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/reminders/{reminder_id}/resolve` | [backend/van_gateway/app.py:1949](/workspace/Van/backend/van_gateway/app.py:1949) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/reminders/{reminder_id}/cancel` | [backend/van_gateway/app.py:1957](/workspace/Van/backend/van_gateway/app.py:1957) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt:94](/workspace/Van/android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt:94). Full declared client/caller references are in the machine registry.

Baseline coverage: **missing**. Gateway client functions exist, but no reminder management destination or current direct UI callsite; Home upcoming is not full lifecycle control.

Happy acceptance: A created reminder is read back with correct due time and original idempotency identity; chained follow-up is visible.

Error acceptance: Ambiguous/invalid time asks for correction; failed resolve/cancel retains the reminder.

### OF-MEMORY-001 — Owner facts CRUD

Information: subject/predicate/value/scope; provenance; owner-confirmed vs inferred; validity; fact identity.

Required actions: state fact; correct via superseding statement; forget one fact.

Authority: [docs/design/VAN_PRODUCT_DESIGN_DNA.md:59](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:59), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:729](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:729).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/context/facts` | [backend/van_gateway/app.py:2020](/workspace/Van/backend/van_gateway/app.py:2020) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `DELETE /v1/context/facts` | [backend/van_gateway/app.py:2135](/workspace/Van/backend/van_gateway/app.py:2135) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:175](/workspace/Van/android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:175), [android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:213](/workspace/Van/android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:213), [android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:229](/workspace/Van/android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:229), [android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:249](/workspace/Van/android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:249). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Free-text remember dispatch reloads after 1.2 seconds without checking the result; mutation delivery and authoritative readback need parity with structured facts.

Happy acceptance: The exact fact and scope are read back with owner provenance; forgetting removes its effective validity.

Error acceptance: Auth/validation/storage failure does not clear draft or announce remembered/forgotten.

### OF-MEMORY-002 — Full memory inspection and erasure

Information: store inventory and counts; actual exported records; provenance and confidence; retention scope; reasoning/evidence/strategic/learned data.

Required actions: inspect export; forget a store; forget all owner-derived memory; inspect retention.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:849](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:849), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:59](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:59).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/context/memory` | [backend/van_gateway/app.py:2047](/workspace/Van/backend/van_gateway/app.py:2047) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/context/export` | [backend/van_gateway/app.py:2081](/workspace/Van/backend/van_gateway/app.py:2081) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `DELETE /v1/context/memory` | [backend/van_gateway/app.py:2055](/workspace/Van/backend/van_gateway/app.py:2055) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:81](/workspace/Van/android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:81), [android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:77](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:77), [android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:71](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:71). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. MemoryRoute uses export but no Android client DELETE /v1/context/memory; per-store/all erasure is backend-only. An exported JSON inventory needs owner-readable domain detail and protection against secrets.

Happy acceptance: Owner can inspect actual stored entries and verify requested erasure counts.

Error acceptance: Unknown store/access failure yields a visible error; zero removed is distinct from request failure.

### OF-MEMORY-003 — History and conflict resolution

Information: prior versions; supersession/expiry; conflicting values; authority/source/time/scope.

Required actions: open fact history; inspect each conflict side; state correction.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:755](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:755), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:772](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:772), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:59](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:59).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/context/history` | [backend/van_gateway/app.py:2104](/workspace/Van/backend/van_gateway/app.py:2104) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/context/conflicts` | [backend/van_gateway/app.py:2121](/workspace/Van/backend/van_gateway/app.py:2121) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/context/facts` | [backend/van_gateway/app.py:2020](/workspace/Van/backend/van_gateway/app.py:2020) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:82](/workspace/Van/android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:82), [android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:175](/workspace/Van/android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:175), [android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:213](/workspace/Van/android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:213), [android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:229](/workspace/Van/android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:229). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Conflict UI exists; full fact history endpoint has no actual current UI caller.

Happy acceptance: A correction shows why the previous belief changed; conflicting owner statements remain distinct until owner resolution.

Error acceptance: Unavailable history is not portrayed as no prior beliefs; parse failures are not no conflicts.

### OF-LEARNING-001 — Owner understanding and corrections

Information: owner assertions; OWNER_CONFIRMED/EVIDENCE_DERIVED/TENTATIVE/REJECTED/REVOKED; vocabulary; calibration; cognitive complement.

Required actions: confirm; correct; reject.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:808](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:808), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:59](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:59).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/understanding` | [backend/van_gateway/understanding/api.py:163](/workspace/Van/backend/van_gateway/understanding/api.py:163) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/understanding/{assertion_id}/confirm` | [backend/van_gateway/understanding/api.py:298](/workspace/Van/backend/van_gateway/understanding/api.py:298) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/understanding/{assertion_id}/correct` | [backend/van_gateway/understanding/api.py:309](/workspace/Van/backend/van_gateway/understanding/api.py:309) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/understanding/{assertion_id}/reject` | [backend/van_gateway/understanding/api.py:326](/workspace/Van/backend/van_gateway/understanding/api.py:326) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:106](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:106), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:118](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:118), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:120](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:120), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:121](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:121). Full declared client/caller references are in the machine registry.

Baseline coverage: **missing**. Client methods are present but no current owner UI callsites; raw context export is not an assertion review workflow.

Happy acceptance: Evidence-derived beliefs are clearly marked and an explicit owner correction changes the assertion/calibration.

Error acceptance: Unknown/revoked/conflicting assertion returns a visible non-success outcome.

### OF-LEARNING-002 — Adaptation review and rollback

Information: effective changes; awaiting-owner changes; evidence; scope/time; reversibility; reason.

Required actions: confirm adaptation; revert adaptation.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:829](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:829).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/understanding` | [backend/van_gateway/understanding/api.py:163](/workspace/Van/backend/van_gateway/understanding/api.py:163) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/understanding/adaptation/{change_id}/confirm` | [backend/van_gateway/understanding/api.py:337](/workspace/Van/backend/van_gateway/understanding/api.py:337) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/understanding/adaptation/{change_id}/revert` | [backend/van_gateway/understanding/api.py:345](/workspace/Van/backend/van_gateway/understanding/api.py:345) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:106](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:106), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:123](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:123), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:122](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:122). Full declared client/caller references are in the machine registry.

Baseline coverage: **missing**. Client methods exist without owner UI callers; current Memory does not surface review/rollback affordances.

Happy acceptance: A supported learned change can be confirmed or read back as reverted, without widening authority.

Error acceptance: ADAPTATION_NOT_REVERSIBLE is explained; rollback is not optimistically reported.

### OF-LEARNING-003 — Goals, decisions and learned strategies

Information: standing goals vs one-off requests; goal tensions; decision reasons/outcomes; strategy verified/failure/inconclusive counts; eval evidence; external observations vs owner beliefs; technology changes.

Required actions: inspect goal conflict; review decision history; inspect evidence/eval.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:808](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:808), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:829](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:829).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/understanding/intents` | [backend/van_gateway/understanding/api.py:179](/workspace/Van/backend/van_gateway/understanding/api.py:179) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/understanding/decisions` | [backend/van_gateway/understanding/api.py:231](/workspace/Van/backend/van_gateway/understanding/api.py:231) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/strategies` | [backend/van_gateway/understanding/api.py:408](/workspace/Van/backend/van_gateway/understanding/api.py:408) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/external-reality` | [backend/van_gateway/understanding/api.py:462](/workspace/Van/backend/van_gateway/understanding/api.py:462) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/technology-radar` | [backend/van_gateway/understanding/api.py:380](/workspace/Van/backend/van_gateway/understanding/api.py:380) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/eval` | [backend/van_gateway/understanding/api.py:498](/workspace/Van/backend/van_gateway/understanding/api.py:498) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:137](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:137), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:138](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:138). Full declared client/caller references are in the machine registry.

Baseline coverage: **missing**. No dedicated Android goal/fingerprint/strategy/external-reality clients or UI; technology/eval client methods are not wired to owner screens. Backend explicitly says pattern inference and contradiction detection are inactive; absence must not imply agreement.

Happy acceptance: Distinguish untested/inconclusive learning from failure and success; show inactive inference limits.

Error acceptance: Unavailable evidence is reported without implying no contradictions or perfect accuracy.

### OF-PROJECT-001 — Project inventory and detail

Information: authoritative project ID/name; phase/mission; health; active work; attention; recent update; truth provenance; decisions/blockers.

Required actions: open project; open bound work/attention; context-bound command.

Authority: [docs/design/VAN_PRODUCT_DESIGN_DNA.md:60](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:60), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:836](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:836), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:740](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:740).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/projects` | [backend/van_gateway/app.py:2659](/workspace/Van/backend/van_gateway/app.py:2659) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/projects/{project_id}/truth` | [backend/van_gateway/app.py:2663](/workspace/Van/backend/van_gateway/app.py:2663) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/missions` | [backend/van_gateway/mission/api.py:188](/workspace/Van/backend/van_gateway/mission/api.py:188) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/attention` | [backend/van_gateway/app.py:2413](/workspace/Van/backend/van_gateway/app.py:2413) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/context/export` | [backend/van_gateway/app.py:2081](/workspace/Van/backend/van_gateway/app.py:2081) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/dev/DevHomeRoute.kt:58](/workspace/Van/android/app/src/main/java/com/dial/van/command/dev/DevHomeRoute.kt:58), [android/app/src/main/java/com/dial/van/command/dev/DevSections.kt:120](/workspace/Van/android/app/src/main/java/com/dial/van/command/dev/DevSections.kt:120), [android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:68](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:68), [android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:72](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:72), [android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:74](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:74). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Projects and detail swallow optional truth/context errors and render defaults; project context must propagate to controller; child detail failures require explicit partial-data state.

Happy acceptance: Project is discovered from registry; every project command carries its ID and each related item opens its record.

Error acceptance: Unknown project and missing truth are distinguished from a healthy empty project.

### OF-PROJECT-002 — Strategic rationale memory

Information: rationale; tried/rejected approaches; evidence refs; separation from repository truth.

Required actions: inspect rationale; record owner rationale.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:849](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:849), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:740](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:740).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/projects/{project_id}/strategic-memory` | [backend/van_gateway/understanding/api.py:259](/workspace/Van/backend/van_gateway/understanding/api.py:259) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/projects/{project_id}/strategic-memory` | [backend/van_gateway/understanding/api.py:272](/workspace/Van/backend/van_gateway/understanding/api.py:272) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

No dedicated current Android surface callsite located for this workflow; runtime/local code or declared client methods can still exist.

Baseline coverage: **missing**. No Android client/UI; Project Truth update is an internal control route and must not be conflated with owner rationale.

Happy acceptance: Project rationale is retrievable separately from current implementation truth.

Error acceptance: Already-rejected approach returns an explicit 409 explanation, not a duplicate successful record.

### OF-AUTHORITY-001 — Permissions and autonomy

Information: standing grants; origin/last use/expiry; domain earned/owner/effective ceilings; suspensions; policy.

Required actions: inspect grant; revoke grant; inspect authority descriptor and readiness.

Authority: [docs/SECURITY_POLICY.md:56](/workspace/Van/docs/SECURITY_POLICY.md:56), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:175](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:175), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:829](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:829).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/permissions` | [backend/van_gateway/understanding/api.py:369](/workspace/Van/backend/van_gateway/understanding/api.py:369) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/permissions/{grant_id}/revoke` | [backend/van_gateway/understanding/api.py:374](/workspace/Van/backend/van_gateway/understanding/api.py:374) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/autonomy` | [backend/van_gateway/understanding/api.py:387](/workspace/Van/backend/van_gateway/understanding/api.py:387) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/authority` | [backend/van_gateway/mission/api.py:316](/workspace/Van/backend/van_gateway/mission/api.py:316) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/capabilities/status` | [backend/van_gateway/mission/api.py:292](/workspace/Van/backend/van_gateway/mission/api.py:292) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:131](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:131), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:132](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:132), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:133](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:133), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:136](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:136). Full declared client/caller references are in the machine registry.

Baseline coverage: **missing**. No current owner UI callers despite available client methods; authority descriptor has no Android client. No autonomy-grant editing route declared here.

Happy acceptance: Revocation reads back; earned history cannot mint standing authority, and false-success suspension is visible.

Error acceptance: Already-revoked or refused grant is explicit; data absence is not permission to act.

### OF-GOOGLE-001 — Google account planes and revocation

Information: Workspace/Gemini/Cloud/consumer planes; identity aliases; scope; readiness evidence; degradation; capability availability.

Required actions: inspect plane; disconnect owner Workspace OAuth; follow supported consent restoration.

Authority: [docs/SECURITY_POLICY.md:72](/workspace/Van/docs/SECURITY_POLICY.md:72), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1090](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1090), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:61](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:61).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/google/status` | [backend/van_gateway/app.py:2290](/workspace/Van/backend/van_gateway/app.py:2290) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/google/planes` | [backend/van_gateway/app.py:2294](/workspace/Van/backend/van_gateway/app.py:2294) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/google/mesh` | [backend/van_gateway/app.py:2355](/workspace/Van/backend/van_gateway/app.py:2355) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/google/capabilities` | [backend/van_gateway/app.py:2359](/workspace/Van/backend/van_gateway/app.py:2359) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/google/owner-revoke` | [backend/van_gateway/app.py:2336](/workspace/Van/backend/van_gateway/app.py:2336) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt:66](/workspace/Van/android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt:66), [android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt:202](/workspace/Van/android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt:202). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Connected shows planes and owner revoke; complete capability/job/consent journey is absent. Connect remains host-controlled; Android must not accept refresh tokens.

Happy acceptance: Each plane has independent status; revoking Workspace does not claim all Google planes disconnected.

Error acceptance: Expired/signed-out/unconfigured planes show scoped restoration with other healthy paths preserved.

### OF-GOOGLE-002 — Workspace owner operations

Information: safe search results; draft/send state; calendar time/details; Drive provenance; contact resolution; tasks; effect verification.

Required actions: search mail/Drive; draft mail; send only with fresh approval; read/insert/reschedule calendar; resolve contact; list tasks; invoke declared typed action.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:861](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:861), [docs/SECURITY_POLICY.md:62](/workspace/Van/docs/SECURITY_POLICY.md:62).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/commands` | [backend/van_gateway/app.py:1702](/workspace/Van/backend/van_gateway/app.py:1702) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/google/gmail/search` | [backend/van_gateway/app.py:2166](/workspace/Van/backend/van_gateway/app.py:2166) | scoped_internal_control |
| `POST /v1/google/gmail/draft` | [backend/van_gateway/app.py:2231](/workspace/Van/backend/van_gateway/app.py:2231) | scoped_internal_control |
| `POST /v1/google/gmail/send` | [backend/van_gateway/app.py:2207](/workspace/Van/backend/van_gateway/app.py:2207) | scoped_internal_control |
| `GET /v1/google/calendar/agenda` | [backend/van_gateway/app.py:2245](/workspace/Van/backend/van_gateway/app.py:2245) | scoped_internal_control |
| `POST /v1/google/calendar/reschedule` | [backend/van_gateway/app.py:2253](/workspace/Van/backend/van_gateway/app.py:2253) | scoped_internal_control |
| `GET /v1/google/drive/search` | [backend/van_gateway/app.py:2266](/workspace/Van/backend/van_gateway/app.py:2266) | scoped_internal_control |
| `GET /v1/google/contacts/resolve` | [backend/van_gateway/app.py:2274](/workspace/Van/backend/van_gateway/app.py:2274) | scoped_internal_control |
| `GET /v1/google/tasks` | [backend/van_gateway/app.py:2282](/workspace/Van/backend/van_gateway/app.py:2282) | scoped_internal_control |
| `POST /v1/google/actions/execute` | [backend/van_gateway/app.py:2193](/workspace/Van/backend/van_gateway/app.py:2193) | scoped_internal_control |

No dedicated current Android surface callsite located for this workflow; runtime/local code or declared client methods can still exist.

Baseline coverage: **partial**. Mostly conversational/internal gateway routes, no dedicated typed results/editor frontend; mark downstream internal access accurately. Registry availability must not imply every provider is ready.

Happy acceptance: Owner sees result and durable mission proof; send-as-owner remains bound to the exact approved content.

Error acceptance: Consent/grant/malformed time/recipient/verification failure yields precise recovery without fake external success.

### OF-KNOWLEDGE-001 — Research and knowledge providers

Information: VEKL/Obsidian/Notebook/research readiness; source/trust/time; evidence; notebook records; research outcomes.

Required actions: ask through command controller; inspect citations; inspect readiness; request declared notebook mutation.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:886](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:886), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1110](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1110), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:61](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:61).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/commands` | [backend/van_gateway/app.py:1702](/workspace/Van/backend/van_gateway/app.py:1702) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/runtime/knowledge/status` | [backend/van_gateway/runtime_api.py:553](/workspace/Van/backend/van_gateway/runtime_api.py:553) | scoped_internal_runtime |
| `POST /v1/runtime/knowledge/vekl/query` | [backend/van_gateway/runtime_api.py:558](/workspace/Van/backend/van_gateway/runtime_api.py:558) | scoped_internal_runtime |
| `POST /v1/runtime/knowledge/obsidian/query` | [backend/van_gateway/runtime_api.py:574](/workspace/Van/backend/van_gateway/runtime_api.py:574) | scoped_internal_runtime |
| `GET /v1/runtime/knowledge/notebook/enterprise/recent` | [backend/van_gateway/runtime_api.py:598](/workspace/Van/backend/van_gateway/runtime_api.py:598) | scoped_internal_runtime |
| `GET /v1/runtime/knowledge/notebook/enterprise/{notebook_id}` | [backend/van_gateway/runtime_api.py:606](/workspace/Van/backend/van_gateway/runtime_api.py:606) | scoped_internal_runtime |
| `POST /v1/runtime/knowledge/notebook/consumer/ask` | [backend/van_gateway/runtime_api.py:623](/workspace/Van/backend/van_gateway/runtime_api.py:623) | scoped_internal_runtime |
| `POST /v1/runtime/knowledge/actions/execute` | [backend/van_gateway/runtime_api.py:639](/workspace/Van/backend/van_gateway/runtime_api.py:639) | scoped_internal_runtime |
| `GET /v1/runtime/research/status` | [backend/van_gateway/runtime_api.py:829](/workspace/Van/backend/van_gateway/runtime_api.py:829) | scoped_internal_runtime |
| `POST /v1/runtime/research/search` | [backend/van_gateway/runtime_api.py:834](/workspace/Van/backend/van_gateway/runtime_api.py:834) | scoped_internal_runtime |

No dedicated current Android surface callsite located for this workflow; runtime/local code or declared client methods can still exist.

Baseline coverage: **partial**. Runtime endpoints are internal, not direct phone API authority; no dedicated owner knowledge/citations destination. Provider unconfigured/unqualified remains external/degraded.

Happy acceptance: Sources are opened from real evidence; unconfigured VEKL is unavailable rather than silently substituted.

Error acceptance: Unknown/unqualified provider and missing citation are reported; no invented source or confidence.

### OF-AUTOMATION-001 — Automation and standing intents

Information: capability/template readiness; workflow mission/run; authority scope; effect receipts; standing intent; repair status.

Required actions: request automation through controller; inspect run/evidence; disable standing intent through supported owner command.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:591](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:591), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1189](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1189), [docs/SECURITY_POLICY.md:24](/workspace/Van/docs/SECURITY_POLICY.md:24).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/commands` | [backend/van_gateway/app.py:1702](/workspace/Van/backend/van_gateway/app.py:1702) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/automation/health` | [backend/van_gateway/automation/health.py:255](/workspace/Van/backend/van_gateway/automation/health.py:255) | scoped_internal_control |
| `GET /v1/automation/templates` | [backend/van_gateway/automation/api.py:763](/workspace/Van/backend/van_gateway/automation/api.py:763) | scoped_internal_control |
| `GET /v1/automation/capabilities/{capability_id}` | [backend/van_gateway/automation/api.py:618](/workspace/Van/backend/van_gateway/automation/api.py:618) | scoped_internal_control |
| `POST /v1/automation/standing-intents` | [backend/van_gateway/automation/api.py:532](/workspace/Van/backend/van_gateway/automation/api.py:532) | scoped_internal_control |
| `POST /v1/automation/standing-intents/{intent_id}/disable` | [backend/van_gateway/automation/api.py:598](/workspace/Van/backend/van_gateway/automation/api.py:598) | scoped_internal_control |
| `GET /v1/automation/temporal/{workflow_id}` | [backend/van_gateway/automation/temporal_bridge.py:170](/workspace/Van/backend/van_gateway/automation/temporal_bridge.py:170) | scoped_internal_control |

No dedicated current Android surface callsite located for this workflow; runtime/local code or declared client methods can still exist.

Baseline coverage: **missing**. No current automation owner destination; compile/admit/execute/repair APIs are privileged worker interfaces, not owner buttons. Work can show child mission records only.

Happy acceptance: Automation is mission-bound, credential/domain scoped and owner can inspect/disable supported standing work.

Error acceptance: Unavailable n8n/Temporal, denied scope and unmet effects remain distinct; no automatic payment or authority expansion.

### OF-BROWSER-001 — Browser task supervision and escalations

Information: task/status; policy/domain limits; escalations; evidence; mission link; profile/control lease.

Required actions: inspect task evidence; resolve escalation decision; open live browser.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1132](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1132), [docs/SECURITY_POLICY.md:46](/workspace/Van/docs/SECURITY_POLICY.md:46).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/browser/status` | [backend/van_gateway/browser/api.py:630](/workspace/Van/backend/van_gateway/browser/api.py:630) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/browser/policy` | [backend/van_gateway/browser/api.py:662](/workspace/Van/backend/van_gateway/browser/api.py:662) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/browser/tasks` | [backend/van_gateway/browser/api.py:707](/workspace/Van/backend/van_gateway/browser/api.py:707) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/browser/tasks/{task_id}` | [backend/van_gateway/browser/api.py:836](/workspace/Van/backend/van_gateway/browser/api.py:836) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/browser/tasks/{task_id}/evidence` | [backend/van_gateway/browser/api.py:691](/workspace/Van/backend/van_gateway/browser/api.py:691) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/browser/escalations` | [backend/van_gateway/browser/api.py:714](/workspace/Van/backend/van_gateway/browser/api.py:714) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/decisions/{decision_id}/resolve` | [backend/van_gateway/app.py:1987](/workspace/Van/backend/van_gateway/app.py:1987) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:65](/workspace/Van/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:65), [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:319](/workspace/Van/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:319), [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:68](/workspace/Van/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:68), [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:386](/workspace/Van/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:386), [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:66](/workspace/Van/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:66). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Legacy modules expose oversight with ad hoc states; task/session links need durable mission context and no raw policy internals.

Happy acceptance: Task evidence and escalation choice are linked to the correct active target and mission.

Error acceptance: Unknown task/missing runtime/domain denial keeps other voice/control planes usable.

### OF-BROWSER-002 — Interactive native browser

Information: omnibox; active tab and tab list; native keyboard; connection/control indicators; lease; viewport revision; audio; session persistence.

Required actions: navigate/search; tabs; back/forward/reload; tap/swipe/fling/pinch/long press; open shortcut; suspend/end session.

Authority: [docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md:529](/workspace/Van/docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md:529), [docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md:809](/workspace/Van/docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md:809).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/browser/interactive-sessions` | [backend/van_gateway/browser/interactive_api.py:199](/workspace/Van/backend/van_gateway/browser/interactive_api.py:199) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/browser/interactive-sessions/{session_id}` | [backend/van_gateway/browser/interactive_api.py:252](/workspace/Van/backend/van_gateway/browser/interactive_api.py:252) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/browser/interactive-sessions/{session_id}/stream-grant` | [backend/van_gateway/browser/interactive_api.py:256](/workspace/Van/backend/van_gateway/browser/interactive_api.py:256) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/browser/interactive-sessions/{session_id}/heartbeat` | [backend/van_gateway/browser/interactive_api.py:377](/workspace/Van/backend/van_gateway/browser/interactive_api.py:377) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/browser/interactive-sessions/{session_id}/viewport` | [backend/van_gateway/browser/interactive_api.py:392](/workspace/Van/backend/van_gateway/browser/interactive_api.py:392) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/browser/interactive-sessions/{session_id}/viewport/ack` | [backend/van_gateway/browser/interactive_api.py:408](/workspace/Van/backend/van_gateway/browser/interactive_api.py:408) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/browser/interactive-sessions/{session_id}/suspend` | [backend/van_gateway/browser/interactive_api.py:419](/workspace/Van/backend/van_gateway/browser/interactive_api.py:419) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `DELETE /v1/browser/interactive-sessions/{session_id}` | [backend/van_gateway/browser/interactive_api.py:431](/workspace/Van/backend/van_gateway/browser/interactive_api.py:431) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/browser/interactive-sessions/{session_id}/tabs` | [backend/van_gateway/browser/interactive_api.py:455](/workspace/Van/backend/van_gateway/browser/interactive_api.py:455) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/browser/interactive-sessions/{session_id}/events` | [backend/van_gateway/browser/interactive_api.py:538](/workspace/Van/backend/van_gateway/browser/interactive_api.py:538) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:385](/workspace/Van/android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:385), [android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:354](/workspace/Van/android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:354), [android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:383](/workspace/Van/android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:383), [android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:473](/workspace/Van/android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:473), [android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:419](/workspace/Van/android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:419). Full declared client/caller references are in the machine registry.

Baseline coverage: **external**. Device/media/runtime qualification cannot be established from source. BrowserActivity has a native shell; live stream not audited here.

Happy acceptance: The actual active remote target is rendered and input applies only under the valid viewport/control lease.

Error acceptance: Media outage, browser crash, lease expiry and control transport failure are separate recoverable states.

### OF-BROWSER-003 — Owner/Hermes takeover and page assistance

Information: lease owner/epoch; delegated goal and step budget; active target; analysis/voice response; takeover status.

Required actions: take control by touch; delegate bounded work; ask about visible page; voice control.

Authority: [docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md:529](/workspace/Van/docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md:529), [docs/SECURITY_POLICY.md:18](/workspace/Van/docs/SECURITY_POLICY.md:18).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/browser/interactive-sessions/{session_id}/take-control` | [backend/van_gateway/browser/interactive_api.py:306](/workspace/Van/backend/van_gateway/browser/interactive_api.py:306) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/browser/interactive-sessions/{session_id}/delegate-control` | [backend/van_gateway/browser/interactive_api.py:346](/workspace/Van/backend/van_gateway/browser/interactive_api.py:346) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/commands` | [backend/van_gateway/app.py:1702](/workspace/Van/backend/van_gateway/app.py:1702) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:472](/workspace/Van/android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:472). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. UI state must distinguish owner vs worker lease and preserve current page/session context in typed/voice commands; physical takeover qualification is external.

Happy acceptance: Owner touch revokes worker control immediately; analysis uses the same visible active target and spoken reply.

Error acceptance: Stale lease/target cannot accept input; Hermes outage can leave manual browsing operational.

### OF-BROWSER-004 — Downloads, uploads and clipboard

Information: download status/progress/failure; file origin/size/type; save/open readiness; upload/clipboard policy.

Required actions: inspect/save/open/delete supported downloads; explicit phone upload; policy-bound clipboard.

Authority: [docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md:809](/workspace/Van/docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md:809).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/browser/interactive-sessions/{session_id}/downloads` | [backend/van_gateway/browser/interactive_api.py:460](/workspace/Van/backend/van_gateway/browser/interactive_api.py:460) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `DELETE /v1/browser/interactive-sessions/{session_id}/downloads/{download_id}` | [backend/van_gateway/browser/interactive_api.py:504](/workspace/Van/backend/van_gateway/browser/interactive_api.py:504) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

No dedicated current Android surface callsite located for this workflow; runtime/local code or declared client methods can still exist.

Baseline coverage: **partial**. Transfers use stream-host bulk contracts in addition to gateway metadata; complete device file/save/cancel/error acceptance remains external.

Happy acceptance: Only owner-selected upload leaves phone; download completion is proven by transfer status and local availability.

Error acceptance: Partial/failed/unavailable files are not shown as saved; cancel and expired grants are explicit.

### OF-VOICE-001 — Wake, recognition, interruption and spoken result

Information: wake/ack/listening; partial/final transcript; routing/queued status; response segments; speaking/heard cursor; ASR/TTS asset readiness; recognition errors.

Required actions: start/end listening; stop speaking; barge in; correct/reissue; continue same mission; repeat cached answer.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1199](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1199), [docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md:4310](/workspace/Van/docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md:4310).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/commands` | [backend/van_gateway/app.py:1702](/workspace/Van/backend/van_gateway/app.py:1702) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/session/open` | [backend/van_gateway/session/api.py:130](/workspace/Van/backend/van_gateway/session/api.py:130) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/session/resume` | [backend/van_gateway/session/api.py:150](/workspace/Van/backend/van_gateway/session/api.py:150) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/session/status` | [backend/van_gateway/session/api.py:228](/workspace/Van/backend/van_gateway/session/api.py:228) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/session/messages` | [backend/van_gateway/session/api.py:245](/workspace/Van/backend/van_gateway/session/api.py:245) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/session/events-stream` | [backend/van_gateway/session/api.py:260](/workspace/Van/backend/van_gateway/session/api.py:260) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `WEBSOCKET /v1/session/ws` | [backend/van_gateway/session/api.py:294](/workspace/Van/backend/van_gateway/session/api.py:294) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

No dedicated current Android surface callsite located for this workflow; runtime/local code or declared client methods can still exist.

Baseline coverage: **partial**. VanVoiceUiStore is written but no UI reads voiceUi; no current endOwnerTurn control; partial transcript/error/voice-cancel presentation missing. Hardware/offline asset readiness requires device evidence.

Happy acceptance: Wake immediately acknowledges locally; verified response is spoken and only TTS_COMPLETED means owner heard the full answer.

Error acceptance: ASR/TTS/network/permission/asset failure is specific; cancelled/barge-in output is distinct from delivered answer.

### OF-VOICE-002 — Speech personalization

Information: personal correction record; speaker profile status; adaptation evidence; local asset readiness.

Required actions: capture correction; inspect/reset personal speech model when supported.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1260](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1260), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:62](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:62).

Local feature; no independent backend endpoint is implied.

No dedicated current Android surface callsite located for this workflow; runtime/local code or declared client methods can still exist.

Baseline coverage: **partial**. Speech settings module exists; adaptation control must not turn speaker identity into action authority. Device voice qualification remains unverified.

Happy acceptance: Explicit correction informs the personal model and preserves original utterance provenance.

Error acceptance: Rejected speaker/invalid correction/unavailable model is visible without bypassing biometric authority.

### OF-OVERLAY-001 — Floating assistant and contextual workboard

Information: durable activity/health/attention/speech; context/chat/voice/approval/task mode; compact/expanded/maximized/minimized/docked state.

Required actions: single tap board toggle; double tap Command Centre; long press quick controls; drag/dock; bottom-X dismiss; minimize/restore; context command/voice.

Authority: [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:601](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:601), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:850](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:850), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:72](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:72).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/commands` | [backend/van_gateway/app.py:1702](/workspace/Van/backend/van_gateway/app.py:1702) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/attention` | [backend/van_gateway/app.py:2413](/workspace/Van/backend/van_gateway/app.py:2413) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/missions` | [backend/van_gateway/mission/api.py:188](/workspace/Van/backend/van_gateway/mission/api.py:188) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/events` | [backend/van_gateway/app.py:2667](/workspace/Van/backend/van_gateway/app.py:2667) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:78](/workspace/Van/android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:78), [android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt:91](/workspace/Van/android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt:91), [android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:75](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:75), [android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:70](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:70), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:34](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:34). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Shared repositories exist but voice-state presentation and old trading links need functional parity. Rive must preserve orthogonal board/activity/health/speech state, not become a static replacement.

Happy acceptance: Workboard and full app show the same mission/context and authoritative state while body/attention/speech continue.

Error acceptance: Permission revoked, obstruction, session outage and dismissed state are truthfully recoverable; long gestures do not trigger accidental command actions.

### OF-NOTIFICATION-001 — Notification capture and privacy policy

Information: observed app inventory; NORMAL/PRIORITY/MUTE; quiet hours; listener permission; redaction/deduplication; attention result.

Required actions: set app policy; configure quiet hours; open Android listener permission; inspect generated attention.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:257](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:257), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:62](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:62).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/context/ingest` | [backend/van_gateway/app.py:2458](/workspace/Van/backend/van_gateway/app.py:2458) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/notifications/ingest` | [backend/van_gateway/app.py:2441](/workspace/Van/backend/van_gateway/app.py:2441) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/attention` | [backend/van_gateway/app.py:2413](/workspace/Van/backend/van_gateway/app.py:2413) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:78](/workspace/Van/android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:78), [android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt:91](/workspace/Van/android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt:91), [android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:75](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:75), [android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:70](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:70). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. At baseline new notifications never populate decidedPackages unless explicit policy exists, contrary to settings copy. Android uses untrusted context ingest, not owner command authority.

Happy acceptance: An observed app is discoverable, policy persists, quiet hours allow only priority sources, redacted events become attention once.

Error acceptance: Denied listener/capture failure is visible; mute/quiet/redacted/suppressed outcomes are distinguished from dispatch success.

### OF-SHARE-001 — Share to VAN

Information: shared payload/provenance/type; capture delivery; target context/mission; owner confirmation boundary.

Required actions: Android share intake; inspect imported context; explicit separate owner instruction.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1293](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1293), [docs/SECURITY_POLICY.md:88](/workspace/Van/docs/SECURITY_POLICY.md:88).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/context/ingest` | [backend/van_gateway/app.py:2458](/workspace/Van/backend/van_gateway/app.py:2458) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

No dedicated current Android surface callsite located for this workflow; runtime/local code or declared client methods can still exist.

Baseline coverage: **partial**. Share activity is connected; review/degraded/offline and target context selection need acceptance evidence. External content must remain DATA even on the owner device.

Happy acceptance: Share creates untrusted context and opens the correct VAN surface without minting command authority.

Error acceptance: Unsupported/oversized/expired/unreadable attachment shows specific failure and never executes embedded instructions.

### OF-PROVISION-001 — Owner device onboarding and identity

Information: permissions; signed provisioning status; paired device; bound hardware identity; overlay/listener/mic/biometric; gateway connectivity; selected Google consent.

Required actions: apply signed provisioning payload; pair/bind; grant Android permissions; run readiness check; re-enroll through supported installer flow.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1305](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1305), [docs/SECURITY_POLICY.md:5](/workspace/Van/docs/SECURITY_POLICY.md:5), [docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md:246](/workspace/Van/docs/VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1_5.md:246).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/devices/pair` | [backend/van_gateway/app.py:1592](/workspace/Van/backend/van_gateway/app.py:1592) | single_use_pairing_ticket |
| `POST /v1/devices/bootstrap/challenge` | [backend/van_gateway/app.py:1775](/workspace/Van/backend/van_gateway/app.py:1775) | signed_installer_bootstrap |
| `POST /v1/devices/bootstrap/attest` | [backend/van_gateway/app.py:1784](/workspace/Van/backend/van_gateway/app.py:1784) | signed_installer_bootstrap |
| `POST /v1/devices/tls-certificate` | [backend/van_gateway/app.py:1667](/workspace/Van/backend/van_gateway/app.py:1667) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/device-binding/status` | [backend/van_gateway/app.py:1819](/workspace/Van/backend/van_gateway/app.py:1819) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/connectivity/manifest` | [backend/van_gateway/app.py:1854](/workspace/Van/backend/van_gateway/app.py:1854) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

No dedicated current Android surface callsite located for this workflow; runtime/local code or declared client methods can still exist.

Baseline coverage: **partial**. Signed installer provisioning replaces manual URL/token entry; do not reintroduce setup secrets in redesign. Full device/consent readiness is external. Device revocation/rebind are internal-control endpoints, not generic phone controls.

Happy acceptance: Paired and hardware-bound owner completes actual permissions/readiness and does not land in a failing dashboard.

Error acceptance: Invalid payload/signature/token, denied permission, absent keystore, expired certificate and wrong device are distinct recovery states.

### OF-SETTINGS-001 — Settings, security and device readiness

Information: voice/notifications/quiet hours; renderer/accessibility/theme; permissions/biometric; overlay/queue/voice/gateway/trading/knowledge/Google/browser signals; restore instruction.

Required actions: change supported local preference; open system permission settings; start/stop supported local services; perform explicit restore action.

Authority: [docs/design/VAN_PRODUCT_DESIGN_DNA.md:62](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:62), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1375](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1375), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1396](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1396).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /health` | [backend/van_gateway/app.py:1479](/workspace/Van/backend/van_gateway/app.py:1479) | outer_ingress_probe |
| `GET /v1/degraded` | [backend/van_gateway/app.py:2655](/workspace/Van/backend/van_gateway/app.py:2655) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/device-binding/status` | [backend/van_gateway/app.py:1819](/workspace/Van/backend/van_gateway/app.py:1819) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt:66](/workspace/Van/android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt:66), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:54](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:54), [android/app/src/main/java/com/dial/van/command/settings/SettingsRoute.kt:81](/workspace/Van/android/app/src/main/java/com/dial/van/command/settings/SettingsRoute.kt:81). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Settings handles local modules but lacks grant/autonomy/memory-retention controls and complete state parity. Access/readiness must not use hardcoded healthy defaults.

Happy acceptance: Every displayed health signal has a real producer and an applicable restore action.

Error acceptance: Expired credentials/revoked permission/degraded dependency are owner-readable and keep independent functions available.

### OF-DIAGNOSTICS-001 — Owner diagnostics and correlation

Information: health/degraded; transport mode/path; queue/breaker; trace/alerts; mission/command/run correlation; verification state.

Required actions: inspect trace/evidence; copy redacted diagnostic receipt; retry supported request.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1426](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1426), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:844](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:844).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /health` | [backend/van_gateway/app.py:1479](/workspace/Van/backend/van_gateway/app.py:1479) | outer_ingress_probe |
| `GET /v1/observability/health` | [backend/van_gateway/app.py:2632](/workspace/Van/backend/van_gateway/app.py:2632) | scoped_internal_control |
| `GET /v1/observability/alerts` | [backend/van_gateway/app.py:2617](/workspace/Van/backend/van_gateway/app.py:2617) | scoped_internal_control |
| `GET /v1/observability/trace/{command_id}` | [backend/van_gateway/app.py:2644](/workspace/Van/backend/van_gateway/app.py:2644) | scoped_internal_control |
| `GET /v1/events` | [backend/van_gateway/app.py:2667](/workspace/Van/backend/van_gateway/app.py:2667) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt:66](/workspace/Van/android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt:66), [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:54](/workspace/Van/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:54), [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:114](/workspace/Van/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:114), [android/app/src/main/java/com/dial/van/command/modules/WorkModules.kt:70](/workspace/Van/android/app/src/main/java/com/dial/van/command/modules/WorkModules.kt:70). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Observability APIs are operator-scoped; phone needs a safe owner projection rather than exposing internal tokens/JSON. ActivityModule currently renders raw payload JSON and 10sp text.

Happy acceptance: A failed owner journey is explainable through safe IDs/evidence without credential disclosure.

Error acceptance: Unavailable trace is not a healthy state and does not suppress the original error.

### OF-TRADING-001 — Trading overview, portfolio and risk

Information: status/assessment; portfolio; positions; risk/heat/margin; market freshness; cognition; significant thesis state; broker/account readiness.

Required actions: open position/account/risk/history detail; refresh.

Authority: [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:58), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:898](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:898), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:974](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:974).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/trading/status` | [backend/van_gateway/app.py:2702](/workspace/Van/backend/van_gateway/app.py:2702) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/trading/assessment` | [backend/van_gateway/app.py:2736](/workspace/Van/backend/van_gateway/app.py:2736) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/trading/portfolio` | [backend/van_gateway/app.py:2713](/workspace/Van/backend/van_gateway/app.py:2713) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/trading/positions` | [backend/van_gateway/app.py:2720](/workspace/Van/backend/van_gateway/app.py:2720) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/trading/risk` | [backend/van_gateway/app.py:2748](/workspace/Van/backend/van_gateway/app.py:2748) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/trading/market-state` | [backend/van_gateway/app.py:2744](/workspace/Van/backend/van_gateway/app.py:2744) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/trading/cognition` | [backend/van_gateway/app.py:2752](/workspace/Van/backend/van_gateway/app.py:2752) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt:230](/workspace/Van/android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt:230), [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:36](/workspace/Van/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:36), [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:19](/workspace/Van/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:19), [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:32](/workspace/Van/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:32), [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:21](/workspace/Van/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:21). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. General trading Loaded.toScreenState has only loading/error/empty/content; full degraded/offline/stale/access parity is incomplete. Semantic cues must reflect thesis/risk, not profit emotion.

Happy acceptance: Read models show authoritative exposure/freshness; each metric opens a concrete detail.

Error acceptance: Stale prices, disabled sender/risk and broker outage are distinct; no stale data used for authority.

### OF-TRADING-002 — Positions, charts, history and opportunity intelligence

Information: position direction/exposure/protection/R; thesis/invalidation/confirmation; bars/chart; events; potential; history; decision/outcome quality.

Required actions: open trade; pan/zoom/crosshair; inspect evidence/history/opportunity.

Authority: [docs/design/VAN_PRODUCT_DESIGN_DNA.md:48](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:48), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:58), [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:974](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:974).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/trading/trades` | [backend/van_gateway/app.py:2706](/workspace/Van/backend/van_gateway/app.py:2706) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/trading/trades/{trade_intent_id}` | [backend/van_gateway/app.py:2757](/workspace/Van/backend/van_gateway/app.py:2757) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/trading/bars` | [backend/van_gateway/app.py:2764](/workspace/Van/backend/van_gateway/app.py:2764) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/trading/events` | [backend/van_gateway/app.py:2724](/workspace/Van/backend/van_gateway/app.py:2724) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/trading/potential` | [backend/van_gateway/app.py:2728](/workspace/Van/backend/van_gateway/app.py:2728) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/trading/history` | [backend/van_gateway/app.py:2732](/workspace/Van/backend/van_gateway/app.py:2732) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/overlay/VanOverlayPanels.kt:78](/workspace/Van/android/app/src/main/java/com/dial/van/overlay/VanOverlayPanels.kt:78), [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:26](/workspace/Van/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:26), [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:24](/workspace/Van/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:24), [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:25](/workspace/Van/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:25), [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:33](/workspace/Van/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:33). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Legacy overlay trade/{id} and trades/{view} paths mismatch new position/history/potential routes at baseline; trading legacy activity ignores initial route extras.

Happy acceptance: Opening a trade reaches the exact detail; chart and outcome data are source-backed.

Error acceptance: Unknown trade/no bars/unverifiable result are explicit and never celebrated from P&L alone.

### OF-TRADING-003 — Trading account setup and controlled actions

Information: broker/platform; connection state; credential reference; capabilities; live/readiness status; pending challenge.

Required actions: request exact account challenge; perform supported signed account action; complete broker OAuth privately.

Authority: [docs/SECURITY_POLICY.md:78](/workspace/Van/docs/SECURITY_POLICY.md:78), [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:58).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/trading/accounts` | [backend/van_gateway/app.py:2740](/workspace/Van/backend/van_gateway/app.py:2740) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/trading/accounts/challenge` | [backend/van_gateway/app.py:2798](/workspace/Van/backend/van_gateway/app.py:2798) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/trading/accounts/action` | [backend/van_gateway/app.py:2827](/workspace/Van/backend/van_gateway/app.py:2827) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/trading/oauth/{broker}/callback` | [backend/van_gateway/app.py:3072](/workspace/Van/backend/van_gateway/app.py:3072) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:23](/workspace/Van/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:23), [android/app/src/main/java/com/dial/van/trading/ui/AccountOnboardingScreen.kt:91](/workspace/Van/android/app/src/main/java/com/dial/van/trading/ui/AccountOnboardingScreen.kt:91), [android/app/src/main/java/com/dial/van/trading/ui/AccountOnboardingScreen.kt:80](/workspace/Van/android/app/src/main/java/com/dial/van/trading/ui/AccountOnboardingScreen.kt:80). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Current account controls need authoritative readback and scoped access/offline handling; broker credential values remain on trading host. Device live qualification external.

Happy acceptance: An exact approved action changes only the intended account and readback confirms effect.

Error acceptance: Challenge expiry/biometric refusal/broker callback failure leaves account status truthful and secrets absent.

### OF-TRADING-004 — Strategy certificate promotion

Information: promotion candidate; certificate/evidence/current hash; target state; authority/approval challenge; capsule-state readback.

Required actions: inspect validation; biometric approve exact certificate; promote; verify authoritative readback.

Authority: [docs/project-state/AUTHORITY_MAP.yaml:608](/workspace/Van/docs/project-state/AUTHORITY_MAP.yaml:608), [docs/SECURITY_POLICY.md:78](/workspace/Van/docs/SECURITY_POLICY.md:78).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/trading/strategies/promotion-candidates` | [backend/van_gateway/app.py:2926](/workspace/Van/backend/van_gateway/app.py:2926) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/trading/strategies/promotion-challenge` | [backend/van_gateway/app.py:2939](/workspace/Van/backend/van_gateway/app.py:2939) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/trading/strategies/promote` | [backend/van_gateway/app.py:2961](/workspace/Van/backend/van_gateway/app.py:2961) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:29](/workspace/Van/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:29), [android/app/src/main/java/com/dial/van/trading/ui/StrategiesScreen.kt:114](/workspace/Van/android/app/src/main/java/com/dial/van/trading/ui/StrategiesScreen.kt:114), [android/app/src/main/java/com/dial/van/trading/ui/StrategiesScreen.kt:158](/workspace/Van/android/app/src/main/java/com/dial/van/trading/ui/StrategiesScreen.kt:158). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Readback verification path exists; owner UI must render unavailable/obsolete certificate rather than accepting transport success. External strategy/certificate/runtime qualification remains separate.

Happy acceptance: Exact device proofs bind strategy,target,certificate; durable current capsule state confirms completion.

Error acceptance: Stale certificate/challenge, authority mismatch, failed readback and biometric cancellation cannot claim promoted.

### OF-TRADING-005 — Trading halt and ticket decisions

Information: halt reason/action semantics; risk authority; ticket exact intent; protection state; receipt.

Required actions: halt through supported signed owner command; inspect/confirm supported ticket with fresh proof.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:914](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:914), [docs/SECURITY_POLICY.md:78](/workspace/Van/docs/SECURITY_POLICY.md:78).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/trading/halt` | [backend/van_gateway/app.py:3126](/workspace/Van/backend/van_gateway/app.py:3126) | scoped_internal_control |
| `GET /v1/trading/tickets` | [backend/van_gateway/app.py:3122](/workspace/Van/backend/van_gateway/app.py:3122) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/trading/tickets/{ticket_id}/confirm` | [backend/van_gateway/app.py:3150](/workspace/Van/backend/van_gateway/app.py:3150) | scoped_internal_control |
| `POST /v1/commands` | [backend/van_gateway/app.py:1702](/workspace/Van/backend/van_gateway/app.py:1702) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

No dedicated current Android surface callsite located for this workflow; runtime/local code or declared client methods can still exist.

Baseline coverage: **partial**. Halt/ticket routes are internally gated protected surfaces; no ordinary Android client methods for these endpoints. Do not invent direct broker order/stop-widening actions.

Happy acceptance: Permitted protective action is scope-bound, independently read back, and respects single sender/risk authority.

Error acceptance: Risk denial/expired ticket/sender unavailable remains explicit; browser/model cannot place orders.

### OF-DEV-001 — Development project hub and task control

Information: project home/stage plan; task lifecycle/graph; agents; evidence; review/memory/research/design/CI/security/infrastructure sections; projection revision.

Required actions: inspect project/task/evidence; submit only actions advertised by upstream contract; owner steer/pause/resume/cancel/retry where allowed.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:151](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:151), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:814](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:814), [docs/SECURITY_POLICY.md:18](/workspace/Van/docs/SECURITY_POLICY.md:18).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/dial-dev/projects` | [backend/van_gateway/dial_dev/api.py:196](/workspace/Van/backend/van_gateway/dial_dev/api.py:196) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/projects/{project_id}/home` | [backend/van_gateway/dial_dev/api.py:200](/workspace/Van/backend/van_gateway/dial_dev/api.py:200) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/projects/{project_id}/stage-plan` | [backend/van_gateway/dial_dev/api.py:207](/workspace/Van/backend/van_gateway/dial_dev/api.py:207) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/projects/{project_id}/tasks` | [backend/van_gateway/dial_dev/api.py:214](/workspace/Van/backend/van_gateway/dial_dev/api.py:214) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/projects/{project_id}/graph` | [backend/van_gateway/dial_dev/api.py:223](/workspace/Van/backend/van_gateway/dial_dev/api.py:223) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/tasks/{task_id}` | [backend/van_gateway/dial_dev/api.py:230](/workspace/Van/backend/van_gateway/dial_dev/api.py:230) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/agents` | [backend/van_gateway/dial_dev/api.py:237](/workspace/Van/backend/van_gateway/dial_dev/api.py:237) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/reviews` | [backend/van_gateway/dial_dev/api.py:288](/workspace/Van/backend/van_gateway/dial_dev/api.py:288) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/memory` | [backend/van_gateway/dial_dev/api.py:288](/workspace/Van/backend/van_gateway/dial_dev/api.py:288) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/research` | [backend/van_gateway/dial_dev/api.py:288](/workspace/Van/backend/van_gateway/dial_dev/api.py:288) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/design` | [backend/van_gateway/dial_dev/api.py:288](/workspace/Van/backend/van_gateway/dial_dev/api.py:288) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/ci` | [backend/van_gateway/dial_dev/api.py:288](/workspace/Van/backend/van_gateway/dial_dev/api.py:288) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/security` | [backend/van_gateway/dial_dev/api.py:288](/workspace/Van/backend/van_gateway/dial_dev/api.py:288) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/infrastructure` | [backend/van_gateway/dial_dev/api.py:298](/workspace/Van/backend/van_gateway/dial_dev/api.py:298) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/evidence/{evidence_ref}` | [backend/van_gateway/dial_dev/api.py:291](/workspace/Van/backend/van_gateway/dial_dev/api.py:291) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/events` | [backend/van_gateway/dial_dev/api.py:304](/workspace/Van/backend/van_gateway/dial_dev/api.py:304) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/dial-dev/actions` | [backend/van_gateway/dial_dev/api.py:340](/workspace/Van/backend/van_gateway/dial_dev/api.py:340) | bound_owner_device_proof |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/dev/DevHomeRoute.kt:58](/workspace/Van/android/app/src/main/java/com/dial/van/command/dev/DevHomeRoute.kt:58), [android/app/src/main/java/com/dial/van/command/dev/DevSections.kt:120](/workspace/Van/android/app/src/main/java/com/dial/van/command/dev/DevSections.kt:120), [android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:68](/workspace/Van/android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:68), [android/app/src/main/java/com/dial/van/command/dev/DevHomeRoute.kt:83](/workspace/Van/android/app/src/main/java/com/dial/van/command/dev/DevHomeRoute.kt:83), [android/app/src/main/java/com/dial/van/command/dev/DevPlanRoute.kt:60](/workspace/Van/android/app/src/main/java/com/dial/van/command/dev/DevPlanRoute.kt:60). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. DIAL projection has dedicated screens and contract-driven actions; access proof/degraded/external upstream availability and correlated post-action readback require full acceptance. Method-name scanner may include unrelated generic names; source callsites require central registry reconciliation.

Happy acceptance: Each control is advertised for the exact upstream record/revision and returns a truthful lifecycle rather than simulated progress.

Error acceptance: Disabled upstream/auth refusal/revision conflict/unsupported action preserves state and does not widen project authority.

### OF-DEV-002 — Workspace evidence and terminal views

Information: workspace state; diff; bounded terminal tail; evidence refs; staleness.

Required actions: open workspace; inspect diff/log/evidence; invoke only supported upstream actions.

Authority: [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:844](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:844), [docs/SECURITY_POLICY.md:18](/workspace/Van/docs/SECURITY_POLICY.md:18).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/dial-dev/workspaces` | [backend/van_gateway/dial_dev/api.py:241](/workspace/Van/backend/van_gateway/dial_dev/api.py:241) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/workspaces/{workspace_id}` | [backend/van_gateway/dial_dev/api.py:245](/workspace/Van/backend/van_gateway/dial_dev/api.py:245) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/workspaces/{workspace_id}/diff` | [backend/van_gateway/dial_dev/api.py:254](/workspace/Van/backend/van_gateway/dial_dev/api.py:254) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/dial-dev/workspaces/{workspace_id}/terminal-tail` | [backend/van_gateway/dial_dev/api.py:263](/workspace/Van/backend/van_gateway/dial_dev/api.py:263) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/dial-dev/actions` | [backend/van_gateway/dial_dev/api.py:340](/workspace/Van/backend/van_gateway/dial_dev/api.py:340) | bound_owner_device_proof |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/dev/DevWorkspacesRoute.kt:65](/workspace/Van/android/app/src/main/java/com/dial/van/command/dev/DevWorkspacesRoute.kt:65), [android/app/src/main/java/com/dial/van/command/dev/DevWorkspacesRoute.kt:120](/workspace/Van/android/app/src/main/java/com/dial/van/command/dev/DevWorkspacesRoute.kt:120), [android/app/src/main/java/com/dial/van/command/dev/DevWorkspacesRoute.kt:198](/workspace/Van/android/app/src/main/java/com/dial/van/command/dev/DevWorkspacesRoute.kt:198), [android/app/src/main/java/com/dial/van/command/dev/DevWorkspacesRoute.kt:249](/workspace/Van/android/app/src/main/java/com/dial/van/command/dev/DevWorkspacesRoute.kt:249), [android/app/src/main/java/com/dial/van/command/dev/DevActions.kt:102](/workspace/Van/android/app/src/main/java/com/dial/van/command/dev/DevActions.kt:102). Full declared client/caller references are in the machine registry.

Baseline coverage: **partial**. Workspace/log projections are read-only; redesign must keep bounded evidence readable and forbid direct shell/SSH UI execution.

Happy acceptance: Workspace/diff/log use the intended record with source revision and stale marker.

Error acceptance: Gone workspace/redacted log/upstream unavailable is explicit; a log tail is not independent verification.

### OF-ARTEMIS-001 — ARTEMIS test console

Information: console admission/session; safe launch URL; connection/access status.

Required actions: request device-proved console session; open governed embedded console.

Authority: [docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1535](/workspace/Van/docs/VAN_FINISHED_PRODUCT_BLUEPRINT_REV_1.md:1535), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:844](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:844).

| Method and exact path | Source | Access plane |
|---|---|---|
| `POST /v1/artemis/console/session` | [backend/van_gateway/app.py:1531](/workspace/Van/backend/van_gateway/app.py:1531) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/artemis/ArtemisConsoleRoute.kt:49](/workspace/Van/android/app/src/main/java/com/dial/van/command/artemis/ArtemisConsoleRoute.kt:49). Full declared client/caller references are in the machine registry.

Baseline coverage: **external**. Session route/native WebView surface exists; full console/live Android test qualification is outside passive source audit.

Happy acceptance: A bound owner opens admitted console without exposing control credentials.

Error acceptance: Missing proof/disabled service/launch expiry is a visible denial, not a connected blank surface.

### OF-EMBODIMENT-001 — Functional Rive state projection

Information: durable activity; orthogonal health/authority; listening/speaking; attention vector/urgency; viseme/mouth; finite action.

Required actions: board gesture parity; reduced-motion mode; renderer diagnostic/acceptance.

Authority: [docs/design/VAN_PRODUCT_DESIGN_DNA.md:72](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:72), [docs/character_forge/VAN_RIVE_INPUT_REFERENCE.md:3](/workspace/Van/docs/character_forge/VAN_RIVE_INPUT_REFERENCE.md:3), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:901](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:901).

| Method and exact path | Source | Access plane |
|---|---|---|
| `GET /v1/events` | [backend/van_gateway/app.py:2667](/workspace/Van/backend/van_gateway/app.py:2667) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `POST /v1/visual/acceptance` | [backend/van_gateway/app.py:3098](/workspace/Van/backend/van_gateway/app.py:3098) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |
| `GET /v1/visual/acceptance` | [backend/van_gateway/app.py:3113](/workspace/Van/backend/van_gateway/app.py:3113) | authenticated_owner_read_or_device_proved_mutation; see ingress policy |

Android callsite evidence: [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:114](/workspace/Van/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:114), [android/app/src/main/java/com/dial/van/command/modules/WorkModules.kt:70](/workspace/Van/android/app/src/main/java/com/dial/van/command/modules/WorkModules.kt:70). Full declared client/caller references are in the machine registry.

Baseline coverage: **external**. Real Rive asset and device certification are external. Exact 9 inputs/8 triggers/18 durable states remain contract-fixed; no extra authoring inputs without contract revision.

Happy acceptance: Verified success alone triggers confirmation; listening/speaking remains visible alongside independent degradation; board opening does not interrupt state.

Error acceptance: Unknown state, missing renderer, offline/degraded/waiting-owner and unverified outcome remain accessible, distinct states.

## Screen registry and navigation requirements

The 55 candidate surfaces below include current destinations/children and missing required workflows. Route syntax is presentation navigation, not a backend path. The leading `/` in DNA notation does not require a leading slash in Kotlin NavHost routes. Keep old Android entry intents as explicit forward mappings rather than parallel experiences.

| Stable screen candidate ID | Route / entry | Domain | Baseline |
|---|---|---|---|
| `van.home` | `home` | overview | partial |
| `van.attention` | `attention` | attention | partial |
| `van.work` | `work` | work | partial |
| `van.work.mission` | `work/missions/{missionId}` | work | partial |
| `van.work.activity` | `work/activity` | work | partial |
| `van.work.artemis` | `work/artemis` | development | external |
| `van.work.browser` | `work/browser` | browser | partial |
| `van.work.browser.tasks` | `work/browser/tasks` | browser | partial |
| `van.work.browser.escalations` | `work/browser/escalations` | browser | partial |
| `van.work.browser.sessions` | `work/browser/sessions` | browser | partial |
| `van.work.browser.policy` | `work/browser/policy` | browser | partial |
| `van.trading` | `trading` | trading | partial |
| `van.trading.overview` | `trading/overview` | trading | partial |
| `van.trading.positions` | `trading/positions` | trading | partial |
| `van.trading.positions.detail` | `trading/positions/{id}` | trading | partial |
| `van.trading.potential` | `trading/potential` | trading | partial |
| `van.trading.history` | `trading/history` | trading | partial |
| `van.trading.accounts` | `trading/accounts` | trading | partial |
| `van.trading.cognition` | `trading/cognition` | trading | partial |
| `van.trading.accounts.add` | `trading/accounts/add` | trading | partial |
| `van.trading.strategies` | `trading/strategies` | trading | partial |
| `van.trading.halt` | `trading#halt` | trading | partial |
| `van.memory` | `memory` | memory | partial |
| `van.projects` | `projects` | projects | partial |
| `van.projects.detail` | `projects/{projectId}` | projects | partial |
| `van.connected` | `connected` | connections | partial |
| `van.settings` | `settings` | settings | partial |
| `van.settings.voice` | `settings/voice` | voice | partial |
| `van.settings.notifications` | `settings/notifications` | notifications | partial |
| `van.work.dev.home` | `work/dev?project={project}` | development | implemented |
| `van.work.dev.plan` | `work/dev/{projectId}/plan` | development | implemented |
| `van.work.dev.tasks` | `work/dev/{projectId}/tasks?view={view}` | development | implemented |
| `van.work.dev.graph` | `work/dev/{projectId}/graph` | development | implemented |
| `van.work.dev.task` | `work/dev/tasks/{taskId}` | development | implemented |
| `van.work.dev.agents` | `work/dev/agents` | development | implemented |
| `van.work.dev.workspaces` | `work/dev/workspaces` | development | implemented |
| `van.work.dev.workspace` | `work/dev/workspaces/{workspaceId}` | development | implemented |
| `van.work.dev.evidence` | `work/dev/evidence/{evidenceRef}` | development | implemented |
| `van.work.dev.reviews` | `work/dev/reviews` | development | implemented |
| `van.work.dev.memory` | `work/dev/memory` | development | implemented |
| `van.work.dev.research` | `work/dev/research` | development | implemented |
| `van.work.dev.design` | `work/dev/design` | development | implemented |
| `van.work.dev.ci` | `work/dev/ci` | development | implemented |
| `van.work.dev.security` | `work/dev/security` | development | implemented |
| `van.floating` | `Native/activity/overlay or required new surface` | overlay | partial |
| `van.voice.turn` | `Native/activity/overlay or required new surface` | voice | partial |
| `van.browser.interactive` | `Native/activity/overlay or required new surface` | browser | partial |
| `van.permissions` | `Native/activity/overlay or required new surface` | permissions | missing |
| `van.autonomy` | `Native/activity/overlay or required new surface` | autonomy | missing |
| `van.understanding` | `Native/activity/overlay or required new surface` | understanding | missing |
| `van.reminders.manage` | `Native/activity/overlay or required new surface` | reminders | missing |
| `van.memory.history` | `Native/activity/overlay or required new surface` | memory | missing |
| `van.onboarding` | `Native/activity/overlay or required new surface` | settings | partial |
| `van.provisioning` | `Native/activity/overlay or required new surface` | settings | partial |
| `van.share.intake` | `Native/activity/overlay or required new surface` | context | partial |

## Functional Rive requirements

Rive is a state projection with existing interaction semantics. Its fixed contract has nine inputs (`state`, `speaking`, `listening`, `attention_x`, `attention_y`, `mouth_open`, `urgency`, `viseme`, `action_code`), eight finite triggers, 18 durable states and 14 finite actions: [docs/character_forge/VAN_RIVE_INPUT_REFERENCE.md:3](/workspace/Van/docs/character_forge/VAN_RIVE_INPUT_REFERENCE.md:3), [visual-authority/rive_contract.json:60](/workspace/Van/visual-authority/rive_contract.json:60). Asset authoring must not invent new public inputs or collapse independent state planes.

Required producers are connecting/offline/health, owner attention and approval, mission/search/delegation/execution/verification, voice listening/speaking, truthful completion/failure/unverifiable and quiet-hours sleep. Verified success alone permits confirmation; profit alone never permits celebration. Reduced motion preserves essential state, speech and attention, and the opened workboard must not halt embodiment state: [docs/design/VAN_PRODUCT_DESIGN_DNA.md:72](/workspace/Van/docs/design/VAN_PRODUCT_DESIGN_DNA.md:72), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:897](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:897), [docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:903](/workspace/Van/docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md:903).

Functional acceptance requires an accessible textual state/action equivalent, interrupted/failed speech distinguished from heard completion, unverified result distinguished from success, gaze/presentation pointing to the real target card, and gesture parity through full/board/minimized/docked modes. Renderer assets and physical device qualification remain explicit external gates.

## Registry recommendations

1. Promote the candidates into one canonical graph: stable feature ID → domain → owner information/actions → screen/entry → exact endpoint IDs → source producer → access/approval policy → owner-work/screen/voice/embodiment state → evidence and acceptance checks. Do not use screen count as functional coverage.
2. Store screen route arguments and Android legacy intent forward mappings explicitly. A concrete mission/project/trade/workspace ID must survive navigation and process recreation.
3. Give every mutation a visible pending/result/error/cancel state and disable duplicate dispatch. Persist idempotency/command/turn identity and read back effect; an acknowledged HTTP request is not effect proof.
4. Mark unsupported controls in capability/readiness projection. Mission pause/resume/retry, goal abandonment, autonomy grant editing and arbitrary broker/credential/account operations cannot be inferred from plausible UI labels.
5. Build owner workflows for the backend-only memory/learning/security/reminder contracts. Keep project rationale separate from Project Truth, owner beliefs separate from external observations, and tentative learning separate from owner authority.
6. Define real data-age/offline/degraded/access producers once in application-scoped repositories shared by floating/full app/voice/notifications. Include scoped restoration and current external gate evidence.
7. Require happy plus error/degraded/offline/access/empty/cancelled/stale acceptance at the actual boundary and representative device flows. A source-string contract or preview fixture alone cannot certify a function, an external mutation or heard voice answer.

## Authorized corrections after the baseline

These fixes do not rewrite baseline coverage. Root is integrating all agents’ corrected findings and final test evidence.

- `android-notification-discovery`: implemented. Listener records observed packages before mute/quiet filtering. Observations are persisted independently from explicit policies; the shared catalogue preserves MUTE/PRIORITY and exposes new NORMAL sources. Settings observes its StateFlow so newly arriving sources appear while open. `AppNotificationPolicy` lives in the pure production catalogue model for shared JVM/device use. Two focused behavioral tests cover discovery and preservation of owner choices.
- `android-mission-deeplink-unbound`: implemented. NavHost forwards the requested mission ID; Work selects running/waiting/terminal missions, places the selected expanded panel immediately below the header, validates fallback record identity and displays timeline empty/error/retry states. Five pure MissionSelection behavioral tests cover the selector.
- `android-attention-mutation-errors`: implemented. Acknowledge/snooze/decision resolve display saving/success/error feedback, guard duplicate item actions until refresh finishes and show post-mutation refresh failure with retry.

Validation completed for this partition: JSON parsing and declared endpoint citation checks; immutable-baseline generation; `git diff --check`; existing owner-surface reachability contract suite **9 passed**. Shared pure JVM behavioral tests passed: NotificationAppCatalogueTest **2/2** and MissionSelectionTest **5/5** (log: `/workspace/van-audit/android-manager-repro/tests.log`). These tests verify production decision logic; Compose/app/device validation remains separate and final whole-repository aggregation belongs to root. No live service or physical device call was made.


## Integrated registry review corrections

The final integrated registries retain 42 features, 65 surfaces and 277 endpoint IDs. These are repository contract declarations and baseline coverage, with live acceptance still unverified. Proposed surfaces retain null current routes.

- ARTEMIS session minting requires ingress plus paired-device authority and bound-device proof. Its one-use launch token and browser-cookie resource boundary are represented separately using the actual middleware resource predicate (`backend/van_gateway/artemis/console.py:142`, `backend/van_gateway/app.py:1535`). Session WebSocket admission requires a paired-device token and an owned session ID, plus bound-device handshake proof or the equivalent verified mTLS identity (`backend/van_gateway/session/api.py:300`); the session ID is not a second credential.
- Trading entries use their actual inner graph route constants and explicit trading host metadata (`android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:69`). Halt is a modal, with no invented navigation route (`:203`).
- Existing Memory conflict resolution and Work A4 approval restore reciprocal feature links (`android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:169`, `android/app/src/main/java/com/dial/van/command/work/WorkRoute.kt:192`, baseline).
- Provisioning intake is explicitly a headless Activity; acceptance distinguishes installer intake/log receipts from enrollment completion and owner readiness. It has no owner status or skeleton screen (`android/app/src/main/java/com/dial/van/provisioning/ProvisioningActivity.kt:35`, `android/app/src/main/AndroidManifest.xml:66`).
- Mission intervention explicitly records missing cancel/message owner controls, with the real backend endpoint refs retained. The selected-mission correction does not supply those controls.

Android endpoint references were independently reconciled from 119 method/path mappings. Six parser/model false positives were removed, two trading-event references were remapped, four declarations were corrected and eight missed direct invocations were added. Helpers, URL builders, WebSocket open/frame calls and descriptor-only paths are typed separately. 145 invocation expressions and 116 function declarations match the pinned baseline source, with zero mismatches. Nested endpoint references and feature/screen aggregates use the same validated mapping. The HTTP session message and SSE contracts do not have a baseline Android HTTP/SSE transport caller; the SSE fallback path descriptor is not counted as a connection. Detailed provenance is in `validated-android-endpoint-callsites.json` and `validated-android-endpoint-callsites-report.json` alongside this audit.

Validation: the endpoint registry, feature/screen registry and owner reachability contract tests pass 16 tests. The self-contained explorer was regenerated with 42 features, 65 surfaces and 277 endpoints. No live readiness claim or device acceptance is inferred from this validation.

## Current owner workflow implementation after the audit

This section supersedes the absence/gap statements above for the original pinned commit. The baseline source audit remains under `baseline_provenance` and `baseline_acceptance_states` in the integrated registries. Current scope is 42 owner capabilities, 68 explicit navigation/modal/inline/headless surfaces, and 285 gateway endpoint contracts with 149 exported schemas. Current capability coverage is 32 partial, 8 source implemented and 2 external; surface coverage is 43 partial, 23 source implemented, 1 external and 1 missing. Coverage describes local source wiring, not acceptance on a physical handset or live service.

The latest actual Android build passed compilation, 203 default app unit tests in 36 suites, default arm64 debug app packaging and lint with unchanged source hashes (`/workspace/van-audit/final-control-restoration-build-receipt.json`). Earlier x86 debug app and instrumentation APK compilation/packaging also passed (`/workspace/van-audit/android-x86-instrumentation-build-receipt.json`); the final control/restoration changes were revalidated in the default arm64 build. No emulator/instrumentation execution or production signing is claimed. The final production-helper JVM suite passed 1,068 tests in 122 suites, zero failures/errors/skips (`/workspace/van-audit/implementation-kotlin-final-summary.json`). Navigation, owner reachability, registry and endpoint contracts pass 30 focused checks. All 3,402 current WORKSPACE_PATCH citation hashes were checked against the final tree; frozen baseline references are retained separately.

Mission cancellation acknowledges a gateway record transition to CANCELLED and prevention of new starts. Already-running remote services may continue; no remote halt is verified. Mission messages acknowledge a matching recorded event, with execution/adoption unverified. Selected terminal missions remain available. Saved route state uses real backstack IDs, rejects unresolved or ambiguous templates, and preserves encoded identifiers. Three production-resolver recreation cases and 23 existing navigation cases pass; physical process recreation is unverified.

A discarded voice turn invalidates recognition callbacks and queued local evidence completion before command submission; Finish preserves the turn while recognition drains. Three lifecycle helper cases cover late final admission, replacement and cancellation; these do not certify handset microphone/acoustic behavior.

Memory privacy exposes the actual allowlisted inventory and retained categories. Destructive erasure submits exact canonical `memory.erase` commands through the existing per-occurrence A4 device-biometric challenge. Direct DELETE memory is a legacy refused route with no UI caller. Store counts render only from a VERIFIED_SUCCESS local effect receipt after authoritative terminal command success. Per-fact withdrawal is a separate historical tombstone operation, with the signed encoded query binding the target.

Automatic setup is read-only owner readiness and supported installer recovery. ProvisioningActivity remains a headless signed installer intake. Provisioning status uses privileged installer authority; no owner screen accepts connection URLs, tokens, endpoint pins or ICE configuration.

Browser takeover, pause, remote close and viewport acknowledgment preserve the latest confirmed snapshot on refusal or unknown outcome, hold input until confirmed state, propagate cancellation, and do not perform blind mutation retry. Matching session/lease/generation or viewport receipts are required. Seven actual used-helper cases pass. Local media disconnection does not confirm remote closure, and lifecycle cancellation may leave a remote lease until expiry. These are implemented local guards; physical stream/control/remote closure acceptance remains unverified. The four original ignored-mutation findings remain in the baseline ledger and now appear under `repaired_mutations` rather than current unhandled mutations.

The following 55 unique owner functions map to current exact source and central endpoint IDs. The complete registry retains all function/source citations, source SHA-256, authority gates, reciprocal surface links and required states.

| Owner function | Current implementation citation | Exact endpoint IDs |
|---|---|---|
| OF-COMMAND-001:submit — Submit owner text or final admitted speech through the existing controller | `android/app/src/main/java/com/dial/van/command/work/WorkRoute.kt:191` | VE-46283550c868 |
| OF-COMMAND-001:status — Read accepted command through terminal owner status | `android/app/src/main/java/com/dial/van/control/VanCommandController.kt:437` | VE-e1308a8edf69 |
| OF-MISSION-001:selected-record — Open the exact selected mission, including terminal state | `android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:269` | VE-2f81bbca1537, VE-d3e2c34b7805 |
| OF-MISSION-001:restore-context — Restore the exact selected mission/project/development context | `android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:178` | Local UI/lifecycle |
| OF-MISSION-002:cancel — Cancel this active mission | `android/app/src/main/java/com/dial/van/command/work/MissionControls.kt:31` | VE-a9de18603483 |
| OF-MISSION-002:message — Record direction on this existing mission | `android/app/src/main/java/com/dial/van/command/work/MissionControls.kt:68` | VE-1d2505634f4b |
| OF-ATTENTION-001:read — Read current attention | `android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:85` | VE-276a5ba5fcd5 |
| OF-ATTENTION-001:ack — Acknowledge an attention item | `android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:223` | VE-cf82eafbdeb9 |
| OF-ATTENTION-001:snooze — Snooze an attention item for one hour | `android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:233` | VE-90761687deb9 |
| OF-APPROVAL-001:approve — Approve the displayed command occurrence with device biometrics | `android/app/src/main/java/com/dial/van/command/work/WorkRoute.kt:225` | VE-46283550c868 |
| OF-REMINDER-001:read — Read open reminders | `android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt:40` | VE-85624e3859a7 |
| OF-REMINDER-001:create — Create a reminder with explicit due time | `android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt:50` | VE-d7f6562ce04b |
| OF-REMINDER-001:resolve — Resolve a reminder | `android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt:66` | VE-b6932785a6e1 |
| OF-REMINDER-001:cancel — Cancel a reminder | `android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt:79` | VE-9765b88983e2 |
| OF-MEMORY-001:state — Remember or correct a scoped owner fact | `android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:222` | VE-4618336736dd |
| OF-MEMORY-001:withdraw — Withdraw a fact while retaining its history | `android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:290` | VE-caa1a831cd8f |
| OF-MEMORY-002:inventory — Inspect held stores and retention | `android/app/src/main/java/com/dial/van/memory/MemoryManagement.kt:64` | VE-d499de7845c7, VE-bf3a9fa9f698 |
| OF-MEMORY-002:erase — Request erasure of a listed store or all owner-derived memory | `android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:301` | VE-46283550c868, VE-e1308a8edf69 |
| OF-MEMORY-003:history — Inspect a fact revision history | `android/app/src/main/java/com/dial/van/memory/MemoryManagement.kt:34` | VE-bdc7ae21680f |
| OF-MEMORY-003:conflict — Inspect conflict sides and state an owner correction | `android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:97` | VE-4f28e519027f, VE-4618336736dd |
| OF-LEARNING-001:read — Inspect assertions, evidence, vocabulary and communication calibration | `android/app/src/main/java/com/dial/van/memory/UnderstandingRoutes.kt:36` | VE-642271170af5 |
| OF-LEARNING-001:confirm — Confirm an assertion | `android/app/src/main/java/com/dial/van/memory/UnderstandingRoutes.kt:69` | VE-45c051d1e101 |
| OF-LEARNING-001:correct — Correct and supersede an assertion | `android/app/src/main/java/com/dial/van/memory/UnderstandingRoutes.kt:114` | VE-31e09178fe07 |
| OF-LEARNING-001:reject — Reject an assertion | `android/app/src/main/java/com/dial/van/memory/UnderstandingRoutes.kt:73` | VE-4faa1c1d1666 |
| OF-LEARNING-002:read — Read active and awaiting adaptations | `android/app/src/main/java/com/dial/van/memory/UnderstandingRoutes.kt:123` | VE-642271170af5 |
| OF-LEARNING-002:confirm — Confirm and read back an adaptation | `android/app/src/main/java/com/dial/van/memory/UnderstandingRoutes.kt:146` | VE-287dc9cf6049, VE-642271170af5 |
| OF-LEARNING-002:revert — Revert a reversible adaptation | `android/app/src/main/java/com/dial/van/memory/UnderstandingRoutes.kt:163` | VE-cfbff17fa74f |
| OF-LEARNING-003:goals — Inspect standing goals, constraints and tensions | `android/app/src/main/java/com/dial/van/memory/GoalsRoute.kt:30` | VE-b2f7e4096027 |
| OF-LEARNING-003:decisions — Read decision history and stated reasons | `android/app/src/main/java/com/dial/van/memory/GoalsRoute.kt:50` | VE-2b4cd04b3bcd |
| OF-LEARNING-003:strategies — Inspect bounded learned strategies | `android/app/src/main/java/com/dial/van/memory/GoalsRoute.kt:69` | VE-308e2e035031 |
| OF-LEARNING-003:reality — Read external observations without inferred agreement | `android/app/src/main/java/com/dial/van/memory/GoalsRoute.kt:88` | VE-13271f00b371 |
| OF-LEARNING-003:radar — Inspect technology evaluation state | `android/app/src/main/java/com/dial/van/memory/GoalsRoute.kt:105` | VE-2f4e0abc0135 |
| OF-LEARNING-003:eval — Inspect measured and unmeasured evaluation dimensions | `android/app/src/main/java/com/dial/van/memory/GoalsRoute.kt:115` | VE-68d130529919 |
| OF-PROJECT-002:read — Inspect project rationale, past rejected strategies and provenance | `android/app/src/main/java/com/dial/van/projects/ProjectRationaleRoute.kt:40` | VE-d00bb1a30df9 |
| OF-PROJECT-002:record — Record owner-authored rationale and verify same-project readback | `android/app/src/main/java/com/dial/van/projects/ProjectRationaleRoute.kt:68` | VE-b3ccb11304be, VE-d00bb1a30df9 |
| OF-AUTHORITY-001:read — Inspect standing permissions | `android/app/src/main/java/com/dial/van/command/settings/PermissionsRoute.kt:36` | VE-4338fb24f4fb |
| OF-AUTHORITY-001:revoke — Withdraw this standing permission | `android/app/src/main/java/com/dial/van/command/settings/PermissionsRoute.kt:59` | VE-3f1397b662d0 |
| OF-AUTHORITY-001:autonomy — Inspect earned, owner and effective autonomy ceilings | `android/app/src/main/java/com/dial/van/command/settings/PermissionsRoute.kt:65` | VE-a85c6a8e08b8 |
| OF-AUTHORITY-001:authority — Inspect action gates | `android/app/src/main/java/com/dial/van/command/settings/PermissionsRoute.kt:88` | VE-6e59a3e94d72 |
| OF-AUTHORITY-001:readiness — Inspect automatic capability readiness | `android/app/src/main/java/com/dial/van/command/settings/PermissionsRoute.kt:95` | VE-d06858d76a7f |
| OF-KNOWLEDGE-001:projection-ownerResearch — Inspect owner-safe research records | `android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt:134` | VE-ecda6dab7297 |
| OF-KNOWLEDGE-001:signed-ownerResearch — Submit only an advertised exact owner command | `android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt:129` | VE-46283550c868 |
| OF-KNOWLEDGE-001:knowledge — Inspect provider evidence, query citations and operations | `android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt:107` | VE-0999839eb5c7 |
| OF-AUTOMATION-001:projection-ownerAutomation — Inspect owner-safe automation records | `android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt:161` | VE-58e368c05889 |
| OF-AUTOMATION-001:signed-ownerAutomation — Submit only an advertised exact owner command | `android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt:156` | VE-46283550c868 |
| OF-BROWSER-001:outcome — Inspect a browser task outcome without claiming task-goal verification | `android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt:251` | VE-05852eec2759 |
| OF-BROWSER-002:viewport — Confirm the current browser viewport | `android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:293` | VE-cb3789db8365 |
| OF-BROWSER-002:pause — Pause this browser session | `android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:504` | VE-5ece98530f31 |
| OF-BROWSER-002:close — Request remote browser closure and distinguish local disconnect | `android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:520` | VE-8f74886a5b7d |
| OF-BROWSER-003:take-control — Take control only after matching fresh owner lease and generation | `android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:487` | VE-e4f5da24b45a, VE-62b65ed91651 |
| OF-VOICE-001:cancel-turn — Cancel unsubmitted speech and reject late recognition results | `android/app/src/main/java/com/dial/van/voice/VoiceInterfaces.kt:687` | Local UI/lifecycle |
| OF-VOICE-001:fallback-carrier — Keep the same owner envelope and acknowledgment boundary on authenticated POST/SSE fallback | `android/app/src/main/java/com/dial/van/session/VanHermesSessionManager.kt:502` | VE-429cca7d769b, VE-0affa45d8c7e |
| OF-NOTIFICATION-001:observed-apps — Review and change explicit policy for apps actually observed | `android/app/src/main/java/com/dial/van/notification/VanNotificationListenerService.kt:26` | Local UI/lifecycle |
| OF-DIAGNOSTICS-001:projection-ownerDiagnostics — Inspect owner-safe settings records | `android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt:216` | VE-eac6e1960005 |
| OF-TRADING-002:legacy-links — Resolve supported legacy trade/view links to actual trading routes | `android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:54` | Local UI/lifecycle |

Current surfaces retain required happy, loading, error, degraded, offline, stale, access, empty and cancelled state contracts. New read sections recover independently, retain cached data with a last-read timestamp, and block mutation retry after an uncertain result until a fresh read. Final-content skeletons and functional Rive bindings remain required; source controls do not certify final Rive rendering. Existing primary pages/overlay still have partial state coverage, and floating attention/A4 interactions remain incomplete.

Remaining acceptance gaps include normalized action/authority detail and a dedicated approval-discard workflow; explicit browser delegation, tab/event inventory and download controls; browser outcome worker-proposal explanation, evidence digest/trust summaries and missing-postcondition presentation; external browser streaming/file bulk UX; Android permission/attestation/biometric/wake/audio acceptance; deployment/provider credentials and egress; real broker, Google and automation receipts; and direct physical owner verification. The browser downloads surface remains a proposal with a null current route. Browser task execution completion remains UNVERIFIED for its task goal; only separately authoritative mission records may support a mission success claim. Rationale records supplied references as owner-authored context, without treating them as repository Project Truth or independently verified evidence.
