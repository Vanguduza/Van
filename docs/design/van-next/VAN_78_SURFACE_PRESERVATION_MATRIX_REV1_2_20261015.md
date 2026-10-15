# VAN 78-Surface Preservation & Rebuild Register — Rev 1.2, 2026-10-15

**Source:** `VAN_FRONTEND_SCREEN_REGISTRY_2026-10-09.md`, snapshot 9 October 2026. **Not a live qualification receipt.**
**Source lineage:** 9 October audit tracks draft owner-core PR #93 (`dfc1557a...`), while current merged main is `8eb18898...`.
**Interpretation:** Current snapshot coverage labels indicate documented/source wiring, not device acceptance. The owner-approved dark/light screenshots and conversation control the new appearance.

## Rev 1.1–1.2 changes

- Route fields that held the prose placeholders "none" / "Not declared" are now empty (CSV) or `null` (JSON), so checkers cannot read them as routes. The 23 non-routed surfaces are unchanged in substance.
- New per-surface fields `source_dependency` and `pr93_only_files`. **35 of 78 surfaces** cite **53 source files** that exist on unmerged PR #93 (`dfc1557`) but not on `main` (`8eb1889`). Those surfaces cannot be migrated from `main` alone; repository consolidation (blueprint Rev 1.2 §12.5, DU-00) comes first.
- Additive VAN Next surfaces are listed separately below (Rev 1.2 adds the add-to-position and handover sheets, the economic calendar with event history, similar-past-events and news coverage); the 78-row obligation inventory is unchanged.
- Trading vocabulary follows the system (blueprint Rev 1.2 §2.6): "Potential trades", "Confidence" (uncalibrated, display only), "Equity", "Portfolio heat".

## Completeness

- Surface records: **78**, unique IDs: **78**.
- Historical owner-action entries: **349** (entries may repeat).
- Parsed endpoint link rows: **324** (references repeat across surfaces).
- Parsed source-reference rows: **428**.

## One-row-per-surface migration inventory

| # | Legacy surface | Presentation | Proposed VAN Next zone | Disposition | Source dependency |
|---:|---|---|---|---|---|
| 1 | `van.home` | `navigation_screen` | Home / Orb | Rebuild screen UI; retain or migrate verified capability and navigation intents; ADD state-aware orb and compact sheet | MAIN |
| 2 | `van.attention` | `navigation_screen` | Attention | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 3 | `van.work` | `navigation_screen` | Work / Missions | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 4 | `van.work.mission` | `navigation_screen` | Work / Missions | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 5 | `van.work.activity` | `navigation_screen` | Work / Missions | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 6 | `van.work.artemis` | `navigation_screen` | Work / Missions | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 7 | `van.work.dev.home` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 8 | `van.work.dev.plan` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 9 | `van.work.dev.tasks` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 10 | `van.work.dev.graph` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents; ADD genuine interactive canvas | MAIN |
| 11 | `van.work.dev.task` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 12 | `van.work.dev.agents` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 13 | `van.work.dev.workspaces` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 14 | `van.work.dev.workspace` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 15 | `van.work.dev.evidence` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 16 | `van.work.dev.reviews` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 17 | `van.work.dev.memory` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 18 | `van.work.dev.research` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 19 | `van.work.dev.design` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 20 | `van.work.dev.ci` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 21 | `van.work.dev.security` | `navigation_screen` | Work / Development / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 22 | `van.work.browser` | `navigation_screen` | Work / Missions | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 23 | `van.work.browser.tasks` | `navigation_screen` | Work / Browser | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 24 | `van.work.browser.escalations` | `navigation_screen` | Work / Browser | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 25 | `van.work.browser.sessions` | `navigation_screen` | Work / Browser | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 26 | `van.work.browser.policy` | `navigation_screen` | Work / Browser | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 27 | `van.browser.interactive` | `native_activity` | Work / Browser | Preserve protected native activity contract; redesign chrome only | MAIN_AND_PR93 |
| 28 | `van.browser.downloads` | `modal` | Work / Browser | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 29 | `van.browser.outcome` | `navigation_screen` | Work / Browser | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 30 | `van.browser.action-plan` | `modal` | Work / Browser | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 31 | `van.browser.file-provider` | `modal` | Work / Browser | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 32 | `van.trading` | `navigation_screen` | Trading / Terminal / Intelligence | Rebuild screen UI; retain or migrate verified capability and navigation intents; ADD Markets/Chart/Intelligence/News | MAIN |
| 33 | `van.trading.overview` | `nested_navigation_screen` | Trading / Terminal / Intelligence | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 34 | `van.trading.positions` | `nested_navigation_screen` | Trading / Terminal / Intelligence | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 35 | `van.trading.positions.detail` | `nested_navigation_screen` | Trading / Terminal / Intelligence | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 36 | `van.trading.potential` | `nested_navigation_screen` | Trading / Terminal / Intelligence | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 37 | `van.trading.history` | `nested_navigation_screen` | Trading / Terminal / Intelligence | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 38 | `van.trading.accounts` | `nested_navigation_screen` | Trading / Terminal / Intelligence | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 39 | `van.trading.cognition` | `nested_navigation_screen` | Trading / Terminal / Intelligence | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 40 | `van.trading.accounts.add` | `nested_navigation_screen` | Trading / Terminal / Intelligence | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 41 | `van.trading.strategies` | `nested_navigation_screen` | Trading / Terminal / Intelligence | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 42 | `van.trading.halt` | `modal` | Trading / Terminal / Intelligence | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN |
| 43 | `van.trading.tickets` | `nested_navigation_screen` | Trading / Terminal / Intelligence | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 44 | `van.approval.trading-ticket` | `modal` | Approval / Context | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 45 | `van.memory` | `navigation_screen` | Memory | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 46 | `van.memory.history` | `modal` | Memory | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 47 | `van.learning.adaptations` | `navigation_screen` | Memory / Learning | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 48 | `van.learning.goals` | `navigation_screen` | Memory / Learning | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 49 | `van.memory.privacy` | `modal` | Memory | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 50 | `van.attention.decision` | `inline_section` | Attention / Decisions | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 51 | `van.work.mission-control` | `inline_section` | Work / Missions | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 52 | `van.memory.record` | `modal` | Memory | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 53 | `van.permissions.grant` | `inline_section` | Permissions | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 54 | `van.automation.plan` | `inline_section` | Automation | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 55 | `van.settings.speaker-profile` | `inline_section` | Settings / Devices | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 56 | `van.projects` | `navigation_screen` | Projects / Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 57 | `van.projects.detail` | `navigation_screen` | Projects / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 58 | `van.projects.rationale` | `navigation_screen` | Projects / Spatial Flow | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 59 | `van.connected` | `navigation_screen` | Connected | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 60 | `van.settings` | `navigation_screen` | Settings / Devices | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN |
| 61 | `van.diagnostics` | `navigation_screen` | Settings / Diagnostics | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 62 | `van.onboarding` | `native_activity` | Onboarding | Preserve protected native activity contract; redesign chrome only | MAIN |
| 63 | `van.provisioning` | `headless_intake_activity` | Provisioning Intake | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN |
| 64 | `van.settings.voice` | `navigation_screen` | Settings / Devices | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 65 | `van.voice.turn` | `inline_section` | Voice / VAN | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 66 | `van.settings.notifications` | `navigation_screen` | Settings / Devices | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 67 | `van.floating` | `overlay_service` | Floating VAN | Preserve resident lifecycle and gestures; rebuild spatial embodiment and workboard | MAIN |
| 68 | `van.permissions` | `navigation_screen` | Permissions | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 69 | `van.autonomy` | `inline_section` | Permissions / Autonomy | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 70 | `van.understanding` | `navigation_screen` | Memory / Adaptation | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 71 | `van.reminders.manage` | `navigation_screen` | Attention / Reminders | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 72 | `van.approval.detail` | `inline_section` | Approval / Context | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN |
| 73 | `van.knowledge.research` | `navigation_screen` | Research / Knowledge | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 74 | `van.knowledge.sources` | `navigation_screen` | Research / Knowledge | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 75 | `van.automation.library` | `navigation_screen` | Automation | Rebuild screen UI; retain or migrate verified capability and navigation intents | MAIN_AND_PR93 |
| 76 | `van.automation.intent` | `inline_section` | Automation | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN_AND_PR93 |
| 77 | `van.devices.provision` | `inline_section` | Settings / Provisioning | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN |
| 78 | `van.share.intake` | `transient_intake_activity` | Share Intake | Preserve contextual/host contract; rebuild presentation, do not invent a tab | MAIN |

## Atomic surface clauses

Every entry below carries its original interaction type and owner actions; the new design is not entitled to omit a supported behaviour merely because the old widget looks obsolete.


### 01. `van.home` — Home

- **Registry source lines:** 102–213; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Understand what needs attention and what VAN is doing..
- **Host/route:** `home` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Home / Orb; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents; ADD state-aware orb and compact sheet.
- **Information obligation:** embodiment/state; top three attention items/briefing; active/waiting missions; trade assessment; reminders due today; recent events.
- **Owner action obligations:** open Attention; open Work; open Trading; retry.
- **Endpoint evidence:** GET /v1/needs-you; GET /v1/missions; GET /health; GET /v1/attention; GET /v1/briefing; GET /v1/reminders; GET /v1/trading/assessment.
- **Historical gap categories:** `["UI_REDESIGN", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt:80](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/home/HomeRoute.kt#L80); [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:32](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt#L32); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:55](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L55); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 02. `van.attention` — Attention

- **Registry source lines:** 214–350; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/attention/OwnerDecisionCard.kt`.
- **Owner goal:** Triage alerts, approve or refuse decisions..
- **Host/route:** `attention` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Attention; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** severity list; source; decision body; pending A4 action ID; quiet-hours banner; listed stable choices and proposed labels; exact owner note/revision/expiry; REFERENCE_ONLY versus RECORDED_EVENT evidence; immutable answer/recovery identity; grants_action_authority=false.
- **Owner action obligations:** filter severity; ack; snooze one hour; open DIAL task; approve/refuse decision; biometric A4 approve; Read current attention; Acknowledge an attention item; Snooze an attention item for one hour; Read and answer an exact owner choice with evidence, expiry, note and immutable recovery identity.
- **Endpoint evidence:** GET /v1/attention; GET /v1/decisions; POST /v1/attention/{item_id}/ack; POST /v1/attention/{item_id}/snooze; POST /v1/decisions/{decision_id}/resolve; GET /v1/decisions/{decision_id}; POST /v1/decisions/{decision_id}/answer.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt:68](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/attention/AttentionRoute.kt#L68); [android/app/src/main/java/com/dial/van/command/attention/OwnerDecisionCard.kt:32](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/attention/OwnerDecisionCard.kt#L32); [backend/van_gateway/decisions/service.py:58](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/decisions/service.py#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:56](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L56); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 03. `van.work` — Work

- **Registry source lines:** 351–476; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/work/MissionControls.kt`, `android/app/src/main/java/com/dial/van/mission/MissionIntervention.kt`.
- **Owner goal:** Send text/voice intent and follow execution..
- **Host/route:** `work` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Missions; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** conversation statuses; A4 pending; running/waiting missions; outage reconfirmations.
- **Owner action obligations:** submit text; begin voice; biometric approve; open browser/ARTEMIS/DIAL/activity; expand mission timeline; reconfirm/cancel queued intent; Cancel this active mission; Record direction on this existing mission.
- **Endpoint evidence:** POST /v1/commands; GET /v1/commands/{command_id}; GET /v1/needs-you; GET /v1/missions; GET /health; GET /v1/missions/{mission_id}/activity; POST /v1/missions/{mission_id}/cancel; POST /v1/missions/{mission_id}/message; GET /v1/owner/google/gmail/drafts/{draft_id}/preview.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_ASSET", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/work/WorkRoute.kt:58](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/work/WorkRoute.kt#L58); [android/app/src/main/java/com/dial/van/command/work/MissionControls.kt:31](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/work/MissionControls.kt#L31); [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:125](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt#L125); [android/app/src/main/java/com/dial/van/mission/MissionIntervention.kt:5](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/mission/MissionIntervention.kt#L5); [android/app/src/main/java/com/dial/van/mission/MissionIntervention.kt:11](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/mission/MissionIntervention.kt#L11); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 04. `van.work.mission` — Mission deep link

- **Registry source lines:** 477–655; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/work/MissionControls.kt`, `android/app/src/main/java/com/dial/van/command/work/MissionExecutionControls.kt`, `android/app/src/main/java/com/dial/van/mission/MissionIntervention.kt`, `backend/van_gateway/mission/control.py`.
- **Owner goal:** Open the exact mission and its timeline..
- **Host/route:** `work/missions/{missionId}` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Missions; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** mission status; timeline; current dispatch fence/generation; exact immutable request hash and direction; run-bound ordered worker acknowledgement; existing command/action authority; already-dispatched work may finish; process_stopped_verified=false.
- **Owner action obligations:** open timeline; Cancel this active mission; Record direction on this existing mission; Request exact mission pause and independently recover its ordered control receipt; Request exact mission resume and independently recover its ordered control receipt; Request exact mission direction and independently recover its ordered control receipt.
- **Endpoint evidence:** GET /v1/missions/{mission_id}/activity; POST /v1/missions/{mission_id}/cancel; POST /v1/missions/{mission_id}/message; GET /v1/missions/{mission_id}/control; GET /v1/missions/{mission_id}/control/requests/{request_id}; POST /v1/missions/{mission_id}/pause; POST /v1/missions/{mission_id}/resume; POST /v1/missions/{mission_id}/direction.
- **Historical gap categories:** `["DEPLOYMENT", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/work/WorkRoute.kt:58](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/work/WorkRoute.kt#L58); [android/app/src/main/java/com/dial/van/command/work/MissionControls.kt:31](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/work/MissionControls.kt#L31); [android/app/src/main/java/com/dial/van/mission/MissionRepository.kt:125](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/mission/MissionRepository.kt#L125); [android/app/src/main/java/com/dial/van/mission/MissionIntervention.kt:5](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/mission/MissionIntervention.kt#L5); [android/app/src/main/java/com/dial/van/mission/MissionIntervention.kt:11](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/mission/MissionIntervention.kt#L11); [android/app/src/main/java/com/dial/van/command/work/MissionExecutionControls.kt:27](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/work/MissionExecutionControls.kt#L27); [backend/van_gateway/mission/control.py:111](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/mission/control.py#L111); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57) (plus 1 more).

### 05. `van.work.activity` — Activity

- **Registry source lines:** 656–748; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/work/WorkDetails.kt`.
- **Owner goal:** Inspect received mission/agent events..
- **Host/route:** `work/activity` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Missions; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** device event stream; event types/payload.
- **Owner action obligations:** retry/re-enter; back.
- **Endpoint evidence:** GET /v1/events.
- **Historical gap categories:** `["EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/work/WorkDetails.kt:57](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/work/WorkDetails.kt#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 06. `van.work.artemis` — ARTEMIS Android Lab

- **Registry source lines:** 749–826; **old coverage:** external.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Use the Hermes governed Android testing console..
- **Host/route:** `work/artemis` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Missions; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** external web console devices/tasks/traces.
- **Owner action obligations:** mint launch; web controls allowed by console; back.
- **Endpoint evidence:** POST /v1/artemis/console/session.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/artemis/ArtemisConsoleRoute.kt:41](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/artemis/ArtemisConsoleRoute.kt#L41); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 07. `van.work.dev.home` — Development Hub

- **Registry source lines:** 827–939; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect DIAL projects and current development work and act only against the live projection..
- **Host/route:** `work/dev?project={project}` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** projects and current development work.
- **Owner action obligations:** project switch; open child.
- **Endpoint evidence:** GET /v1/dial-dev/projects; GET /v1/dial-dev/projects/{project_id}/home; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevHomeRoute.kt:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevHomeRoute.kt#L58); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [android/app/src/main/java/com/dial/van/command/dev/DevActions.kt:82](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevActions.kt#L82); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 08. `van.work.dev.plan` — Stage Plan

- **Registry source lines:** 940–1051; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect DIAL stage/phase plan and act only against the live projection..
- **Host/route:** `work/dev/{projectId}/plan` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** stage/phase plan.
- **Owner action obligations:** refresh; open task.
- **Endpoint evidence:** GET /v1/dial-dev/projects/{project_id}/stage-plan; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevPlanRoute.kt:60](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevPlanRoute.kt#L60); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [android/app/src/main/java/com/dial/van/command/dev/DevActions.kt:82](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevActions.kt#L82); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 09. `van.work.dev.tasks` — Development Tasks

- **Registry source lines:** 1052–1163; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect DIAL task list and selected view and act only against the live projection..
- **Host/route:** `work/dev/{projectId}/tasks?view={view}` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** task list and selected view.
- **Owner action obligations:** choose view; open task.
- **Endpoint evidence:** GET /v1/dial-dev/projects/{project_id}/tasks; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevTasksRoute.kt:51](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevTasksRoute.kt#L51); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [android/app/src/main/java/com/dial/van/command/dev/DevActions.kt:82](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevActions.kt#L82); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 10. `van.work.dev.graph` — Task Graph

- **Registry source lines:** 1164–1274; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect DIAL dependency graph and act only against the live projection..
- **Host/route:** `work/dev/{projectId}/graph` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents; ADD genuine interactive canvas.
- **Information obligation:** dependency graph.
- **Owner action obligations:** open task.
- **Endpoint evidence:** GET /v1/dial-dev/projects/{project_id}/graph; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevTasksRoute.kt:99](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevTasksRoute.kt#L99); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [android/app/src/main/java/com/dial/van/command/dev/DevActions.kt:82](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevActions.kt#L82); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 11. `van.work.dev.task` — Task Detail

- **Registry source lines:** 1275–1392; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect DIAL live task state, decisions/evidence and act only against the live projection..
- **Host/route:** `work/dev/tasks/{taskId}` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** live task state, decisions/evidence.
- **Owner action obligations:** steer; pause safely; resume; checkpoint; review; revoke; resolve owner decision.
- **Endpoint evidence:** GET /v1/dial-dev/tasks/{task_id}; POST /v1/dial-dev/actions; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevTaskDetailRoute.kt:48](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevTaskDetailRoute.kt#L48); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [android/app/src/main/java/com/dial/van/command/dev/DevActions.kt:82](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevActions.kt#L82); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 12. `van.work.dev.agents` — Agents

- **Registry source lines:** 1393–1503; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect DIAL agent registry/status and act only against the live projection..
- **Host/route:** `work/dev/agents` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** agent registry/status.
- **Owner action obligations:** open related task.
- **Endpoint evidence:** GET /v1/dial-dev/agents; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevAgentsRoute.kt:44](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevAgentsRoute.kt#L44); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [android/app/src/main/java/com/dial/van/command/dev/DevActions.kt:82](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevActions.kt#L82); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 13. `van.work.dev.workspaces` — Workspaces

- **Registry source lines:** 1504–1614; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect DIAL workspace list and act only against the live projection..
- **Host/route:** `work/dev/workspaces` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** workspace list.
- **Owner action obligations:** open workspace.
- **Endpoint evidence:** GET /v1/dial-dev/workspaces; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevWorkspacesRoute.kt:65](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevWorkspacesRoute.kt#L65); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [android/app/src/main/java/com/dial/van/command/dev/DevActions.kt:82](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevActions.kt#L82); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 14. `van.work.dev.workspace` — Workspace Detail

- **Registry source lines:** 1615–1729; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect DIAL workspace, bounded diff and terminal tail and act only against the live projection..
- **Host/route:** `work/dev/workspaces/{workspaceId}` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** workspace, bounded diff and terminal tail.
- **Owner action obligations:** read diff/tail; typed task controls.
- **Endpoint evidence:** GET /v1/dial-dev/workspaces/{workspace_id}; GET /v1/dial-dev/workspaces/{workspace_id}/diff; GET /v1/dial-dev/workspaces/{workspace_id}/terminal-tail; POST /v1/dial-dev/actions; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevWorkspacesRoute.kt:120](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevWorkspacesRoute.kt#L120); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [android/app/src/main/java/com/dial/van/command/dev/DevActions.kt:82](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevActions.kt#L82); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 15. `van.work.dev.evidence` — Evidence

- **Registry source lines:** 1730–1840; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect DIAL evidence projection and act only against the live projection..
- **Host/route:** `work/dev/evidence/{evidenceRef}` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** evidence projection.
- **Owner action obligations:** open admitted evidence links.
- **Endpoint evidence:** GET /v1/dial-dev/evidence/{evidence_ref}; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt:245](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt#L245); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [android/app/src/main/java/com/dial/van/command/dev/DevActions.kt:82](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevActions.kt#L82); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 16. `van.work.dev.reviews` — Development Reviews

- **Registry source lines:** 1841–1951; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect authoritative DIAL reviews projection..
- **Host/route:** `work/dev/reviews` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** reviews projection.
- **Owner action obligations:** refresh; open task/evidence where offered.
- **Endpoint evidence:** GET /v1/dial-dev/reviews; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt:50](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt#L50); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 17. `van.work.dev.memory` — Development Memory

- **Registry source lines:** 1952–2062; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect authoritative DIAL memory projection..
- **Host/route:** `work/dev/memory` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** memory projection.
- **Owner action obligations:** refresh; open task/evidence where offered.
- **Endpoint evidence:** GET /v1/dial-dev/memory; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt:91](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt#L91); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 18. `van.work.dev.research` — Development Research

- **Registry source lines:** 2063–2173; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect authoritative DIAL research projection..
- **Host/route:** `work/dev/research` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** research projection.
- **Owner action obligations:** refresh; open task/evidence where offered.
- **Endpoint evidence:** GET /v1/dial-dev/research; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt:128](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt#L128); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 19. `van.work.dev.design` — Development Design

- **Registry source lines:** 2174–2284; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect authoritative DIAL design projection..
- **Host/route:** `work/dev/design` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** design projection.
- **Owner action obligations:** refresh; open task/evidence where offered.
- **Endpoint evidence:** GET /v1/dial-dev/design; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt:154](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt#L154); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 20. `van.work.dev.ci` — Development Ci

- **Registry source lines:** 2285–2395; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect authoritative DIAL ci projection..
- **Host/route:** `work/dev/ci` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** ci projection.
- **Owner action obligations:** refresh; open task/evidence where offered.
- **Endpoint evidence:** GET /v1/dial-dev/ci; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt:184](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt#L184); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 21. `van.work.dev.security` — Development Security

- **Registry source lines:** 2396–2508; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect authoritative DIAL security projection..
- **Host/route:** `work/dev/security` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Development / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** security projection.
- **Owner action obligations:** refresh; open task/evidence where offered.
- **Endpoint evidence:** GET /v1/dial-dev/security; GET /v1/dial-dev/events.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt:218](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevHubRoutes.kt#L218); [android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevProjection.kt#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 22. `van.work.browser` — Browser & Automation

- **Registry source lines:** 2509–2594; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Monitor browser automation tasks and escalations..
- **Host/route:** `work/browser` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Missions; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** browser status; tasks; escalations; policy.
- **Owner action obligations:** open children.
- **Endpoint evidence:** GET /v1/browser/status; GET /v1/browser/tasks; GET /v1/browser/escalations; GET /v1/browser/policy.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 23. `van.work.browser.tasks` — Browser Tasks

- **Registry source lines:** 2595–2678; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect automation state and task evidence..
- **Host/route:** `work/browser/tasks` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Browser; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** task list; evidence.
- **Owner action obligations:** expand evidence; back.
- **Endpoint evidence:** GET /v1/browser/tasks; GET /v1/browser/tasks/{task_id}/evidence.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:252](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt#L252); [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:285](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt#L285); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 24. `van.work.browser.escalations` — Browser Escalations

- **Registry source lines:** 2679–2765; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Resolve a browser escalation..
- **Host/route:** `work/browser/escalations` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Browser; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** escalation; linked decision.
- **Owner action obligations:** approve/refuse; submit to VAN; back.
- **Endpoint evidence:** GET /v1/browser/escalations; POST /v1/decisions/{decision_id}/resolve; POST /v1/commands.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:166](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt#L166); [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:202](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt#L202); [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:225](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt#L225); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 25. `van.work.browser.sessions` — Browser Sessions

- **Registry source lines:** 2766–2841; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect remote sessions..
- **Host/route:** `work/browser/sessions` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Browser; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** session list derived from browser status.
- **Owner action obligations:** back.
- **Endpoint evidence:** GET /v1/browser/status.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:319](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt#L319); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 26. `van.work.browser.policy` — Browser Policy

- **Registry source lines:** 2842–2921; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Understand browser policy..
- **Host/route:** `work/browser/policy` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Browser; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** policy data.
- **Owner action obligations:** back.
- **Endpoint evidence:** GET /v1/browser/policy.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:386](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt#L386); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 27. `van.browser.interactive` — Remote Browser

- **Registry source lines:** 2922–3267; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/browser/BrowserActionPlansPanel.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserControlMutation.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserDownloadReview.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserDownloadsPanel.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserFileProvider.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserFileProvidersPanel.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserInertFileDialog.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserPhoneActions.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserSessionPanel.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserTransferClient.kt`, `backend/van_gateway/auth/provider_transport.py`, `backend/van_gateway/browser/action_plans.py`, `backend/van_gateway/browser/artifact_admission.py`.
- **Owner goal:** Browse under an owner device lease..
- **Host/route:** `none` / `none`; **presentation:** `native_activity`.
- **New destination:** Work / Browser; **disposition:** Preserve protected native activity contract; redesign chrome only.
- **Information obligation:** remote rendered page; snapshot/link state; omnibox/tabs/window state; owned download/chooser identifiers and current target; producer and media epoch; filename/type/size/hash and safe origin metadata; pending/failed/available byte effect status; host deletion acknowledgement; explicit clipboard effect receipt; current native target/hostname/profile/producer epoch; owner-prepared task/immutable plan; exact effect parameters/observed predicates; claimed/uncertain/observed result without re-actuation; foreground A3 task preparation; fresh native biometric A4 plan approval; current profile_mutation_permitted/gateway_authorized_only posture; exact click/fill parameters/step observations; cancellation fence/retained result; exact file hash/size/type/producer epoch; safe inert local preview; bounded source-labelled native analysis; exact operation result/recovery; external provider bound/executable/qualified status; unbound imports unavailable; immutable provider request/idempotency key/digest/deadline; current exact provider/owner/project destination; fresh native A4 challenge and approval state; actual one-use provider claim and independent persisted-byte receipt; explicit OBSERVED_EXTERNAL_EFFECT versus STILL_UNKNOWN observation; original canonical outcome/fence retained; UNKNOWN remains read-only; no content execution or truth promotion.
- **Owner action obligations:** inspect tabs/target/events; owner touch and keyboard; pause/resume/close; take control; delegate current control to an existing mission; review downloads and explicit save/upload/copy/paste; Confirm the current browser viewport; Pause this browser session; Request remote browser closure and distinguish local disconnect; Read current target/tab inventory and safe session event history; Resume the exact admitted session with fresh readback; Take control only after matching fresh owner lease and generation; Delegate the exact current lease to an existing mission and require authoritative readback; Review actual owned-session download records; Remove an eligible host download record and confirm exact DELETED readback; Save verified browser download bytes through the Android Storage Access Framework; Choose and upload a bounded phone document only for an explicit current browser chooser; Explicitly copy browser selection or paste phone clipboard under current owner control; Prepare an actual browser task, review exact click/fill effects and observe the sealed result without re-actuation; Inspect native file analysis and exact import operation readbacks, with bound hash/epoch and provider limits; Open independently verified selected bytes in VAN's bounded inert native viewer; Read current archive/candidate provider capability, exact admitted destination and unavailable/refused states; Prepare and independently recover the exact immutable file/destination request before any provider effect; Approve the exact file request with fresh native A4 and inspect separately admitted provider claim and persisted-byte evidence; Explicitly check an already claimed external byte receipt after an uncertain effect without resubmitting or changing the original outcome.
- **Endpoint evidence:** POST /v1/browser/interactive-sessions; GET /v1/browser/interactive-sessions/{session_id}; POST /v1/browser/interactive-sessions/{session_id}/stream-grant; POST /v1/browser/interactive-sessions/{session_id}/take-control; POST /v1/browser/interactive-sessions/{session_id}/heartbeat; POST /v1/browser/interactive-sessions/{session_id}/viewport; POST /v1/browser/interactive-sessions/{session_id}/viewport/ack; POST /v1/browser/interactive-sessions/{session_id}/suspend; DELETE /v1/browser/interactive-sessions/{session_id}; GET /v1/browser/interactive-sessions/{session_id}/downloads; DELETE /v1/browser/interactive-sessions/{session_id}/downloads/{download_id}; POST /v1/browser/interactive-sessions/{session_id}/resume; GET /v1/browser/interactive-sessions/{session_id}/tabs; GET /v1/browser/interactive-sessions/{session_id}/events; POST /v1/browser/interactive-sessions/{session_id}/delegate-control; POST /v1/browser/interactive-sessions/{session_id}/transfer-grants; GET /v1/browser/interactive-sessions/{session_id}/action-plans; POST /v1/browser/interactive-sessions/{session_id}/action-plans; GET /v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id}; POST /v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id}/cancel; POST /v1/commands; GET /v1/browser/interactive-sessions/{session_id}/downloads/{download_id}/operations; GET /v1/browser/interactive-sessions/{session_id}/file-provider-contracts; POST /v1/browser/interactive-sessions/{session_id}/file-provider-requests; GET /v1/browser/interactive-sessions/{session_id}/file-provider-requests; GET /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}; POST /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/cancel; POST /v1/browser/artifact-provider/admissions/{admission_id}/introspect; POST /v1/browser/artifact-provider/admissions/{admission_id}/claim; GET /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/observation.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt:39](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserSessionController.kt#L39); [android/app/src/main/java/com/dial/van/browser/BrowserControlMutation.kt:9](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserControlMutation.kt#L9); [android/app/src/main/java/com/dial/van/browser/BrowserSessionPanel.kt:32](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserSessionPanel.kt#L32); [android/app/src/main/java/com/dial/van/browser/BrowserActivity.kt:72](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserActivity.kt#L72); [android/app/src/main/java/com/dial/van/browser/BrowserDownloadsPanel.kt:36](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserDownloadsPanel.kt#L36); [android/app/src/main/java/com/dial/van/browser/BrowserDownloadReview.kt:10](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserDownloadReview.kt#L10); [android/app/src/main/java/com/dial/van/browser/BrowserPhoneActions.kt:30](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserPhoneActions.kt#L30); [android/app/src/main/java/com/dial/van/browser/BrowserTransferClient.kt:13](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserTransferClient.kt#L13) (plus 12 more).

### 28. `van.browser.downloads` — Downloads, uploads and content policy

- **Registry source lines:** 3268–3530; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/browser/BrowserDownloadReview.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserDownloadsPanel.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserFileProvider.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserFileProvidersPanel.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserInertFileDialog.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserPhoneActions.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserTransferClient.kt`, `backend/van_gateway/auth/provider_transport.py`, `backend/van_gateway/browser/artifact_admission.py`.
- **Owner goal:** Transfer files under explicit owner control..
- **Host/route:** `none` / `none`; **presentation:** `modal`.
- **New destination:** Work / Browser; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** Host download state, record ID and suggested name; Known size/type, dangerous/quarantine/failure reason; Record-removal confirmation derived from exact receipt and independent readback; Explicit unsupported phone binary transfer/upload and clipboard state; owned download/chooser identifiers and current target; producer and media epoch; filename/type/size/hash and safe origin metadata; pending/failed/available byte effect status; host deletion acknowledgement; explicit clipboard effect receipt; exact file hash/size/type/producer epoch; safe inert local preview; bounded source-labelled native analysis; exact operation result/recovery; external provider bound/executable/qualified status; unbound imports unavailable; immutable provider request/idempotency key/digest/deadline; current exact provider/owner/project destination; fresh native A4 challenge and approval state; actual one-use provider claim and independent persisted-byte receipt; explicit OBSERVED_EXTERNAL_EFFECT versus STILL_UNKNOWN observation; original canonical outcome/fence retained; UNKNOWN remains read-only; no content execution or truth promotion.
- **Owner action obligations:** review host downloads; save exact download to phone; choose and upload a phone document for current browser chooser; explicit copy browser selection; explicit paste phone clipboard; remove eligible host record and inspect physical cleanup acknowledgement; Review actual owned-session download records; Remove an eligible host download record and confirm exact DELETED readback; Save verified browser download bytes through the Android Storage Access Framework; Choose and upload a bounded phone document only for an explicit current browser chooser; Explicitly copy browser selection or paste phone clipboard under current owner control; Inspect native file analysis and exact import operation readbacks, with bound hash/epoch and provider limits; Open independently verified selected bytes in VAN's bounded inert native viewer; Read current archive/candidate provider capability, exact admitted destination and unavailable/refused states; Prepare and independently recover the exact immutable file/destination request before any provider effect; Approve the exact file request with fresh native A4 and inspect separately admitted provider claim and persisted-byte evidence; Explicitly check an already claimed external byte receipt after an uncertain effect without resubmitting or changing the original outcome.
- **Endpoint evidence:** GET /v1/browser/interactive-sessions/{session_id}/downloads; DELETE /v1/browser/interactive-sessions/{session_id}/downloads/{download_id}; POST /v1/browser/interactive-sessions/{session_id}/transfer-grants; GET /v1/browser/interactive-sessions/{session_id}/downloads/{download_id}/operations; GET /v1/browser/interactive-sessions/{session_id}/file-provider-contracts; POST /v1/browser/interactive-sessions/{session_id}/file-provider-requests; GET /v1/browser/interactive-sessions/{session_id}/file-provider-requests; GET /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}; POST /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/cancel; POST /v1/commands; POST /v1/browser/artifact-provider/admissions/{admission_id}/introspect; POST /v1/browser/artifact-provider/admissions/{admission_id}/claim; GET /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/observation.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/browser/BrowserDownloadsPanel.kt:36](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserDownloadsPanel.kt#L36); [android/app/src/main/java/com/dial/van/browser/BrowserDownloadReview.kt:10](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserDownloadReview.kt#L10); [android/app/src/main/java/com/dial/van/browser/BrowserActivity.kt:72](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserActivity.kt#L72); [android/app/src/main/java/com/dial/van/browser/BrowserPhoneActions.kt:30](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserPhoneActions.kt#L30); [android/app/src/main/java/com/dial/van/browser/BrowserTransferClient.kt:13](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserTransferClient.kt#L13); [backend/van_gateway/browser/interactive_api.py:128](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/browser/interactive_api.py#L128); [android/app/src/main/java/com/dial/van/browser/BrowserInertFileDialog.kt:36](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserInertFileDialog.kt#L36); [backend/van_gateway/browser/artifact_admission.py:245](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/browser/artifact_admission.py#L245) (plus 5 more).

### 29. `van.browser.outcome` — Browser task outcome evidence

- **Registry source lines:** 3531–3663; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/owner/OwnerServicePresentation.kt`, `android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt`.
- **Owner goal:** Inspect automation state and task evidence..
- **Host/route:** `owner/browser-outcome/{taskId}` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Work / Browser; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** Execution completion distinct from unverified task goal; Worker goal proposal nullable/not persisted explanation; Evidence kind/time/ID, source trust and injection assessment; URL/DOM/screenshot/extraction digest summaries; Missing postconditions and next action; Separately authoritative mission outcome, observation time and evidence references.
- **Owner action obligations:** Refresh task outcome; Open linked mission; Inspect a browser task outcome without claiming task-goal verification.
- **Endpoint evidence:** GET /v1/owner/browser/tasks/{task_id}/outcome.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt:159](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt#L159); [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt#L101); [android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt:247](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/modules/BrowserModules.kt#L247); [android/app/src/main/java/com/dial/van/command/owner/OwnerServicePresentation.kt:60](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/owner/OwnerServicePresentation.kt#L60); [android/app/src/main/java/com/dial/van/command/owner/OwnerServicePresentation.kt:73](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/owner/OwnerServicePresentation.kt#L73); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:57](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L57); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 30. `van.browser.action-plan` — Immutable browser effect review and observation

- **Registry source lines:** 3664–3795; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/browser/BrowserActionPlansPanel.kt`, `backend/van_gateway/browser/action_plans.py`.
- **Owner goal:** Ask VAN about the visible page and keep immediate owner control..
- **Host/route:** `none` / `none`; **presentation:** `modal`.
- **New destination:** Work / Browser; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** current native target/hostname/profile/producer epoch; owner-prepared task/immutable plan; exact effect parameters/observed predicates; claimed/uncertain/observed result without re-actuation; foreground A3 task preparation; fresh native biometric A4 plan approval; current profile_mutation_permitted/gateway_authorized_only posture; exact click/fill parameters/step observations; cancellation fence/retained result.
- **Owner action obligations:** Prepare an actual browser task, review exact click/fill effects and observe the sealed result without re-actuation.
- **Endpoint evidence:** GET /v1/browser/interactive-sessions/{session_id}/action-plans; POST /v1/browser/interactive-sessions/{session_id}/action-plans; GET /v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id}; POST /v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id}/cancel; POST /v1/commands.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/browser/BrowserActionPlansPanel.kt:41](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserActionPlansPanel.kt#L41); [android/app/src/main/java/com/dial/van/browser/BrowserActivity.kt:72](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserActivity.kt#L72); [backend/van_gateway/browser/action_plans.py:96](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/browser/action_plans.py#L96).

### 31. `van.browser.file-provider` — Exact owner file destination, admission and result

- **Registry source lines:** 3796–3981; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/browser/BrowserDownloadsPanel.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserFileProvider.kt`, `android/app/src/main/java/com/dial/van/browser/BrowserFileProvidersPanel.kt`, `backend/van_gateway/auth/provider_transport.py`, `backend/van_gateway/browser/artifact_admission.py`.
- **Owner goal:** Transfer files under explicit owner control..
- **Host/route:** `none` / `none`; **presentation:** `modal`.
- **New destination:** Work / Browser; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** reviewed file identity/hash/size; exact provider/owner/project destination; current target capability/availability; immutable request/digest/idempotency key/deadline; fresh exact native A4 challenge/biometric outcome; request status and original recovery identity; actual provider claim and independently observed persisted-byte receipt; explicit read-only observation separate from retained canonical outcome and replacement fence; untrusted file source; no content execution or owner/project truth promotion.
- **Owner action obligations:** Read current archive/candidate provider capability, exact admitted destination and unavailable/refused states; Prepare and independently recover the exact immutable file/destination request before any provider effect; Approve the exact file request with fresh native A4 and inspect separately admitted provider claim and persisted-byte evidence; Explicitly check an already claimed external byte receipt after an uncertain effect without resubmitting or changing the original outcome.
- **Endpoint evidence:** GET /v1/browser/interactive-sessions/{session_id}/file-provider-contracts; POST /v1/browser/interactive-sessions/{session_id}/file-provider-requests; GET /v1/browser/interactive-sessions/{session_id}/file-provider-requests; GET /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}; POST /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/cancel; POST /v1/commands; POST /v1/browser/artifact-provider/admissions/{admission_id}/introspect; POST /v1/browser/artifact-provider/admissions/{admission_id}/claim; GET /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/observation.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/browser/BrowserFileProvidersPanel.kt:38](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserFileProvidersPanel.kt#L38); [android/app/src/main/java/com/dial/van/browser/BrowserActivity.kt:72](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserActivity.kt#L72); [backend/van_gateway/browser/artifact_admission.py:245](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/browser/artifact_admission.py#L245); [android/app/src/main/java/com/dial/van/browser/BrowserFileProvider.kt:6](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserFileProvider.kt#L6); [android/app/src/main/java/com/dial/van/browser/BrowserDownloadsPanel.kt:36](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/browser/BrowserDownloadsPanel.kt#L36); [backend/van_gateway/auth/provider_transport.py:133](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/auth/provider_transport.py#L133); [backend/van_gateway/authority/descriptor.py:143](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/authority/descriptor.py#L143); [backend/van_gateway/browser/artifact_admission.py:722](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/browser/artifact_admission.py#L722).

### 32. `van.trading` — Trading

- **Registry source lines:** 3982–4056; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect portfolio and trade lifecycle..
- **Host/route:** `trading` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Trading / Terminal / Intelligence; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents; ADD Markets/Chart/Intelligence/News.
- **Information obligation:** nested overview/positions/potential/history/accounts/strategies/cognition.
- **Owner action obligations:** navigate trading children; halt trading.
- **Endpoint evidence:** No direct endpoint row recorded.
- **Historical gap categories:** `["UI_REDESIGN", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:115](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L115); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 33. `van.trading.overview` — Overview

- **Registry source lines:** 4057–4147; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect balances, assessment, active positions and events..
- **Host/route:** `overview` / `trading`; **presentation:** `nested_navigation_screen`.
- **New destination:** Trading / Terminal / Intelligence; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** portfolio; assessment; positions; events.
- **Owner action obligations:** refresh; open positions/potential/history/accounts/strategies/cognition.
- **Endpoint evidence:** GET /v1/trading/portfolio; GET /v1/trading/assessment; GET /v1/trading/positions; GET /v1/trading/events; GET /v1/trading/status.
- **Historical gap categories:** `["UI_REDESIGN", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/trading/ui/OverviewScreen.kt:69](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/OverviewScreen.kt#L69); [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:19](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt#L19); [android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt:34](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt#L34); [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:69](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L69); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 34. `van.trading.positions` — Positions

- **Registry source lines:** 4148–4233; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Review every open position..
- **Host/route:** `positions` / `trading`; **presentation:** `nested_navigation_screen`.
- **New destination:** Trading / Terminal / Intelligence; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** positions; protection; thesis.
- **Owner action obligations:** refresh; open position.
- **Endpoint evidence:** GET /v1/trading/positions.
- **Historical gap categories:** `["UI_REDESIGN", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/trading/ui/PositionsScreen.kt:45](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/PositionsScreen.kt#L45); [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:19](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt#L19); [android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt:34](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt#L34); [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:69](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L69); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 35. `van.trading.positions.detail` — Position Detail

- **Registry source lines:** 4234–4324; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Review a position chart, thesis and execution evidence..
- **Host/route:** `positions/{id}` / `trading`; **presentation:** `nested_navigation_screen`.
- **New destination:** Trading / Terminal / Intelligence; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** chart; thesis; events; proposal; risk/evidence.
- **Owner action obligations:** refresh; chart pan/zoom/inspect.
- **Endpoint evidence:** GET /v1/trading/positions; GET /v1/trading/trades/{trade_intent_id}; GET /v1/trading/events; GET /v1/trading/market-state.
- **Historical gap categories:** `["UI_REDESIGN", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/trading/ui/PositionDetailScreen.kt:64](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/PositionDetailScreen.kt#L64); [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:19](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt#L19); [android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt:34](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt#L34); [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:69](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L69); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 36. `van.trading.potential` — Potential

- **Registry source lines:** 4325–4408; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect candidate ideas and admission blockers..
- **Host/route:** `potential` / `trading`; **presentation:** `nested_navigation_screen`.
- **New destination:** Trading / Terminal / Intelligence; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** candidate theses; readiness.
- **Owner action obligations:** refresh.
- **Endpoint evidence:** GET /v1/trading/potential.
- **Historical gap categories:** `["UI_REDESIGN", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/trading/ui/PotentialScreen.kt:43](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/PotentialScreen.kt#L43); [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:19](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt#L19); [android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt:34](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt#L34); [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:69](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L69); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 37. `van.trading.history` — History & Intelligence

- **Registry source lines:** 4409–4493; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Review outcomes and decision quality..
- **Host/route:** `history` / `trading`; **presentation:** `nested_navigation_screen`.
- **New destination:** Trading / Terminal / Intelligence; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** history; intelligence filters.
- **Owner action obligations:** refresh; filter.
- **Endpoint evidence:** GET /v1/trading/history.
- **Historical gap categories:** `["UI_REDESIGN", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/trading/ui/HistoryScreen.kt:53](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/HistoryScreen.kt#L53); [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:19](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt#L19); [android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt:34](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt#L34); [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:69](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L69); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 38. `van.trading.accounts` — Accounts

- **Registry source lines:** 4494–4580; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Review account safety, health and balances..
- **Host/route:** `accounts` / `trading`; **presentation:** `nested_navigation_screen`.
- **New destination:** Trading / Terminal / Intelligence; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** account mode/safety/connection; balances; kill switch; sync age.
- **Owner action obligations:** refresh; add.
- **Endpoint evidence:** GET /v1/trading/accounts.
- **Historical gap categories:** `["UI_REDESIGN", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/trading/ui/AccountsScreen.kt:44](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/AccountsScreen.kt#L44); [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:19](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt#L19); [android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt:34](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt#L34); [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:69](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L69); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 39. `van.trading.cognition` — Cognition

- **Registry source lines:** 4581–4663; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect VAN cognition status..
- **Host/route:** `cognition` / `trading`; **presentation:** `nested_navigation_screen`.
- **New destination:** Trading / Terminal / Intelligence; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** cognition ledger.
- **Owner action obligations:** refresh.
- **Endpoint evidence:** GET /v1/trading/cognition.
- **Historical gap categories:** `["UI_REDESIGN", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/trading/ui/CognitionScreens.kt:47](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/CognitionScreens.kt#L47); [android/app/src/main/java/com/dial/van/trading/TradingRepository.kt:19](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/TradingRepository.kt#L19); [android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt:34](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingUiSupport.kt#L34); [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:69](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L69); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 40. `van.trading.accounts.add` — Add Trading Account

- **Registry source lines:** 4664–4749; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Link a broker/paper account using owner approval..
- **Host/route:** `accounts/add` / `trading`; **presentation:** `nested_navigation_screen`.
- **New destination:** Trading / Terminal / Intelligence; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** broker forms; validation/status.
- **Owner action obligations:** submit account actions; get challenge; biometric sign; Done.
- **Endpoint evidence:** POST /v1/trading/accounts/challenge; POST /v1/trading/accounts/action.
- **Historical gap categories:** `["UI_REDESIGN", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/trading/ui/AccountOnboardingScreen.kt:76](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/AccountOnboardingScreen.kt#L76); [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:69](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L69); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 41. `van.trading.strategies` — Strategies

- **Registry source lines:** 4750–4840; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Review and approve strategy promotion..
- **Host/route:** `strategies` / `trading`; **presentation:** `nested_navigation_screen`.
- **New destination:** Trading / Terminal / Intelligence; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** candidates; certificate/evidence; target states/status.
- **Owner action obligations:** authority grant; challenge; biometric proof; promote; refresh.
- **Endpoint evidence:** GET /v1/trading/strategies/promotion-candidates; POST /v1/trading/strategies/promotion-challenge; POST /v1/trading/strategies/promote.
- **Historical gap categories:** `["UI_REDESIGN", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/trading/ui/StrategiesScreen.kt:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/StrategiesScreen.kt#L68); [android/app/src/main/java/com/dial/van/trading/ui/StrategiesScreen.kt:114](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/StrategiesScreen.kt#L114); [android/app/src/main/java/com/dial/van/trading/ui/StrategiesScreen.kt:158](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/StrategiesScreen.kt#L158); [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:69](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L69); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 42. `van.trading.halt` — Halt Trading

- **Registry source lines:** 4841–4930; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Stop new trading activity across accounts with two approvals..
- **Host/route:** `none` / `trading`; **presentation:** `modal`.
- **New destination:** Trading / Terminal / Intelligence; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** action digest; authority status; pending gateway A4; command outcome.
- **Owner action obligations:** open sheet; sign authority grant; submit halt command; approve gateway A4; dismiss.
- **Endpoint evidence:** POST /v1/commands; GET /v1/commands/{command_id}; GET /v1/trading/status.
- **Historical gap categories:** `["EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:201](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L201); [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:250](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L250); [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:274](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L274); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 43. `van.trading.tickets` — Trading tickets and broker receipts

- **Registry source lines:** 4931–5032; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/trading/ui/TicketsScreen.kt`.
- **Owner goal:** Inspect real tickets and record exact broker fills with fresh owner authority and independent receipt readback..
- **Host/route:** `tickets` / `trading`; **presentation:** `nested_navigation_screen`.
- **New destination:** Trading / Terminal / Intelligence; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** ticket identifier/status; broker fill price and quantity; contract note reference; normalized approval scope/expiry; independent confirmation ledger receipt.
- **Owner action obligations:** inspect ticket; refresh; confirm exact broker fill; decline pending approval; Read and refresh actual ticket/fill-confirmation records; Record an exact broker fill with independent chained-ledger readback.
- **Endpoint evidence:** GET /v1/trading/tickets; POST /v1/commands.
- **Historical gap categories:** `["EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/trading/ui/TicketsScreen.kt:39](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/trading/ui/TicketsScreen.kt#L39); [android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt:135](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/trading/ui/TradingRoute.kt#L135); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 44. `van.approval.trading-ticket` — Exact broker-fill receipt confirmation

- **Registry source lines:** 5033–5133; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/trading/ui/TicketsScreen.kt`.
- **Owner goal:** Inspect real tickets and record exact broker fills with fresh owner authority and independent receipt readback..
- **Host/route:** `none` / `trading`; **presentation:** `modal`.
- **New destination:** Approval / Context; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** ticket identifier/status; broker fill price and quantity; contract note reference; normalized approval scope/expiry; independent confirmation ledger receipt.
- **Owner action obligations:** inspect ticket; refresh; confirm exact broker fill; decline pending approval; Record an exact broker fill with independent chained-ledger readback.
- **Endpoint evidence:** GET /v1/trading/tickets; POST /v1/commands.
- **Historical gap categories:** `["EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/trading/ui/TicketsScreen.kt:39](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/trading/ui/TicketsScreen.kt#L39); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:58](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 45. `van.memory` — Memory

- **Registry source lines:** 5134–5257; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/memory/MemoryManagement.kt`.
- **Owner goal:** See what VAN believes and add/correct/forget it..
- **Host/route:** `memory` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Memory; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** facts by scope; decisions/preferences; conflicts; stale/expiring facts; recent changes; authority/confidence.
- **Owner action obligations:** remember free text/structured; correct; forget; choose conflict value; Remember or correct a scoped owner fact; Withdraw a fact while retaining its history; Inspect a fact revision history; Inspect conflict sides and state an owner correction.
- **Endpoint evidence:** GET /v1/context/export; GET /v1/context/conflicts; POST /v1/context/facts; DELETE /v1/context/facts; POST /v1/commands; GET /v1/context/history.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:72](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt#L72); [android/app/src/main/java/com/dial/van/memory/MemoryManagement.kt:29](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/MemoryManagement.kt#L29); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:59](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L59); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 46. `van.memory.history` — Fact History

- **Registry source lines:** 5258–5357; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/memory/MemoryManagement.kt`.
- **Owner goal:** Inspect and control fact history..
- **Host/route:** `none` / `memory`; **presentation:** `modal`.
- **New destination:** Memory; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** Scoped revisions, source/trust/authority, validity, supersession and withdrawal.
- **Owner action obligations:** Inspect fact history; Refresh; Close; Inspect a fact revision history.
- **Endpoint evidence:** GET /v1/context/history.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/memory/MemoryManagement.kt:29](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/MemoryManagement.kt#L29); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:59](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L59); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 47. `van.learning.adaptations` — Adaptation review and rollback

- **Registry source lines:** 5358–5463; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/memory/UnderstandingRoutes.kt`.
- **Owner goal:** Approve or reverse learned changes..
- **Host/route:** `memory/adaptations` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Memory / Learning; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** Awaiting/active adaptations; Before/after behavior, reason, evidence and reversibility.
- **Owner action obligations:** Confirm and read back; Revert reversible change; Refresh; Read active and awaiting adaptations; Confirm and read back an adaptation; Revert a reversible adaptation.
- **Endpoint evidence:** GET /v1/understanding; POST /v1/understanding/adaptation/{change_id}/confirm; POST /v1/understanding/adaptation/{change_id}/revert.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/memory/UnderstandingRoutes.kt:36](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/UnderstandingRoutes.kt#L36); [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt#L101).

### 48. `van.learning.goals` — Goals, unresolved threads and learned strategies

- **Registry source lines:** 5464–5626; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/memory/GoalsRoute.kt`, `android/app/src/main/java/com/dial/van/memory/LearningProducerSection.kt`, `backend/van_gateway/learning/observations.py`.
- **Owner goal:** Inspect continuity, conflicts and learning limits..
- **Host/route:** `memory/goals` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Memory / Learning; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** Standing/project goals, constraints, priority and tensions; Decision history and inactive inference; Strategies, external evidence, technology radar and measured/unmeasured evaluation; independent READY/NO_DATA/PARTIAL/DEGRADED producers; bounded observations/comparisons and unmeasured counts; timestamps/snapshot digest/source references; candidate support/counterexamples/unknown outcomes; original external trust and exact scope disagreement; advisory inference with no execution grant.
- **Owner action obligations:** Read; Open linked mission; Discuss in Work; Refresh; Inspect standing goals, constraints and tensions; Read decision history and stated reasons; Inspect bounded learned strategies; Read external observations without inferred agreement; Inspect technology evaluation state; Inspect measured and unmeasured evaluation dimensions; Inspect actual independent read-time producer status, bounds, timestamps and evidence; Inspect bounded repeated-choice candidates, counterexamples and independent outcome references; Compare an exact cited structured source claim with the current matching owner declaration.
- **Endpoint evidence:** GET /v1/understanding/intents; GET /v1/understanding/decisions; GET /v1/strategies; GET /v1/external-reality; GET /v1/technology-radar; GET /v1/eval; GET /v1/understanding/learning/producers.
- **Historical gap categories:** `["EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/memory/GoalsRoute.kt:25](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/GoalsRoute.kt#L25); [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt#L101); [android/app/src/main/java/com/dial/van/memory/LearningProducerSection.kt:16](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/LearningProducerSection.kt#L16); [backend/van_gateway/learning/observations.py:114](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/learning/observations.py#L114); [backend/van_gateway/knowledge/evidence.py:14](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/knowledge/evidence.py#L14); [backend/van_gateway/learning/observations.py:58](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/learning/observations.py#L58).

### 49. `van.memory.privacy` — Memory privacy and retention

- **Registry source lines:** 5627–5790; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/work/WorkDetails.kt`, `android/app/src/main/java/com/dial/van/memory/DerivedMemoryRecordsSection.kt`, `android/app/src/main/java/com/dial/van/memory/MemoryEffectReceipt.kt`, `android/app/src/main/java/com/dial/van/memory/MemoryManagement.kt`, `backend/van_gateway/context/memory_erasure.py`, `backend/van_gateway/understanding/records.py`.
- **Owner goal:** Inspect and control fact history..
- **Host/route:** `none` / `memory`; **presentation:** `modal`.
- **New destination:** Memory; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** Actual owner-derived stores, row counts, retained record categories; Erasure target and exact approval scope; privacy-safe stable record identity; declared/observed/inferred/mixed/unclassified provenance; screened bounded fields/export; complete stored-scope revision digest; affected store counts/dependent identities; retained work/audit and independent erased-identity readback.
- **Owner action obligations:** Inspect stores; Request forget store/all; Cancel confirmation; Open Work approval; Inspect held stores and retention; Request erasure of a listed store or all owner-derived memory; Inspect paginated exact records, screened fields and declared/observed/inferred provenance; Copy an independently reread screened bounded representation of the selected exact record; Review affected record counts and request fresh biometric erasure of precisely that revision.
- **Endpoint evidence:** GET /v1/context/memory; POST /v1/commands; GET /v1/commands/{command_id}; GET /v1/context/export; GET /v1/context/records; GET /v1/context/records/{store}/{record_id}; GET /v1/context/records/{store}/{record_id}/export; GET /v1/context/records/{store}/{record_id}/erasure-plan.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/memory/MemoryManagement.kt:56](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/MemoryManagement.kt#L56); [android/app/src/main/java/com/dial/van/memory/MemoryEffectReceipt.kt:4](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/MemoryEffectReceipt.kt#L4); [android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt:72](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/MemoryRoute.kt#L72); [android/app/src/main/java/com/dial/van/command/work/WorkDetails.kt:159](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/work/WorkDetails.kt#L159); [android/app/src/main/java/com/dial/van/control/VanCommandController.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/control/VanCommandController.kt#L101); [android/app/src/main/java/com/dial/van/memory/DerivedMemoryRecordsSection.kt:36](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/DerivedMemoryRecordsSection.kt#L36); [backend/van_gateway/understanding/records.py:126](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/understanding/records.py#L126); [android/app/src/main/java/com/dial/van/memory/DerivedMemoryRecordsSection.kt:67](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/DerivedMemoryRecordsSection.kt#L67) (plus 3 more).

### 50. `van.attention.decision` — Exact owner choice and evidence

- **Registry source lines:** 5791–5905; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/attention/OwnerDecisionCard.kt`.
- **Owner goal:** Understand why owner input is needed and record a choice..
- **Host/route:** `none` / `attention`; **presentation:** `inline_section`.
- **New destination:** Attention / Decisions; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** listed stable choices and proposed labels; exact owner note/revision/expiry; REFERENCE_ONLY versus RECORDED_EVENT evidence; immutable answer/recovery identity; grants_action_authority=false.
- **Owner action obligations:** Read and answer an exact owner choice with evidence, expiry, note and immutable recovery identity.
- **Endpoint evidence:** GET /v1/decisions/{decision_id}; POST /v1/decisions/{decision_id}/answer.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/attention/OwnerDecisionCard.kt:32](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/attention/OwnerDecisionCard.kt#L32); [backend/van_gateway/decisions/service.py:58](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/decisions/service.py#L58); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:59](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L59); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 51. `van.work.mission-control` — Mission dispatch fence and direction receipt

- **Registry source lines:** 5906–6044; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/work/MissionExecutionControls.kt`, `backend/van_gateway/mission/control.py`.
- **Owner goal:** Stop or add direction to the existing mission..
- **Host/route:** `none` / `work`; **presentation:** `inline_section`.
- **New destination:** Work / Missions; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** current dispatch fence/generation; exact immutable request hash and direction; run-bound ordered worker acknowledgement; existing command/action authority; already-dispatched work may finish; process_stopped_verified=false.
- **Owner action obligations:** Request exact mission pause and independently recover its ordered control receipt; Request exact mission resume and independently recover its ordered control receipt; Request exact mission direction and independently recover its ordered control receipt.
- **Endpoint evidence:** GET /v1/missions/{mission_id}/control; GET /v1/missions/{mission_id}/control/requests/{request_id}; POST /v1/missions/{mission_id}/pause; POST /v1/missions/{mission_id}/resume; POST /v1/missions/{mission_id}/direction.
- **Historical gap categories:** `["DEPLOYMENT", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/work/MissionExecutionControls.kt:27](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/work/MissionExecutionControls.kt#L27); [backend/van_gateway/mission/control.py:111](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/mission/control.py#L111); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:59](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L59); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 52. `van.memory.record` — Exact retained record and erasure scope

- **Registry source lines:** 6045–6186; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/memory/DerivedMemoryRecordsSection.kt`, `backend/van_gateway/context/memory_erasure.py`, `backend/van_gateway/understanding/records.py`.
- **Owner goal:** Read everything VAN holds and control retention..
- **Host/route:** `none` / `memory`; **presentation:** `modal`.
- **New destination:** Memory; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** privacy-safe stable record identity; declared/observed/inferred/mixed/unclassified provenance; screened bounded fields/export; complete stored-scope revision digest; affected store counts/dependent identities; retained work/audit and independent erased-identity readback.
- **Owner action obligations:** Inspect paginated exact records, screened fields and declared/observed/inferred provenance; Copy an independently reread screened bounded representation of the selected exact record; Review affected record counts and request fresh biometric erasure of precisely that revision.
- **Endpoint evidence:** GET /v1/context/records; GET /v1/context/records/{store}/{record_id}; GET /v1/context/records/{store}/{record_id}/export; GET /v1/context/records/{store}/{record_id}/erasure-plan; POST /v1/commands.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/memory/DerivedMemoryRecordsSection.kt:67](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/DerivedMemoryRecordsSection.kt#L67); [android/app/src/main/java/com/dial/van/memory/DerivedMemoryRecordsSection.kt:36](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/DerivedMemoryRecordsSection.kt#L36); [backend/van_gateway/understanding/records.py:126](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/understanding/records.py#L126); [backend/van_gateway/context/memory_erasure.py:94](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/context/memory_erasure.py#L94); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:59](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L59); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 53. `van.permissions.grant` — Exact bounded owner consent

- **Registry source lines:** 6187–6315; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/settings/OwnerPermissionGrantSection.kt`, `backend/van_gateway/capability/owner_permissions.py`.
- **Owner goal:** Know and revoke what VAN may do unprompted..
- **Host/route:** `none` / `settings/permissions`; **presentation:** `inline_section`.
- **New destination:** Permissions; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** supported action contracts/exact parameter scope; expiry/max uses and remaining-use enforcement; fresh native approval/separate service authority; stored grant/use/revoke readback.
- **Owner action obligations:** Select a supported action and review bounded exact scope, expiry and maximum uses before A4 approval; Inspect the exact stored grant and independent use/remaining-scope readback; revoke it explicitly.
- **Endpoint evidence:** GET /v1/permissions/contracts; POST /v1/commands; GET /v1/permissions/grants/{grant_id}; POST /v1/permissions/{grant_id}/revoke.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/settings/OwnerPermissionGrantSection.kt:30](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/settings/OwnerPermissionGrantSection.kt#L30); [backend/van_gateway/capability/owner_permissions.py:136](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/capability/owner_permissions.py#L136); [android/app/src/main/java/com/dial/van/command/settings/OwnerPermissionGrantSection.kt:86](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/settings/OwnerPermissionGrantSection.kt#L86); [backend/van_gateway/capability/owner_permissions.py:217](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/capability/owner_permissions.py#L217); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:59](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L59); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 54. `van.automation.plan` — Automation candidate, admission and exact run evidence

- **Registry source lines:** 6316–6462; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/owner/OwnerAutomationPlansSection.kt`, `backend/van_gateway/automation/dsl.py`, `backend/van_gateway/automation/owner_api.py`, `backend/van_gateway/automation/worker_runtime.py`.
- **Owner goal:** Inspect bounded automation and disable standing work..
- **Host/route:** `none` / `owner/automation`; **presentation:** `inline_section`.
- **New destination:** Automation; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** supported closed IR/DSL and deployment requirements; immutable candidate request/artifact/revision; pinned admitted helper/parent manifests and inputs; selected/skipped/refused step receipts; preconditions/independent target predicates; actual provider/worker configuration status.
- **Owner action obligations:** Prepare a bounded typed IR candidate, recover the exact artifact and review its declared deployment limitations; Review deterministic supported branches, mappings, preconditions and independent success predicates; Request only an admitted immutable artifact with pinned inputs and inspect actual run/step evidence.
- **Endpoint evidence:** GET /v1/owner/automation/contracts; POST /v1/owner/automation/plans; GET /v1/owner/automation/plans; GET /v1/owner/automation/plans/{artifact_id}; GET /v1/owner/automation/requests/{idempotency_key}; GET /v1/owner/automation/runs/{run_id}; POST /v1/commands.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/owner/OwnerAutomationPlansSection.kt:31](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/owner/OwnerAutomationPlansSection.kt#L31); [backend/van_gateway/automation/owner_api.py:59](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/owner_api.py#L59); [backend/van_gateway/automation/dsl.py:103](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/dsl.py#L103); [backend/van_gateway/automation/dsl.py:138](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/dsl.py#L138); [backend/van_gateway/automation/worker_runtime.py:165](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/worker_runtime.py#L165); [backend/van_gateway/automation/worker_runtime.py:737](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/worker_runtime.py#L737); [backend/van_gateway/automation/verifier.py:42](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/verifier.py#L42); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:59](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L59) (plus 1 more).

### 55. `van.settings.speaker-profile` — Local owner speaker consent, capture and erasure

- **Registry source lines:** 6463–6635; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentManager.kt`, `android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentPanel.kt`, `android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentPolicy.kt`, `android/app/src/main/java/com/dial/van/voice/SpeakerProfileStore.kt`.
- **Owner goal:** Correct pronunciation/recognition and control adaptation..
- **Host/route:** `none` / `settings/voice`; **presentation:** `inline_section`.
- **New destination:** Settings / Devices; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** generic speaker model readiness separate from authenticated profile presence; current full owner/device/hardware/approval binding; dedicated local consent operation/revision/model/freshness; current clip phrase/index/energy quality/progress; encrypted normalized embedding and retained consent metadata; no stored raw PCM; inconclusive stale/unbound speaker evidence; no action authority; exact offline erasure using genuine local keys and absence readback.
- **Owner action obligations:** Enroll owner voice or replace retained profile after dedicated native strong biometric consent; Allow microphone and observe actual current phrase, clip index and sample progress; Cancel pending consent or capture without replacing or erasing the existing profile; Read current model/profile readiness with exact binding and encrypted-store readback; Erase the exact local profile after separate fresh cryptographic consent and verify absence; Enroll or replace the exact device-local owner profile using dedicated biometric consent and three actual microphone clips; Read local profile/model readiness and permit revocable similarity evidence only for the exact fresh current owner binding; Erase precisely the retained encrypted profile after dedicated biometric consent, including when the backend is unreachable.
- **Endpoint evidence:** No direct endpoint row recorded.
- **Historical gap categories:** `["ACOUSTIC_ASSET_QUALIFICATION", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentPanel.kt:47](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentPanel.kt#L47); [android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentManager.kt:33](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentManager.kt#L33); [android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentPolicy.kt:75](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentPolicy.kt#L75); [android/app/src/main/java/com/dial/van/voice/SherpaSpeakerSimilarity.kt:12](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/SherpaSpeakerSimilarity.kt#L12); [android/app/src/main/java/com/dial/van/voice/SpeakerProfileStore.kt:9](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/SpeakerProfileStore.kt#L9); [android/app/src/main/java/com/dial/van/voice/SherpaSpeakerSimilarity.kt:61](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/SherpaSpeakerSimilarity.kt#L61); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:59](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L59); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 56. `van.projects` — Projects

- **Registry source lines:** 6636–6718; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Find project phase, health and blockers..
- **Host/route:** `projects` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Projects / Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** project ID; health; phase; running/blocker counts.
- **Owner action obligations:** open project.
- **Endpoint evidence:** GET /v1/projects; GET /v1/missions; GET /v1/attention; GET /v1/context/export; GET /v1/projects/{project_id}/truth.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt:64](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/projects/ProjectsRoute.kt#L64); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:60](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L60); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 57. `van.projects.detail` — Project Detail

- **Registry source lines:** 6719–6817; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Understand one project and ask VAN about it..
- **Host/route:** `projects/{projectId}` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Projects / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** truth SHA/repo SHA; current work; blockers; recent changes; decisions; next actions; context.
- **Owner action obligations:** ask VAN; open DIAL hub; Open rationale independently from the main project read.
- **Endpoint evidence:** GET /v1/projects/{project_id}/truth; GET /v1/missions; GET /v1/attention; GET /v1/decisions; GET /v1/context/export; GET /v1/dial-dev/projects; POST /v1/commands.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt#L68); [android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:129](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt#L129); [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:288](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt#L288); [android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt:59](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/projects/ProjectDetailRoute.kt#L59); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:60](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L60); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 58. `van.projects.rationale` — Project rationale and decision provenance

- **Registry source lines:** 6818–6930; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/projects/ProjectRationaleRoute.kt`.
- **Owner goal:** Remember why choices were made and rejected..
- **Host/route:** `projects/{projectId}/rationale` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Projects / Spatial Flow; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** rationale; tried/rejected approaches; evidence refs; separation from repository truth.
- **Owner action obligations:** inspect rationale; record owner rationale; Inspect project rationale, past rejected strategies and provenance; Record owner-authored rationale and verify same-project readback.
- **Endpoint evidence:** GET /v1/projects/{project_id}/strategic-memory; POST /v1/projects/{project_id}/strategic-memory.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/projects/ProjectRationaleRoute.kt:31](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/projects/ProjectRationaleRoute.kt#L31); [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt#L101); [android/app/src/main/java/com/dial/van/projects/ProjectRationaleRoute.kt:40](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/projects/ProjectRationaleRoute.kt#L40); [android/app/src/main/java/com/dial/van/projects/ProjectRationaleRoute.kt:68](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/projects/ProjectRationaleRoute.kt#L68).

### 59. `van.connected` — Connected

- **Registry source lines:** 6931–7018; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Inspect provider readiness and revoke Google..
- **Host/route:** `connected` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Connected; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** Hermes health; knowledge readiness; Google credential planes; DIAL fabric.
- **Owner action obligations:** revoke Google with confirmation; retry.
- **Endpoint evidence:** GET /health; GET /v1/google/planes; POST /v1/google/owner-revoke; GET /v1/dial-dev/infrastructure; GET /v1/google/status.
- **Historical gap categories:** `["EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt:62](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt#L62); [android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt:187](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/connected/ConnectedRoute.kt#L187); [android/app/src/main/java/com/dial/van/command/dev/DevSections.kt:47](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/dev/DevSections.kt#L47); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:61](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L61); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 60. `van.settings` — Settings & Devices

- **Registry source lines:** 7019–7155; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Manage device capabilities and diagnose unavailable features..
- **Host/route:** `settings` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Settings / Devices; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** local paired/hardware-bound state; display awareness; renderer status; device/gateway diagnostics.
- **Owner action obligations:** floating start/stop; Android accessibility settings; restore subsystem; accept asset with biometric; debug candidate preview; open voice/notifications.
- **Endpoint evidence:** GET /v1/degraded; POST /v1/visual/acceptance.
- **Historical gap categories:** `["RELEASE_PROVISIONING", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/settings/SettingsRoute.kt:79](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/settings/SettingsRoute.kt#L79); [android/app/src/main/java/com/dial/van/command/settings/SettingsRoute.kt:103](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/settings/SettingsRoute.kt#L103); [android/app/src/main/java/com/dial/van/command/settings/SettingsRoute.kt:133](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/settings/SettingsRoute.kt#L133); [android/app/src/main/java/com/dial/van/command/settings/SettingsRoute.kt:175](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/settings/SettingsRoute.kt#L175); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:62](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L62); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 61. `van.diagnostics` — Connection health and command correlation

- **Registry source lines:** 7156–7269; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt`.
- **Owner goal:** Understand a failure and inspect safe evidence..
- **Host/route:** `owner/diagnostics` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Settings / Diagnostics; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** health/degraded; transport mode/path; queue/breaker; trace/alerts; mission/command/run correlation; verification state.
- **Owner action obligations:** inspect trace/evidence; copy redacted diagnostic receipt; retry supported request; Inspect owner-safe settings records.
- **Endpoint evidence:** GET /health; GET /v1/observability/health; GET /v1/observability/alerts; GET /v1/observability/trace/{command_id}; GET /v1/events; GET /v1/owner/diagnostics.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt:159](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt#L159); [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt#L101).

### 62. `van.onboarding` — Device Onboarding

- **Registry source lines:** 7270–7348; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Grant the Android capabilities needed by resident VAN..
- **Host/route:** `none` / `none`; **presentation:** `native_activity`.
- **New destination:** Onboarding; **disposition:** Preserve protected native activity contract; redesign chrome only.
- **Information obligation:** permission readiness; overlay/notification/microphone/battery/biometric stages.
- **Owner action obligations:** open Android settings; grant microphone; continue to Command Centre.
- **Endpoint evidence:** No direct endpoint row recorded.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/onboarding/OnboardingActivity.kt:39](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/onboarding/OnboardingActivity.kt#L39); [android/app/src/main/java/com/dial/van/onboarding/OnboardingPlan.kt:1](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/onboarding/OnboardingPlan.kt#L1); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:62](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L62); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 63. `van.provisioning` — Signed Provisioning Intake

- **Registry source lines:** 7349–7559; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Enroll this owner device through the signed installer without an interactive setup screen..
- **Host/route:** `none` / `none`; **presentation:** `headless_intake_activity`.
- **New destination:** Provisioning Intake; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** safe installer intake acknowledgment/refusal reason; safe application log after enrollment succeeds or fails.
- **Owner action obligations:** installer invokes explicit Activity with signed envelope; validate signature, expiry and replay; pair and bind hardware identity on application scope; finish intake Activity immediately.
- **Endpoint evidence:** POST /v1/devices/pair; POST /v1/devices/bootstrap/challenge; POST /v1/devices/bootstrap/attest; POST /v1/devices/bootstrap/recover; POST /v1/device-binding/certify; POST /v1/devices/provisioning-status.
- **Historical gap categories:** `["DEPLOYMENT", "RELEASE_PROVISIONING", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/provisioning/ProvisioningActivity.kt:63](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/provisioning/ProvisioningActivity.kt#L63); [android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt:297](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt#L297); [android/app/src/main/AndroidManifest.xml:66](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/AndroidManifest.xml#L66); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:62](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L62); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 64. `van.settings.voice` — Voice Settings

- **Registry source lines:** 7560–7723; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentManager.kt`, `android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentPanel.kt`, `android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentPolicy.kt`, `android/app/src/main/java/com/dial/van/voice/SpeakerProfileStore.kt`.
- **Owner goal:** Teach personal speech corrections and pin names..
- **Host/route:** `settings/voice` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Settings / Devices; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** correction fields; pinned term fields; context selector; generic speaker model readiness separate from authenticated profile presence; current full owner/device/hardware/approval binding; dedicated local consent operation/revision/model/freshness; current clip phrase/index/energy quality/progress; encrypted normalized embedding and retained consent metadata; no stored raw PCM; inconclusive stale/unbound speaker evidence; no action authority; exact offline erasure using genuine local keys and absence readback.
- **Owner action obligations:** recordCorrection; pinTerm; choose context; back; Enroll or replace the exact device-local owner profile using dedicated biometric consent and three actual microphone clips; Read local profile/model readiness and permit revocable similarity evidence only for the exact fresh current owner binding; Erase precisely the retained encrypted profile after dedicated biometric consent, including when the backend is unreachable.
- **Endpoint evidence:** No direct endpoint row recorded.
- **Historical gap categories:** `["ACOUSTIC_ASSET_QUALIFICATION", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/modules/SpeechModule.kt:47](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/modules/SpeechModule.kt#L47); [android/app/src/main/java/com/dial/van/command/modules/SpeechModule.kt:94](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/modules/SpeechModule.kt#L94); [android/app/src/main/java/com/dial/van/command/modules/SpeechModule.kt:128](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/command/modules/SpeechModule.kt#L128); [android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentPanel.kt:47](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentPanel.kt#L47); [android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentManager.kt:33](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentManager.kt#L33); [android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentPolicy.kt:75](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/SpeakerEnrollmentPolicy.kt#L75); [android/app/src/main/java/com/dial/van/voice/SherpaSpeakerSimilarity.kt:12](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/SherpaSpeakerSimilarity.kt#L12); [android/app/src/main/java/com/dial/van/voice/SpeakerProfileStore.kt:9](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/SpeakerProfileStore.kt#L9) (plus 3 more).

### 65. `van.voice.turn` — Voice Turn

- **Registry source lines:** 7724–7893; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/session/HttpSessionCarrier.kt`, `android/app/src/main/java/com/dial/van/voice/EmbeddedVoiceAssetInstaller.kt`, `android/app/src/main/java/com/dial/van/voice/OfflineVoiceTurn.kt`, `android/app/src/main/java/com/dial/van/voice/VoiceAssetInstaller.kt`, `android/app/src/main/java/com/dial/van/voice/VoiceTurnLifecycle.kt`.
- **Owner goal:** Speak, review transcription and interrupt safely..
- **Host/route:** `none` / `work`; **presentation:** `inline_section`.
- **New destination:** Voice / VAN; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** recognition result/state currently produced in app only; actual generic bundle/install/runtime readiness; selected recognition/TTS engine and offline fallback; actual EnergyVadGate endpointing for local PCM turns; permission/no-speech/timeout/cancel/late-final states; declared assets are separate from prepared usable models and acoustic accuracy; actual owner speaker enrollment controls available; owner profile absent until real capture; generic models grant no owner identity or action authority.
- **Owner action obligations:** beginOwnerTurn; Cancel unsubmitted speech and reject late recognition results; Keep the same owner envelope and acknowledgment boundary on authenticated POST/SSE fallback; Use automatically installed generic local acoustic assets and retain honest engine/fallback readiness without phone configuration; End the selected local Sherpa recognition turn on actual EnergyVadGate speech/silence or explicit bounded no-speech/maximum-duration state.
- **Endpoint evidence:** POST /v1/commands; POST /v1/session/messages; GET /v1/session/events-stream.
- **Historical gap categories:** `["ACOUSTIC_ASSET_QUALIFICATION", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/work/WorkRoute.kt:58](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/work/WorkRoute.kt#L58); [android/app/src/main/java/com/dial/van/voice/VoiceInterfaces.kt:922](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/VoiceInterfaces.kt#L922); [android/app/src/main/java/com/dial/van/voice/VoiceTurnLifecycle.kt:19](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/VoiceTurnLifecycle.kt#L19); [android/app/src/main/java/com/dial/van/session/VanHermesSessionManager.kt:47](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/session/VanHermesSessionManager.kt#L47); [android/app/src/main/java/com/dial/van/session/HttpSessionCarrier.kt:23](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/session/HttpSessionCarrier.kt#L23); [android/app/src/main/java/com/dial/van/voice/VoiceAssetInstaller.kt:10](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/VoiceAssetInstaller.kt#L10); [android/app/src/main/java/com/dial/van/voice/EmbeddedVoiceAssetInstaller.kt:10](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/EmbeddedVoiceAssetInstaller.kt#L10); [android/app/src/main/java/com/dial/van/voice/VoiceEdge.kt:29](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/voice/VoiceEdge.kt#L29) (plus 6 more).

### 66. `van.settings.notifications` — Notification Policy

- **Registry source lines:** 7894–7999; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/notification/NotificationAppCatalogue.kt`.
- **Owner goal:** Choose apps VAN reads and quiet hours..
- **Host/route:** `settings/notifications` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Settings / Devices; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** explicit decided package policies; quiet config.
- **Owner action obligations:** toggle quiet; start/end +1h; normal/priority/mute; mute package by name; Review and change explicit policy for apps actually observed.
- **Endpoint evidence:** No direct endpoint row recorded.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/modules/NotificationPolicyModule.kt:48](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/modules/NotificationPolicyModule.kt#L48); [android/app/src/main/java/com/dial/van/notification/VanNotificationListenerService.kt:26](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/notification/VanNotificationListenerService.kt#L26); [android/app/src/main/java/com/dial/van/notification/NotificationAppCatalogue.kt:11](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/notification/NotificationAppCatalogue.kt#L11); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:62](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L62); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 67. `van.floating` — Floating VAN

- **Registry source lines:** 8000–8088; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Keep VAN available over other apps..
- **Host/route:** `none` / `none`; **presentation:** `overlay_service`.
- **New destination:** Floating VAN; **disposition:** Preserve resident lifecycle and gestures; rebuild spatial embodiment and workboard.
- **Information obligation:** embodiment/chrome; conversation; trade ledger.
- **Owner action obligations:** drag/dock/minimize/dismiss; chat; voice; open owner routes; refresh trades.
- **Endpoint evidence:** POST /v1/commands; GET /v1/trading/trades.
- **Historical gap categories:** `["UI_REDESIGN", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/overlay/FloatingOverlayService.kt:217](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/overlay/FloatingOverlayService.kt#L217); [android/app/src/main/java/com/dial/van/overlay/VanOverlaySurface.kt:137](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/overlay/VanOverlaySurface.kt#L137); [android/app/src/main/java/com/dial/van/overlay/VanOverlayWorkboards.kt:48](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/overlay/VanOverlayWorkboards.kt#L48); [android/app/src/main/java/com/dial/van/overlay/VanOverlayPanels.kt:78](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/overlay/VanOverlayPanels.kt#L78); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:11](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L11); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 68. `van.permissions` — Standing Permissions

- **Registry source lines:** 8089–8273; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/settings/OwnerPermissionGrantSection.kt`, `android/app/src/main/java/com/dial/van/command/settings/PermissionsRoute.kt`, `backend/van_gateway/capability/owner_permissions.py`, `backend/van_gateway/proactive/owner_control.py`.
- **Owner goal:** Inspect and control standing permissions..
- **Host/route:** `settings/permissions` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Permissions; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** standing grants; origin/last use/expiry; domain earned/owner/effective ceilings; suspensions; policy; supported domains and levels; exact normalized ceiling change and expiry; independent operation-specific stored ceiling readback; supported action contracts/exact parameter scope; expiry/max uses and remaining-use enforcement; fresh native approval/separate service authority; stored grant/use/revoke readback.
- **Owner action obligations:** inspect grant; revoke grant; inspect authority descriptor and readiness; select supported domain and S0..S4 owner ceiling; review and biometrically approve exact sealed ceiling change; Inspect standing permissions; Withdraw this standing permission; Inspect earned, owner and effective autonomy ceilings; Inspect action gates; Inspect automatic capability readiness; Choose a supported domain and owner autonomy ceiling, then approve the exact sealed change with biometrics; Select a supported action and review bounded exact scope, expiry and maximum uses before A4 approval; Inspect the exact stored grant and independent use/remaining-scope readback; revoke it explicitly.
- **Endpoint evidence:** GET /v1/permissions; POST /v1/permissions/{grant_id}/revoke; GET /v1/autonomy; GET /v1/authority; GET /v1/capabilities/status; POST /v1/commands; GET /v1/permissions/contracts; GET /v1/permissions/grants/{grant_id}.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/settings/PermissionsRoute.kt:34](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/settings/PermissionsRoute.kt#L34); [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt#L101); [backend/van_gateway/proactive/owner_control.py:75](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/proactive/owner_control.py#L75); [android/app/src/main/java/com/dial/van/command/settings/OwnerPermissionGrantSection.kt:30](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/settings/OwnerPermissionGrantSection.kt#L30); [backend/van_gateway/capability/owner_permissions.py:136](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/capability/owner_permissions.py#L136); [android/app/src/main/java/com/dial/van/command/settings/OwnerPermissionGrantSection.kt:86](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/settings/OwnerPermissionGrantSection.kt#L86); [backend/van_gateway/capability/owner_permissions.py:217](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/capability/owner_permissions.py#L217); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:62](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L62) (plus 1 more).

### 69. `van.autonomy` — Autonomy

- **Registry source lines:** 8274–8414; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/settings/PermissionsRoute.kt`, `backend/van_gateway/proactive/owner_control.py`.
- **Owner goal:** Inspect and control autonomy..
- **Host/route:** `none` / `settings/permissions`; **presentation:** `inline_section`.
- **New destination:** Permissions / Autonomy; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** standing grants; origin/last use/expiry; domain earned/owner/effective ceilings; suspensions; policy; supported domains and levels; exact normalized ceiling change and expiry; independent operation-specific stored ceiling readback.
- **Owner action obligations:** inspect grant; revoke grant; inspect authority descriptor and readiness; select supported domain and S0..S4 owner ceiling; review and biometrically approve exact sealed ceiling change; Inspect earned, owner and effective autonomy ceilings; Inspect action gates; Inspect automatic capability readiness; Choose a supported domain and owner autonomy ceiling, then approve the exact sealed change with biometrics.
- **Endpoint evidence:** GET /v1/autonomy; GET /v1/authority; GET /v1/capabilities/status; POST /v1/commands.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/settings/PermissionsRoute.kt:34](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/settings/PermissionsRoute.kt#L34); [backend/van_gateway/proactive/owner_control.py:75](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/proactive/owner_control.py#L75); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:62](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L62); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 70. `van.understanding` — Understanding & Adaptation

- **Registry source lines:** 8415–8557; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/memory/OwnerDeclarationSections.kt`, `android/app/src/main/java/com/dial/van/memory/UnderstandingRoutes.kt`, `backend/van_gateway/understanding/owner_preferences.py`.
- **Owner goal:** Inspect and control understanding & adaptation..
- **Host/route:** `memory/understanding` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Memory / Adaptation; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** owner assertions; OWNER_CONFIRMED/EVIDENCE_DERIVED/TENTATIVE/REJECTED/REVOKED; vocabulary; calibration; cognitive complement; owner meaning and operationalization; examples and counterexamples; optional existing project scope; owner-authored provenance and exact committed readback; separate inferred-trait confidence; declarations grant no execution authority.
- **Owner action obligations:** confirm; correct; reject; define or edit a scoped vocabulary term; set an explicit domain collaboration instruction; Inspect assertions, evidence, vocabulary and communication calibration; Confirm an assertion; Correct and supersede an assertion; Reject an assertion; Define or edit a scoped shared term with exact committed definition and owner provenance readback; Record or edit an explicit domain collaboration instruction with matching owner-authored readback.
- **Endpoint evidence:** GET /v1/understanding; POST /v1/understanding/{assertion_id}/confirm; POST /v1/understanding/{assertion_id}/correct; POST /v1/understanding/{assertion_id}/reject; POST /v1/understanding/adaptation/{change_id}/revert; POST /v1/understanding/adaptation/{change_id}/confirm; GET /v1/understanding/vocabulary; PUT /v1/understanding/vocabulary; GET /v1/understanding/complement/preferences; PUT /v1/understanding/complement/preferences.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/memory/UnderstandingRoutes.kt:36](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/UnderstandingRoutes.kt#L36); [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt#L101); [android/app/src/main/java/com/dial/van/memory/OwnerDeclarationSections.kt:28](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/OwnerDeclarationSections.kt#L28); [backend/van_gateway/understanding/owner_preferences.py:133](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/understanding/owner_preferences.py#L133); [android/app/src/main/java/com/dial/van/memory/OwnerDeclarationSections.kt:85](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/memory/OwnerDeclarationSections.kt#L85); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:59](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L59); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 71. `van.reminders.manage` — Reminder Management

- **Registry source lines:** 8558–8679; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt`.
- **Owner goal:** Inspect and control reminder management..
- **Host/route:** `attention/reminders` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Attention / Reminders; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** Open reminder text, due time and overdue state; Create/resolve/cancel receipt state; UTC parse semantics and local due readback.
- **Owner action obligations:** Create; Resolve; Cancel; Refresh; Read open reminders; Create a reminder with explicit due time; Resolve a reminder; Cancel a reminder.
- **Endpoint evidence:** GET /v1/reminders; POST /v1/reminders/parse; POST /v1/reminders/{reminder_id}/resolve; POST /v1/reminders/{reminder_id}/cancel.
- **Historical gap categories:** `["PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt:35](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt#L35); [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt#L101); [android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt:40](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt#L40); [android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt:50](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt#L50); [android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt:66](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt#L66); [android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt:79](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/attention/RemindersRoute.kt#L79); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:55](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L55); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

### 72. `van.approval.detail` — Exact-action approval and refusal

- **Registry source lines:** 8680–8800; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Approve the exact consequential effect deliberately..
- **Host/route:** `none` / `work`; **presentation:** `inline_section`.
- **New destination:** Approval / Context; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** Original owner command; Resolved action ID; Approval expiry; Biometric challenge pending/refusal.
- **Owner action obligations:** Approve this occurrence through device biometrics; Dismiss OS biometric prompt; Approve the displayed command occurrence with device biometrics; Explicitly decline the displayed occurrence without authorizing an action.
- **Endpoint evidence:** POST /v1/commands; GET /v1/authority; GET /v1/owner/google/gmail/drafts/{draft_id}/preview.
- **Historical gap categories:** `["EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/work/WorkRoute.kt:58](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/work/WorkRoute.kt#L58); [android/app/src/main/java/com/dial/van/control/VanCommandController.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/control/VanCommandController.kt#L101); [android/app/src/main/java/com/dial/van/control/VanCommandController.kt:274](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/control/VanCommandController.kt#L274).

### 73. `van.knowledge.research` — Research, private knowledge and evidence

- **Registry source lines:** 8801–8929; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt`.
- **Owner goal:** Obtain citable knowledge with explicit provider readiness..
- **Host/route:** `owner/research` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Research / Knowledge; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** VEKL/Obsidian/Notebook/research readiness; source/trust/time; evidence; notebook records; research outcomes.
- **Owner action obligations:** ask through command controller; inspect citations; inspect readiness; request declared notebook mutation; Inspect owner-safe research records; Submit only an advertised exact owner command; Inspect provider evidence, query citations and operations.
- **Endpoint evidence:** POST /v1/commands; GET /v1/runtime/knowledge/status; POST /v1/runtime/knowledge/vekl/query; POST /v1/runtime/knowledge/obsidian/query; GET /v1/runtime/knowledge/notebook/enterprise/recent; GET /v1/runtime/knowledge/notebook/enterprise/{notebook_id}; POST /v1/runtime/knowledge/notebook/consumer/ask; POST /v1/runtime/knowledge/actions/execute; GET /v1/runtime/research/status; POST /v1/runtime/research/search; GET /v1/owner/research; GET /v1/owner/knowledge.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt:159](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt#L159); [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt#L101).

### 74. `van.knowledge.sources` — Private knowledge providers and citations

- **Registry source lines:** 8930–9043; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt`.
- **Owner goal:** Obtain citable knowledge with explicit provider readiness..
- **Host/route:** `owner/knowledge` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Research / Knowledge; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** VEKL/Obsidian/Notebook/research readiness; source/trust/time; evidence; notebook records; research outcomes.
- **Owner action obligations:** ask through command controller; inspect citations; inspect readiness; request declared notebook mutation; Inspect provider evidence, query citations and operations.
- **Endpoint evidence:** GET /v1/owner/knowledge; POST /v1/commands.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt:159](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt#L159); [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt#L101).

### 75. `van.automation.library` — Automation inventory and admission

- **Registry source lines:** 9044–9219; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/owner/OwnerAutomationPlansSection.kt`, `android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt`, `backend/van_gateway/automation/dsl.py`, `backend/van_gateway/automation/owner_api.py`, `backend/van_gateway/automation/worker_runtime.py`.
- **Owner goal:** Inspect bounded automation and disable standing work..
- **Host/route:** `owner/automation` / `none`; **presentation:** `navigation_screen`.
- **New destination:** Automation; **disposition:** Rebuild screen UI; retain or migrate verified capability and navigation intents.
- **Information obligation:** capability/template readiness; workflow mission/run; authority scope; effect receipts; standing intent; repair status; supported closed IR/DSL and deployment requirements; immutable candidate request/artifact/revision; pinned admitted helper/parent manifests and inputs; selected/skipped/refused step receipts; preconditions/independent target predicates; actual provider/worker configuration status.
- **Owner action obligations:** request automation through controller; inspect run/evidence; disable standing intent through supported owner command; Inspect owner-safe automation records; Submit only an advertised exact owner command; Prepare a bounded typed IR candidate, recover the exact artifact and review its declared deployment limitations; Review deterministic supported branches, mappings, preconditions and independent success predicates; Request only an admitted immutable artifact with pinned inputs and inspect actual run/step evidence.
- **Endpoint evidence:** POST /v1/commands; GET /v1/automation/health; GET /v1/automation/templates; GET /v1/automation/capabilities/{capability_id}; POST /v1/automation/standing-intents; POST /v1/automation/standing-intents/{intent_id}/disable; GET /v1/automation/temporal/{workflow_id}; GET /v1/owner/automation; GET /v1/owner/automation/contracts; POST /v1/owner/automation/plans; GET /v1/owner/automation/plans; GET /v1/owner/automation/plans/{artifact_id}; GET /v1/owner/automation/requests/{idempotency_key}; GET /v1/owner/automation/runs/{run_id}.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt:159](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt#L159); [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt#L101); [android/app/src/main/java/com/dial/van/command/owner/OwnerAutomationPlansSection.kt:31](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/owner/OwnerAutomationPlansSection.kt#L31); [backend/van_gateway/automation/owner_api.py:59](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/owner_api.py#L59); [backend/van_gateway/automation/dsl.py:103](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/dsl.py#L103); [backend/van_gateway/automation/dsl.py:138](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/dsl.py#L138); [backend/van_gateway/automation/worker_runtime.py:165](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/worker_runtime.py#L165); [backend/van_gateway/automation/worker_runtime.py:737](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/worker_runtime.py#L737) (plus 1 more).

### 76. `van.automation.intent` — Standing authority and workflow detail

- **Registry source lines:** 9220–9392; **old coverage:** implemented.
- **Source dependency (Rev 1.1):** MAIN_AND_PR93; PR #93-only files: `android/app/src/main/java/com/dial/van/command/owner/OwnerAutomationPlansSection.kt`, `android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt`, `backend/van_gateway/automation/dsl.py`, `backend/van_gateway/automation/owner_api.py`, `backend/van_gateway/automation/worker_runtime.py`.
- **Owner goal:** Inspect bounded automation and disable standing work..
- **Host/route:** `none` / `owner/automation`; **presentation:** `inline_section`.
- **New destination:** Automation; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** capability/template readiness; workflow mission/run; authority scope; effect receipts; standing intent; repair status; supported closed IR/DSL and deployment requirements; immutable candidate request/artifact/revision; pinned admitted helper/parent manifests and inputs; selected/skipped/refused step receipts; preconditions/independent target predicates; actual provider/worker configuration status.
- **Owner action obligations:** request automation through controller; inspect run/evidence; disable standing intent through supported owner command; Inspect owner-safe automation records; Submit only an advertised exact owner command; Prepare a bounded typed IR candidate, recover the exact artifact and review its declared deployment limitations; Review deterministic supported branches, mappings, preconditions and independent success predicates; Request only an admitted immutable artifact with pinned inputs and inspect actual run/step evidence.
- **Endpoint evidence:** GET /v1/owner/automation; POST /v1/commands; GET /v1/owner/automation/contracts; POST /v1/owner/automation/plans; GET /v1/owner/automation/plans; GET /v1/owner/automation/plans/{artifact_id}; GET /v1/owner/automation/requests/{idempotency_key}; GET /v1/owner/automation/runs/{run_id}.
- **Historical gap categories:** `["DEPLOYMENT", "EXTERNAL_PROVIDER", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt:159](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/owner/OwnerServiceRoutes.kt#L159); [android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt:101](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt#L101); [android/app/src/main/java/com/dial/van/command/owner/OwnerAutomationPlansSection.kt:31](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/owner/OwnerAutomationPlansSection.kt#L31); [backend/van_gateway/automation/owner_api.py:59](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/owner_api.py#L59); [backend/van_gateway/automation/dsl.py:103](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/dsl.py#L103); [backend/van_gateway/automation/dsl.py:138](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/dsl.py#L138); [backend/van_gateway/automation/worker_runtime.py:165](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/worker_runtime.py#L165); [backend/van_gateway/automation/worker_runtime.py:737](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/backend/van_gateway/automation/worker_runtime.py#L737) (plus 1 more).

### 77. `van.devices.provision` — Signed provisioning and recovery

- **Registry source lines:** 9393–9622; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Use the app only after a supported readiness journey..
- **Host/route:** `none` / `settings`; **presentation:** `inline_section`.
- **New destination:** Settings / Provisioning; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** permissions; signed provisioning status; paired device; bound hardware identity; overlay/listener/mic/biometric; gateway connectivity; selected Google consent.
- **Owner action obligations:** apply signed provisioning payload; pair/bind; grant Android permissions; run readiness check; re-enroll through supported installer flow.
- **Endpoint evidence:** POST /v1/devices/pair; POST /v1/devices/bootstrap/challenge; POST /v1/devices/bootstrap/attest; POST /v1/devices/tls-certificate; GET /v1/device-binding/status; GET /v1/connectivity/manifest; POST /v1/devices/bootstrap/recover; POST /v1/device-binding/certify; POST /v1/devices/provisioning-status.
- **Historical gap categories:** `["DEPLOYMENT", "RELEASE_PROVISIONING", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/command/settings/SettingsRoute.kt:62](https://github.com/Vanguduza/Van/blob/dfc1557ab99ad8d41cf84714e1bb671e89b045e6/android/app/src/main/java/com/dial/van/command/settings/SettingsRoute.kt#L62).

### 78. `van.share.intake` — Shared Context Intake

- **Registry source lines:** 9623–9710; **old coverage:** partial.
- **Source dependency (Rev 1.1):** MAIN.
- **Owner goal:** Share owner-selected content with VAN..
- **Host/route:** `none` / `none`; **presentation:** `transient_intake_activity`.
- **New destination:** Share Intake; **disposition:** Preserve contextual/host contract; rebuild presentation, do not invent a tab.
- **Information obligation:** shared text/URL metadata; sanitization/classification.
- **Owner action obligations:** enqueue selected context.
- **Endpoint evidence:** POST /v1/context/ingest.
- **Historical gap categories:** `["UI_REDESIGN", "PHYSICAL_ACCEPTANCE"]`.
- **Source references:** [android/app/src/main/java/com/dial/van/share/ShareIntakeActivity.kt:23](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/share/ShareIntakeActivity.kt#L23); [android/app/src/main/java/com/dial/van/share/ShareIntake.kt:1](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/android/app/src/main/java/com/dial/van/share/ShareIntake.kt#L1); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:62](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L62); [docs/design/VAN_PRODUCT_DESIGN_DNA.md:68](https://github.com/Vanguduza/Van/blob/12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af/docs/design/VAN_PRODUCT_DESIGN_DNA.md#L68).

## Audit limitations

The source register documents 78 surfaces and their recorded functional obligations. It does not assert that the 9 October source was merged, that all features operate on the physical owner handset, or that later branch changes have been qualified. Revalidate source hashes, routes, upstream providers and device behaviour during each development unit.

## Additive VAN Next surfaces (Rev 1.2)

New surfaces have their own IDs and tests. They do not count toward the 78 inherited obligations.

| ID | Surface | Zone | Presentation | Requirement | Status |
|---|---|---|---|---|---|
| `van.next.orb-hub` | Home orb quick hub | Home / Orb | `modal_sheet` | VAN-NX-005 | SPEC_ONLY |
| `van.next.trading.chart` | Instrument chart terminal | Trading / Terminal | `navigation_screen` | VAN-NX-009 | SPEC_ONLY |
| `van.next.trading.manual-review` | Manual trade review & approval sheet | Trading / Terminal | `modal_sheet` | VAN-NX-027 | SPEC_ONLY |
| `van.next.trading.exit-sheet` | Position exit / protection sheet | Trading / Positions | `modal_sheet` | VAN-NX-027 | SPEC_ONLY |
| `van.next.trading.add-sheet` | Add to position sheet (manual or automatic trade) | Trading / Positions | `modal_sheet` | VAN-NX-027/031 | SPEC_ONLY |
| `van.next.trading.handover-sheet` | Hand to VAN / take back sheet | Trading / Positions | `modal_sheet` | VAN-NX-031 | SPEC_ONLY |
| `van.next.trading.markets` | Markets & watchlists | Trading / Markets | `navigation_screen` | VAN-NX-011 | SPEC_ONLY |
| `van.next.intel.news` | News briefs | Trading / Intelligence | `navigation_screen` | VAN-NX-013 | SPEC_ONLY |
| `van.next.intel.news-story` | News story brief & trading effect | Trading / Intelligence | `navigation_screen` | VAN-NX-013 | SPEC_ONLY |
| `van.next.intel.calendar` | Economic calendar with event history | Trading / Intelligence | `navigation_screen` | VAN-NX-032 | SPEC_ONLY |
| `van.next.intel.event-history` | Similar past events for a story | Trading / Intelligence | `inline_section` | VAN-NX-032 | SPEC_ONLY |
| `van.next.intel.news-coverage` | News source coverage and health | Trading / Intelligence | `inline_section` | VAN-NX-013 | SPEC_ONLY |
| `van.next.intel.news-live` | News Live (live headlines, armed releases, latency) | Trading / Intelligence | `navigation_screen` | VAN-NX-033 | SPEC_ONLY |
| `van.next.trading.armed-ticket` | Armed news ticket (pre-signed, one tap at release) | Trading / Terminal | `modal_sheet` | VAN-NX-033 | SPEC_ONLY |
| `van.next.trading.behaviour` | Manual trading habits and behaviour flags | Trading / Positions | `inline_section` | VAN-NX-034 | SPEC_ONLY |
| `van.next.trading.pattern-candidates` | Patterns from your trades (candidate strategies) | Trading / Intelligence | `navigation_screen` | VAN-NX-035 | SPEC_ONLY |
| `van.next.intel.keyword-watchlists` | News keyword watchlists | Trading / Intelligence | `modal_sheet` | VAN-NX-037 | SPEC_ONLY |
| `van.next.trading.replay` | Chart replay sandbox | Trading / Terminal | `navigation_screen` | VAN-NX-044 | SPEC_ONLY |
| `van.next.trading.alerts` | Alerts (price, indicator, drawing, keyword) | Trading / Intelligence | `navigation_screen` | VAN-NX-047 | SPEC_ONLY |
| `van.next.trading.screener` | Screener | Trading / Markets | `navigation_screen` | VAN-NX-047 | SPEC_ONLY |
| `van.next.trading.chart-tools` | Indicators, drawings and workspaces sheets | Trading / Terminal | `modal_sheet` | VAN-NX-043 | SPEC_ONLY |
| `van.next.work.flow` | Project task flow graph | Work / Spatial Flow | `navigation_screen` | VAN-NX-015 | SPEC_ONLY |
| `van.next.work.agent-map` | Agent handoff map | Work / Spatial Flow | `navigation_screen` | VAN-NX-016 | SPEC_ONLY |
