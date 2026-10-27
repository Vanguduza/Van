# VAN current frontend screen and feature registry

Current source inventory: **42 features, 105 source functions, 78 screens/hosted surfaces, 483 endpoint declarations and 376 schemas**.

This generated document renders the current source contracts, including gaps and unverified states. It does not declare features complete, qualify live services or authorize a redesigned frontend. No new frontend/prototype before BG-001. Current source features are distinct from the frozen Rev1.18 programme of **93 planned features, 349 owner actions, 324 requirements, 1,610 acceptance identities and 131 units**. The complete planned scope remains in [the frozen package](../../../review-inputs/van-rev115/package/) and its [backend consumption contract](../../../review-inputs/van-rev115/package/contracts/BACKEND_TO_FRONTEND_CONSUMPTION_CONTRACT.md).

Android receives its gateway/Hermes route and trust from signed release/provisioning. Screen designs must not require an owner to enter a host, port, bearer token or certificate. Provisioning, production signing, deployed connectivity and S24 acceptance remain separate qualifications.

Preserve available/empty/loading/stale/refused/unknown/reconciling states. Accepted or requested work is not an applied effect. Keep original operation identity on uncertainty; GET observes rather than dispatches. Final risk recovery never supplies blanket entry permission. An expired original refused before actor observation has null current risk fields; fetch current state before another approval.

Owner-access endpoints and service dependencies are listed separately below. An endpoint declaration or client method does not establish a screen consumer, runtime deployment or handset behavior. Historical qualification fields remain in the JSON inputs; this document does not promote them to current evidence.

## Source inputs

| Registry | SHA-256 |
| --- | --- |
| [owner_features.json](../../../../registries/owner_features.json) | `1202c468c1abb4e73eea760c527a75dcb3ae21bd60644c6a14debdb7c81e4566` |
| [owner_screens.json](../../../../registries/owner_screens.json) | `b2b7f2713f526dd7db63d68e2128eb272d99f83c259bf6c817f43451f07d2309` |
| [owner_endpoints.json](../../../../registries/owner_endpoints.json) | `0b87f6974883cb4ec082eb8f3de1b2bf2f668b237596bff7a39cb2ab46a24004` |
| [owner_endpoint_schemas.json](../../../../registries/owner_endpoint_schemas.json) | `9ce0201aa9b971070380bc129b38592ad2d1da2d23e34c449b4606ebf75ab7b7` |

Regenerate with `python3 tools/rebuild/render_frontend_registry.py --apply`; verify with `--check`.

## Screen index

| ID | Title | Route / host interaction | Feature IDs | Wiring status |
| --- | --- | --- | --- | --- |
| van.home | Home | home / navigation_screen | OF-HOME-001, OF-ATTENTION-001, OF-REMINDER-001, OF-EMBODIMENT-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.attention | Attention | attention / navigation_screen | OF-ATTENTION-001, OF-DECISION-001, OF-APPROVAL-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work | Work | work / navigation_screen | OF-COMMAND-001, OF-MISSION-001, OF-GOOGLE-002, OF-KNOWLEDGE-001, OF-SHARE-001, OF-APPROVAL-001 | EXTERNAL_CONTRACT_OR_ASSET_REQUIRED |
| van.work.mission | Mission deep link | work/missions/{missionId} / navigation_screen | OF-MISSION-001, OF-MISSION-002, OF-DECISION-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.activity | Activity | work/activity / navigation_screen | OF-MISSION-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.artemis | ARTEMIS Android Lab | work/artemis / navigation_screen | OF-ARTEMIS-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.browser | Browser & Automation | work/browser / navigation_screen | OF-AUTOMATION-001, OF-BROWSER-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.browser.tasks | Browser Tasks | work/browser/tasks / navigation_screen | OF-BROWSER-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.browser.escalations | Browser Escalations | work/browser/escalations / navigation_screen | OF-BROWSER-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.browser.sessions | Browser Sessions | work/browser/sessions / navigation_screen | OF-BROWSER-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.browser.policy | Browser Policy | work/browser/policy / navigation_screen | OF-BROWSER-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.trading | Trading | trading / navigation_screen | OF-TRADING-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.trading.overview | Overview | overview / nested_navigation_screen | OF-TRADING-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.trading.positions | Positions | positions / nested_navigation_screen | OF-TRADING-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.trading.positions.detail | Position Detail | positions/{id} / nested_navigation_screen | OF-TRADING-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.trading.potential | Potential | potential / nested_navigation_screen | OF-TRADING-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.trading.history | History & Intelligence | history / nested_navigation_screen | OF-TRADING-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.trading.accounts | Accounts | accounts / nested_navigation_screen | OF-TRADING-003 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.trading.cognition | Cognition | cognition / nested_navigation_screen | OF-TRADING-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.trading.accounts.add | Add Trading Account | accounts/add / nested_navigation_screen | OF-TRADING-003 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.trading.strategies | Strategies | strategies / nested_navigation_screen | OF-TRADING-004 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.trading.halt | Halt Trading | None / modal | OF-TRADING-005 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.memory | Memory | memory / navigation_screen | OF-MEMORY-001, OF-MEMORY-002, OF-MEMORY-003 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.projects | Projects | projects / navigation_screen | OF-PROJECT-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.projects.detail | Project Detail | projects/{projectId} / navigation_screen | OF-PROJECT-001, OF-PROJECT-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.connected | Connected | connected / navigation_screen | OF-GOOGLE-001, OF-GOOGLE-002, OF-KNOWLEDGE-001, OF-SETTINGS-001, OF-DIAGNOSTICS-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.settings | Settings & Devices | settings / navigation_screen | OF-PROVISION-001, OF-SETTINGS-001, OF-DIAGNOSTICS-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.settings.voice | Voice Settings | settings/voice / navigation_screen | OF-VOICE-001, OF-VOICE-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.settings.notifications | Notification Policy | settings/notifications / navigation_screen | OF-NOTIFICATION-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.home | Development Hub | work/dev?project={project} / navigation_screen | OF-DEV-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.plan | Stage Plan | work/dev/{projectId}/plan / navigation_screen | OF-DEV-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.tasks | Development Tasks | work/dev/{projectId}/tasks?view={view} / navigation_screen | OF-DEV-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.graph | Task Graph | work/dev/{projectId}/graph / navigation_screen | OF-DEV-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.task | Task Detail | work/dev/tasks/{taskId} / navigation_screen | OF-DEV-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.agents | Agents | work/dev/agents / navigation_screen | OF-DEV-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.workspaces | Workspaces | work/dev/workspaces / navigation_screen | OF-DEV-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.workspace | Workspace Detail | work/dev/workspaces/{workspaceId} / navigation_screen | OF-DEV-001, OF-DEV-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.evidence | Evidence | work/dev/evidence/{evidenceRef} / navigation_screen | OF-DEV-001, OF-DEV-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.reviews | Development Reviews | work/dev/reviews / navigation_screen | OF-DEV-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.memory | Development Memory | work/dev/memory / navigation_screen | OF-DEV-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.research | Development Research | work/dev/research / navigation_screen | OF-DEV-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.design | Development Design | work/dev/design / navigation_screen | OF-DEV-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.ci | Development Ci | work/dev/ci / navigation_screen | OF-DEV-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.dev.security | Development Security | work/dev/security / navigation_screen | OF-DEV-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.floating | Floating VAN | None / overlay_service | OF-COMMAND-001, OF-OVERLAY-001, OF-SHARE-001, OF-EMBODIMENT-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.voice.turn | Voice Turn | None / inline_section | OF-COMMAND-001, OF-VOICE-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.browser.interactive | Remote Browser | None / native_activity | OF-BROWSER-002, OF-BROWSER-003, OF-BROWSER-004, OF-BROWSER-001 | EXTERNAL_CONTRACT_OR_ASSET_REQUIRED |
| van.permissions | Standing Permissions | settings/permissions / navigation_screen | OF-AUTHORITY-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.autonomy | Autonomy | None / inline_section | OF-AUTHORITY-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.understanding | Understanding & Adaptation | memory/understanding / navigation_screen | OF-LEARNING-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.reminders.manage | Reminder Management | attention/reminders / navigation_screen | OF-REMINDER-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.memory.history | Fact History | None / modal | OF-MEMORY-003 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.approval.detail | Exact-action approval and refusal | None / inline_section | OF-APPROVAL-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.learning.adaptations | Adaptation review and rollback | memory/adaptations / navigation_screen | OF-LEARNING-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.learning.goals | Goals, unresolved threads and learned strategies | memory/goals / navigation_screen | OF-LEARNING-003 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.projects.rationale | Project rationale and decision provenance | projects/{projectId}/rationale / navigation_screen | OF-PROJECT-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.knowledge.research | Research, private knowledge and evidence | owner/research / navigation_screen | OF-KNOWLEDGE-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.automation.library | Automation inventory and admission | owner/automation / navigation_screen | OF-AUTOMATION-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.automation.intent | Standing authority and workflow detail | None / inline_section | OF-AUTOMATION-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.browser.downloads | Downloads, uploads and content policy | None / modal | OF-BROWSER-004 | EXTERNAL_CONTRACT_OR_ASSET_REQUIRED |
| van.devices.provision | Signed provisioning and recovery | None / inline_section | OF-PROVISION-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.diagnostics | Connection health and command correlation | owner/diagnostics / navigation_screen | OF-DIAGNOSTICS-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.onboarding | Device Onboarding | None / native_activity | OF-PROVISION-001, OF-SETTINGS-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.provisioning | Signed Provisioning Intake | None / headless_intake_activity | OF-PROVISION-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.share.intake | Shared Context Intake | None / transient_intake_activity | OF-SHARE-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.memory.privacy | Memory privacy and retention | None / modal | OF-MEMORY-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.knowledge.sources | Private knowledge providers and citations | owner/knowledge / navigation_screen | OF-KNOWLEDGE-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.browser.outcome | Browser task outcome evidence | owner/browser-outcome/{taskId} / navigation_screen | OF-BROWSER-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.trading.tickets | Trading tickets and broker receipts | tickets / nested_navigation_screen | OF-TRADING-005 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.approval.trading-ticket | Exact broker-fill receipt confirmation | None / modal | OF-TRADING-005, OF-APPROVAL-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.attention.decision | Exact owner choice and evidence | None / inline_section | OF-DECISION-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.work.mission-control | Mission dispatch fence and direction receipt | None / inline_section | OF-MISSION-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.memory.record | Exact retained record and erasure scope | None / modal | OF-MEMORY-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.permissions.grant | Exact bounded owner consent | None / inline_section | OF-AUTHORITY-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.automation.plan | Automation candidate, admission and exact run evidence | None / inline_section | OF-AUTOMATION-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.browser.action-plan | Immutable browser effect review and observation | None / modal | OF-BROWSER-003, OF-BROWSER-001 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |
| van.browser.file-provider | Exact owner file destination, admission and result | None / modal | OF-BROWSER-004 | EXTERNAL_CONTRACT_OR_ASSET_REQUIRED |
| van.settings.speaker-profile | Local owner speaker consent, capture and erasure | None / inline_section | OF-VOICE-002 | SOURCE_WIRED_REQUIRES_ACCEPTANCE |

## Screens and hosted surfaces

### van.home — Home

Owner goal: Understand what needs attention and what VAN is doing.

Route: `home`; interaction: `navigation_screen`; domain: `overview`.

Feature IDs: OF-HOME-001, OF-ATTENTION-001, OF-REMINDER-001, OF-EMBODIMENT-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- embodiment/state
- top three attention items/briefing
- active/waiting missions
- trade assessment
- reminders due today
- recent events

**Owner interactions and controls**

- open Attention
- open Work
- open Trading
- retry

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Source reads are bounded independently; failed or timed-out reads retain UNKNOWN/unavailable health and available cached age. Final visual state design and physical navigation acceptance remain pending.

**Current navigation contract**

- {"description": "Fresh launch and an intent delivered to the resident singleTop Activity use the same validated destination resolver. A resident deep link navigates the existing NavHost once instead of recursively restarting the Activity. A pending known destination is saved/restored through recreation and consumed once; foreign/invalid link content is never a raw route or fallback authority. Real process/deep-link behavior remains a handset acceptance case.", "device_execution_status": "UNVERIFIED", "source_citations": [{"file": "android/app/src/main/java/com/dial/van/command/nav/VanNavModel.kt", "line": 65, "ref": "WORKSPACE_PATCH", "review_scope": "Fresh and resident Activity entry share the exact allowlisted destination resolver; foreign links do not fall through to extra-module steering.", "sha256": "187616b948c9dbf6de5a2914f9b49f6ed444bba19b9de841dac1947db695bcd2"}, {"file": "android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt", "line": 150, "ref": "WORKSPACE_PATCH", "review_scope": "Resident singleTop entry steers the existing NavHost once, with saved pending-route recovery, without restarting/redelivering the Activity.", "sha256": "14c746d2024fccf594a99227b2e1685c6f35a7045933a5eb0c69cafc0c28d032"}]}

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/needs-you | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.needsYou |
| GET | /v1/missions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missions |
| GET | /health | DIRECT_OWNER_ROUTE / INGRESS_BEARER | VanGatewayClient.health |
| GET | /v1/attention | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.attention |
| GET | /v1/briefing | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.briefing |
| GET | /v1/reminders | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.reminders |
| GET | /v1/trading/assessment | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingAssessment |

### van.attention — Attention

Owner goal: Triage alerts, approve or refuse decisions.

Route: `attention`; interaction: `navigation_screen`; domain: `attention`.

Feature IDs: OF-ATTENTION-001, OF-DECISION-001, OF-APPROVAL-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- severity list
- source
- decision body
- pending A4 action ID
- quiet-hours banner
- listed stable choices and proposed labels
- exact owner note/revision/expiry
- REFERENCE_ONLY versus RECORDED_EVENT evidence
- immutable answer/recovery identity; grants_action_authority=false

**Owner interactions and controls**

- filter severity
- ack
- snooze one hour
- open DIAL task
- approve/refuse decision
- biometric A4 approve
- Read current attention
- Acknowledge an attention item
- Snooze an attention item for one hour
- Read and answer an exact owner choice with evidence, expiry, note and immutable recovery identity

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Actual typed detail, listed choices, source-labelled references, expiry, immutable answer and recovery are wired. The first authorized answer and its learning fingerprint commit together. A choice is a judgment and does not substitute for cryptographic action approval.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/attention | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.attention |
| GET | /v1/decisions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.decisions |
| POST | /v1/attention/{item_id}/ack | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.attentionAck |
| POST | /v1/attention/{item_id}/snooze | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.attentionSnooze |
| POST | /v1/decisions/{decision_id}/resolve | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.resolveDecision |
| GET | /v1/decisions/{decision_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.decision |
| POST | /v1/decisions/{decision_id}/answer | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.answerDecision |

### van.work — Work

Owner goal: Send text/voice intent and follow execution.

Route: `work`; interaction: `navigation_screen`; domain: `work`.

Feature IDs: OF-COMMAND-001, OF-MISSION-001, OF-GOOGLE-002, OF-KNOWLEDGE-001, OF-SHARE-001, OF-APPROVAL-001.

Wiring: `EXTERNAL_CONTRACT_OR_ASSET_REQUIRED`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- conversation statuses
- A4 pending
- running/waiting missions
- outage reconfirmations

**Owner interactions and controls**

- submit text
- begin voice
- biometric approve
- open browser/ARTEMIS/DIAL/activity
- expand mission timeline
- reconfirm/cancel queued intent
- Cancel this active mission
- Record direction on this existing mission

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Exact prepared signed bodies survive ambiguous transport replies; one controller polls every admitted command to terminal status. RESULT_PENDING is uncertain settlement, not successful execution. Live Hermes connectivity, acoustic assets and physical acceptance remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/commands/{command_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.commandStatus |
| GET | /v1/needs-you | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.needsYou |
| GET | /v1/missions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missions |
| GET | /health | DIRECT_OWNER_ROUTE / INGRESS_BEARER | VanGatewayClient.health |
| GET | /v1/missions/{mission_id}/activity | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missionActivity |
| POST | /v1/missions/{mission_id}/cancel | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.cancelMission |
| POST | /v1/missions/{mission_id}/message | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.messageMission |
| GET | /v1/owner/google/gmail/drafts/{draft_id}/preview | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.googleGmailDraftPreview |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/conversations/{thread_id}/messages | VanGatewayClient.convergenceThreadMessages | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_PAGING_CONSUMER_PENDING | Latest bounded history with total count, has_more and next_before_message_id. Older pages use a message identity scoped to this thread; invalid, deleted and foreign cursors are refused. Equal-time messages are paged exactly once in chronological order. Atomic message/draft/follow-up writes and original projection scope preserve current owner thread state. Late canonical replies may complete archived history without reopening it. Follow-up promotion supplies a fresh owner prompt and never dispatches a command. |

### van.work.mission — Mission deep link

Owner goal: Open the exact mission and its timeline.

Route: `work/missions/{missionId}`; interaction: `navigation_screen`; domain: `work`.

Feature IDs: OF-MISSION-001, OF-MISSION-002, OF-DECISION-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- mission status
- timeline
- current dispatch fence/generation
- exact immutable request hash and direction
- run-bound ordered worker acknowledgement
- existing command/action authority
- already-dispatched work may finish; process_stopped_verified=false

**Owner interactions and controls**

- open timeline
- Cancel this active mission
- Record direction on this existing mission
- Request exact mission pause and independently recover its ordered control receipt
- Request exact mission resume and independently recover its ordered control receipt
- Request exact mission direction and independently recover its ordered control receipt

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Durable pause/resume/direction requests, exact recovery and run-bound ordered Hermes checkpoints are implemented. The fence prevents new gateway/browser/automation effects; it does not prove an already running external OS process stopped. Direction applies at the next admitted worker checkpoint without widening authority.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/missions/{mission_id}/activity | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missionActivity |
| POST | /v1/missions/{mission_id}/cancel | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.cancelMission |
| POST | /v1/missions/{mission_id}/message | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.messageMission |
| GET | /v1/missions/{mission_id}/control | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missionControl |
| GET | /v1/missions/{mission_id}/control/requests/{request_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missionControlRequest |
| POST | /v1/missions/{mission_id}/pause | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.writeMissionControl |
| POST | /v1/missions/{mission_id}/resume | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.writeMissionControl |
| POST | /v1/missions/{mission_id}/direction | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.writeMissionControl |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/missions/{mission_id}/graph | .UNWIRED | CANDIDATE_BACKEND_SOURCE_ANDROID_CONSUMER_PENDING | One durable mission snapshot: stable activity and dependency identities, owner-visible stage evidence, observed executor outcomes, explicit cycles/orphans/conflicting executor claims. Critical path is dependency count only; no invented duration or verified success. Payload limits refuse rather than omit work. |

### van.work.activity — Activity

Owner goal: Inspect received mission/agent events.

Route: `work/activity`; interaction: `navigation_screen`; domain: `work`.

Feature IDs: OF-MISSION-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- device event stream
- event types/payload

**Owner interactions and controls**

- retry/re-enter
- back

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Exact mission selection, lifecycle timeline and evidence pointers are source wired. Physical process recreation and provider evidence acceptance remain unverified.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.events |

### van.work.artemis — ARTEMIS Android Lab

Owner goal: Use the Hermes governed Android testing console.

Route: `work/artemis`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-ARTEMIS-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- external web console devices/tasks/traces

**Owner interactions and controls**

- mint launch
- web controls allowed by console
- back

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Governed Android console/session source is wired. S24 Ultra USB authorization on Windows was owner-reported, not independently observed; no callable Global DIAL/Artemis device channel exists here. Physical Android cases executed: 0; acceptance is deferred until complete wiring/release provisioning.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/artemis/console/session | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.artemisConsoleSession |

### van.work.browser — Browser & Automation

Owner goal: Monitor browser automation tasks and escalations.

Route: `work/browser`; interaction: `navigation_screen`; domain: `browser`.

Feature IDs: OF-AUTOMATION-001, OF-BROWSER-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- browser status
- tasks
- escalations
- policy

**Owner interactions and controls**

- open children

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Bounded browser mutation plans, click/fill results and exact cancellation fencing are implemented. Current native target/profile/producer and private stream/control hosts must be observed. A draft or successful transport does not prove mutation, closure or provider effect; arbitrary unsealed mutation remains refused.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/browser/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserStatus |
| GET | /v1/browser/tasks | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserTasks |
| GET | /v1/browser/escalations | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserEscalations |
| GET | /v1/browser/policy | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserPolicy |

### van.work.browser.tasks — Browser Tasks

Owner goal: Inspect automation state and task evidence.

Route: `work/browser/tasks`; interaction: `navigation_screen`; domain: `browser`.

Feature IDs: OF-BROWSER-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- task list
- evidence

**Owner interactions and controls**

- expand evidence
- back

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Bounded browser mutation plans, click/fill results and exact cancellation fencing are implemented. Current native target/profile/producer and private stream/control hosts must be observed. A draft or successful transport does not prove mutation, closure or provider effect; arbitrary unsealed mutation remains refused.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/browser/tasks | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserTasks |
| GET | /v1/browser/tasks/{task_id}/evidence | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserEvidence |

### van.work.browser.escalations — Browser Escalations

Owner goal: Resolve a browser escalation.

Route: `work/browser/escalations`; interaction: `navigation_screen`; domain: `browser`.

Feature IDs: OF-BROWSER-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- escalation
- linked decision

**Owner interactions and controls**

- approve/refuse
- submit to VAN
- back

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Bounded browser mutation plans, click/fill results and exact cancellation fencing are implemented. Current native target/profile/producer and private stream/control hosts must be observed. A draft or successful transport does not prove mutation, closure or provider effect; arbitrary unsealed mutation remains refused.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/browser/escalations | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserEscalations |
| POST | /v1/decisions/{decision_id}/resolve | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.resolveDecision |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |

### van.work.browser.sessions — Browser Sessions

Owner goal: Inspect remote sessions.

Route: `work/browser/sessions`; interaction: `navigation_screen`; domain: `browser`.

Feature IDs: OF-BROWSER-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- session list derived from browser status

**Owner interactions and controls**

- back

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/browser/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserStatus |

### van.work.browser.policy — Browser Policy

Owner goal: Understand browser policy.

Route: `work/browser/policy`; interaction: `navigation_screen`; domain: `browser`.

Feature IDs: OF-BROWSER-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- policy data

**Owner interactions and controls**

- back

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Bounded browser mutation plans, click/fill results and exact cancellation fencing are implemented. Current native target/profile/producer and private stream/control hosts must be observed. A draft or successful transport does not prove mutation, closure or provider effect; arbitrary unsealed mutation remains refused.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/browser/policy | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserPolicy |

### van.trading — Trading

Owner goal: Inspect portfolio and trade lifecycle.

Route: `trading`; interaction: `navigation_screen`; domain: `trading`.

Feature IDs: OF-TRADING-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- nested overview/positions/potential/history/accounts/strategies/cognition

**Owner interactions and controls**

- navigate trading children
- halt trading

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Trading root hosts actual private nested routes, including ticket records. Legacy position/history extras resolve to concrete destinations; final visual state and physical navigation acceptance remain pending.

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| DELETE /v1/trading/monitors/alerts/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| DELETE /v1/trading/monitors/screen-rules/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| DELETE /v1/trading/monitors/watchlists/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/alerts | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/alerts/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/capabilities | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/operations/{request_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/screen-rules | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/screen-rules/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/watchlists | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/watchlists/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/alerts | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/alerts/{object_id}/pause | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/alerts/{object_id}/restart | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/screen | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/screen-rules | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/screen-rules/{object_id}/run | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/watchlists | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/watchlists/{object_id}/market | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| PUT /v1/trading/monitors/alerts/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| PUT /v1/trading/monitors/screen-rules/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| PUT /v1/trading/monitors/watchlists/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |

### van.trading.overview — Overview

Owner goal: Inspect balances, assessment, active positions and events.

Route: `overview`; interaction: `nested_navigation_screen`; domain: `trading`.

Feature IDs: OF-TRADING-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- portfolio
- assessment
- positions
- events

**Owner interactions and controls**

- refresh
- open positions/potential/history/accounts/strategies/cognition

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Overview reads actual runtime integrity/freshness/halt status and independent per-source failures. Missing time/data/failed chain shows UNKNOWN; refresh and concrete navigation are wired. Final visual state parity and real broker/provider data acceptance remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/portfolio | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPortfolio |
| GET | /v1/trading/assessment | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingAssessment |
| GET | /v1/trading/positions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPositions |
| GET | /v1/trading/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingEvents |
| GET | /v1/trading/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingStatus |

### van.trading.positions — Positions

Owner goal: Review every open position.

Route: `positions`; interaction: `nested_navigation_screen`; domain: `trading`.

Feature IDs: OF-TRADING-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- positions
- protection
- thesis

**Owner interactions and controls**

- refresh
- open position

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Actual nested position/potential/history routes and legacy route arguments are wired. Read-source failure is explicit; final cached/degraded/access visual parity and real broker/pricing data acceptance remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/positions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPositions |

### van.trading.positions.detail — Position Detail

Owner goal: Review a position chart, thesis and execution evidence.

Route: `positions/{id}`; interaction: `nested_navigation_screen`; domain: `trading`.

Feature IDs: OF-TRADING-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- chart
- thesis
- events
- proposal
- risk/evidence

**Owner interactions and controls**

- refresh
- chart pan/zoom/inspect

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Actual nested position/potential/history routes and legacy route arguments are wired. Read-source failure is explicit; final cached/degraded/access visual parity and real broker/pricing data acceptance remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/positions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPositions |
| GET | /v1/trading/trades/{trade_intent_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingTradeDetail |
| GET | /v1/trading/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingEvents |
| GET | /v1/trading/market-state | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingMarketState |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/trading/market/depth-history | .UNWIRED | CANDIDATE_HISTORICAL_SOURCE_READ_ANDROID_CONSUMER_PENDING | Original partial-depth captures by exact native realm/account/symbol scope, revision or as-of boundary. Configured server storage, cumulative byte verification and two original read slots; cancellation cannot reopen capacity before completion. No broker refresh or query-supplied path/policy. Unavailable/corrupt/over-budget sources refuse and missing captures remain null. Complete original versioned capture/receipt retained; no current freshness, normalized price, complete book, provider right or frontend implementation is claimed. |
| DELETE /v1/trading/charts/workspaces/{workspace_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| GET /v1/trading/charts/capabilities | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| GET /v1/trading/charts/operations/{request_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| GET /v1/trading/charts/workspaces | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| GET /v1/trading/charts/workspaces/{workspace_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| GET /v1/trading/charts/workspaces/{workspace_id}/revisions | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| POST /v1/trading/charts/workspaces | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| POST /v1/trading/charts/workspaces/{workspace_id}/restore | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| PUT /v1/trading/charts/workspaces/{workspace_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| DELETE /v1/trading/monitors/alerts/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| DELETE /v1/trading/monitors/screen-rules/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| DELETE /v1/trading/monitors/watchlists/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/alerts | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/alerts/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/capabilities | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/operations/{request_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/screen-rules | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/screen-rules/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/watchlists | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/watchlists/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/alerts | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/alerts/{object_id}/pause | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/alerts/{object_id}/restart | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/screen | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/screen-rules | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/screen-rules/{object_id}/run | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/watchlists | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/watchlists/{object_id}/market | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| PUT /v1/trading/monitors/alerts/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| PUT /v1/trading/monitors/screen-rules/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| PUT /v1/trading/monitors/watchlists/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |

### van.trading.potential — Potential

Owner goal: Inspect candidate ideas and admission blockers.

Route: `potential`; interaction: `nested_navigation_screen`; domain: `trading`.

Feature IDs: OF-TRADING-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- candidate theses
- readiness

**Owner interactions and controls**

- refresh

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Actual nested position/potential/history routes and legacy route arguments are wired. Read-source failure is explicit; final cached/degraded/access visual parity and real broker/pricing data acceptance remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/potential | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPotential |

### van.trading.history — History & Intelligence

Owner goal: Review outcomes and decision quality.

Route: `history`; interaction: `nested_navigation_screen`; domain: `trading`.

Feature IDs: OF-TRADING-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- history
- intelligence filters

**Owner interactions and controls**

- refresh
- filter

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Actual nested position/potential/history routes and legacy route arguments are wired. Read-source failure is explicit; final cached/degraded/access visual parity and real broker/pricing data acceptance remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/history | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingHistory |

### van.trading.accounts — Accounts

Owner goal: Review account safety, health and balances.

Route: `accounts`; interaction: `nested_navigation_screen`; domain: `trading`.

Feature IDs: OF-TRADING-003.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- account mode/safety/connection
- balances
- kill switch
- sync age

**Owner interactions and controls**

- refresh
- add

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Account projections and exact gated account controls are wired. Final scoped access/offline/stale visual parity and actual broker receipt/credential admission acceptance remain pending; credentials stay on the trading host.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/accounts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingAccounts |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/trading/accounts | VanGatewayClient.tradingAccounts | CANDIDATE_NATIVE_FACTS_ANDROID_DTO_SOURCE_TESTED | native_account_observation preserves current physical identity, original equity/balance/credit, credit-excluded risk valuation or explicit unknown/liability, source/read clocks and original snapshot references independently of cash-history coverage. Invalid evidence or changed profiles withhold financial values. Exact Kotlin decimal text and 64-bit identity/clock parsing; existing AccountCard DTO only, no new UI. Response schema: trading/vati/contracts/schemas/native_account_observation.schema.json |
| GET /v1/trading/portfolio | VanGatewayClient.tradingPortfolio | CANDIDATE_NATIVE_FACTS_ANDROID_DTO_SOURCE_TESTED | native_account_observation preserves current physical identity, original equity/balance/credit, credit-excluded risk valuation or explicit unknown/liability, source/read clocks and original snapshot references independently of cash-history coverage. Invalid evidence or changed profiles withhold financial values. Exact Kotlin decimal text and 64-bit identity/clock parsing; existing AccountCard DTO only, no new UI. Response schema: trading/vati/contracts/schemas/native_account_observation.schema.json |
| GET /v1/trading/funding/drafts/{request_id} | .UNWIRED | CANDIDATE_UNAPPROVED_FUNDING_DRAFT_ANDROID_CONSUMER_PENDING | Immutable exact owner/request funding inputs and original committed receipts in the existing VATI ledger. Current payment eligibility remains NOT_ADMITTED. Quote/beneficiary digests are unverified references; strict wire, retention, original-request, expiry and capacity refusal apply. Bound request proof stores a draft and does not authorize a payment. Existing provider admission and unsupported funding states remain required. No frontend implementation or native financial effect is claimed. |
| GET /v1/trading/funding/drafts/{request_id}/receipt | .UNWIRED | CANDIDATE_UNAPPROVED_FUNDING_DRAFT_ANDROID_CONSUMER_PENDING | Immutable exact owner/request funding inputs and original committed receipts in the existing VATI ledger. Current payment eligibility remains NOT_ADMITTED. Quote/beneficiary digests are unverified references; strict wire, retention, original-request, expiry and capacity refusal apply. Bound request proof stores a draft and does not authorize a payment. Existing provider admission and unsupported funding states remain required. No frontend implementation or native financial effect is claimed. |
| POST /v1/trading/funding/drafts | .UNWIRED | CANDIDATE_UNAPPROVED_FUNDING_DRAFT_ANDROID_CONSUMER_PENDING | Immutable exact owner/request funding inputs and original committed receipts in the existing VATI ledger. Current payment eligibility remains NOT_ADMITTED. Quote/beneficiary digests are unverified references; strict wire, retention, original-request, expiry and capacity refusal apply. Bound request proof stores a draft and does not authorize a payment. Existing provider admission and unsupported funding states remain required. No frontend implementation or native financial effect is claimed. |

### van.trading.cognition — Cognition

Owner goal: Inspect VAN cognition status.

Route: `cognition`; interaction: `nested_navigation_screen`; domain: `trading`.

Feature IDs: OF-TRADING-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- cognition ledger

**Owner interactions and controls**

- refresh

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Strategy/runtime certificate readback is supplied; absent or obsolete evidence remains unavailable. Final visual state parity and live strategy/certificate qualification remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/cognition | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingCognition |

### van.trading.accounts.add — Add Trading Account

Owner goal: Link a broker/paper account using owner approval.

Route: `accounts/add`; interaction: `nested_navigation_screen`; domain: `trading`.

Feature IDs: OF-TRADING-003.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- broker forms
- validation/status

**Owner interactions and controls**

- submit account actions
- get challenge
- biometric sign
- Done

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Account projections and exact gated account controls are wired. Final scoped access/offline/stale visual parity and actual broker receipt/credential admission acceptance remain pending; credentials stay on the trading host.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/trading/accounts/challenge | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingAccountChallenge |
| POST | /v1/trading/accounts/action | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingAccountAction |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/trading/accounts/operations/{operation_id} | VanGatewayClient.tradingAccountOperation | CANDIDATE_SOURCE_ANDROID_REPAIR_NATIVE_ACCEPTANCE_PENDING | Native journal for account_upsert/account_credentials/account_remove/mt5_ea_issue_key; original non-secret operation identity survives Android restart; absence and incomplete effects stay UNKNOWN |
| GET /v1/trading/accounts/catalog | VanGatewayClient.tradingAccountCatalog | CANDIDATE_SOURCE_ANDROID_REPAIR_NATIVE_ACCEPTANCE_PENDING | Exact existing action fields, credential-key names, approval and original-result capabilities. Partial account edits preserve omitted settings. Generic edits require native resolved before/after review bound to the biometric proof and checked again by the native writer. |
| GET /v1/trading/accounts | VanGatewayClient.tradingAccounts | CANDIDATE_NATIVE_FACTS_ANDROID_DTO_SOURCE_TESTED | native_account_observation preserves current physical identity, original equity/balance/credit, credit-excluded risk valuation or explicit unknown/liability, source/read clocks and original snapshot references independently of cash-history coverage. Invalid evidence or changed profiles withhold financial values. Exact Kotlin decimal text and 64-bit identity/clock parsing; existing AccountCard DTO only, no new UI. Response schema: trading/vati/contracts/schemas/native_account_observation.schema.json |
| GET /v1/trading/portfolio | VanGatewayClient.tradingPortfolio | CANDIDATE_NATIVE_FACTS_ANDROID_DTO_SOURCE_TESTED | native_account_observation preserves current physical identity, original equity/balance/credit, credit-excluded risk valuation or explicit unknown/liability, source/read clocks and original snapshot references independently of cash-history coverage. Invalid evidence or changed profiles withhold financial values. Exact Kotlin decimal text and 64-bit identity/clock parsing; existing AccountCard DTO only, no new UI. Response schema: trading/vati/contracts/schemas/native_account_observation.schema.json |

### van.trading.strategies — Strategies

Owner goal: Review and approve strategy promotion.

Route: `strategies`; interaction: `nested_navigation_screen`; domain: `trading`.

Feature IDs: OF-TRADING-004.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- candidates
- certificate/evidence
- target states/status

**Owner interactions and controls**

- authority grant
- challenge
- biometric proof
- promote
- refresh

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Strategy/runtime certificate readback is supplied; absent or obsolete evidence remains unavailable. Final visual state parity and live strategy/certificate qualification remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/strategies/promotion-candidates | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPromotionCandidates |
| POST | /v1/trading/strategies/promotion-challenge | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPromotionChallenge |
| POST | /v1/trading/strategies/promote | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPromoteStrategy |

### van.trading.halt — Halt Trading

Owner goal: Stop new trading activity across accounts with two approvals.

Route: `null`; interaction: `modal`; domain: `trading`.

Feature IDs: OF-TRADING-005.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- action digest
- authority status
- pending gateway A4
- command outcome

**Owner interactions and controls**

- open sheet
- sign authority grant
- submit halt command
- approve gateway A4
- dismiss

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Actual ticket read UI and exact broker-fill confirmation sheet are wired through fresh ticket authority plus A4 biometric command; an independent chained-ledger verifier settles the receipt. Owner halt has current status readback. Confirmation records a broker receipt and never executes an order; credentials/execution/provider acceptance remain external.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/commands/{command_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.commandStatus |
| GET | /v1/trading/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingStatus |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/trading/runtime/recovery/catalog | VanGatewayClient.tradingRuntimeRecoveryCatalog | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_CONSUMER_PENDING | Single-session and multi-instrument account kill clear, loss-scope reset and drawdown rebaseline. The native account actor publishes its opaque session identity; symbol/contract configuration and lease changes invalidate an old review. Original approval ID and durable public proof survive uncertain dispatch. Reads never dispatch. APPLIED is not blanket entry authority; all other holds, unresolved original orders, profile and final native fences remain. |
| GET /v1/trading/runtime/recovery/operations/{operation_id} | VanGatewayClient.tradingRuntimeRecoveryOperation | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_CONSUMER_PENDING | Single-session and multi-instrument account kill clear, loss-scope reset and drawdown rebaseline. The native account actor publishes its opaque session identity; symbol/contract configuration and lease changes invalidate an old review. Original approval ID and durable public proof survive uncertain dispatch. Reads never dispatch. APPLIED is not blanket entry authority; all other holds, unresolved original orders, profile and final native fences remain. |
| GET /v1/trading/runtime/recovery/state | VanGatewayClient.tradingRuntimeRecoveryState | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_CONSUMER_PENDING | Single-session and multi-instrument account kill clear, loss-scope reset and drawdown rebaseline. The native account actor publishes its opaque session identity; symbol/contract configuration and lease changes invalidate an old review. Original approval ID and durable public proof survive uncertain dispatch. Reads never dispatch. APPLIED is not blanket entry authority; all other holds, unresolved original orders, profile and final native fences remain. |
| POST /v1/trading/runtime/recovery/challenge | VanGatewayClient.tradingRuntimeRecoveryChallenge | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_CONSUMER_PENDING | Single-session and multi-instrument account kill clear, loss-scope reset and drawdown rebaseline. The native account actor publishes its opaque session identity; symbol/contract configuration and lease changes invalidate an old review. Original approval ID and durable public proof survive uncertain dispatch. Reads never dispatch. APPLIED is not blanket entry authority; all other holds, unresolved original orders, profile and final native fences remain. |
| POST /v1/trading/runtime/recovery/request | VanGatewayClient.tradingRuntimeRecoveryRequest | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_CONSUMER_PENDING | Single-session and multi-instrument account kill clear, loss-scope reset and drawdown rebaseline. The native account actor publishes its opaque session identity; symbol/contract configuration and lease changes invalidate an old review. Original approval ID and durable public proof survive uncertain dispatch. Reads never dispatch. APPLIED is not blanket entry authority; all other holds, unresolved original orders, profile and final native fences remain. |

### van.memory — Memory

Owner goal: See what VAN believes and add/correct/forget it.

Route: `memory`; interaction: `navigation_screen`; domain: `memory`.

Feature IDs: OF-MEMORY-001, OF-MEMORY-002, OF-MEMORY-003.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- facts by scope
- decisions/preferences
- conflicts
- stale/expiring facts
- recent changes
- authority/confidence

**Owner interactions and controls**

- remember free text/structured
- correct
- forget
- choose conflict value
- Remember or correct a scoped owner fact
- Withdraw a fact while retaining its history
- Inspect a fact revision history
- Inspect conflict sides and state an owner correction

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Per-record inspection, bounded screened export and exact immutable A4 erasure are supplied for all twelve forgettable stores. New/changed dependencies refuse stale approval; independent readback preserves unrelated rows. Direct DELETE remains refused. Physical privacy, biometric and restart acceptance remains unverified.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/context/export | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextExport |
| GET | /v1/context/conflicts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextConflicts |
| POST | /v1/context/facts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.stateOwnerFact |
| DELETE | /v1/context/facts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.forgetOwnerFact |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/context/history | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextHistory |

### van.projects — Projects

Owner goal: Find project phase, health and blockers.

Route: `projects`; interaction: `navigation_screen`; domain: `projects`.

Feature IDs: OF-PROJECT-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- project ID
- health
- phase
- running/blocker counts

**Owner interactions and controls**

- open project

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Project truth, work, attention, decisions and context preserve independent source failures and read timestamps. Missing health/phase stays UNKNOWN; mission controls, next actions and memory provenance have concrete navigation.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/projects | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.projects |
| GET | /v1/missions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missions |
| GET | /v1/attention | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.attention |
| GET | /v1/context/export | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextExport |
| GET | /v1/projects/{project_id}/truth | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.projectTruth |

### van.projects.detail — Project Detail

Owner goal: Understand one project and ask VAN about it.

Route: `projects/{projectId}`; interaction: `navigation_screen`; domain: `projects`.

Feature IDs: OF-PROJECT-001, OF-PROJECT-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- truth SHA/repo SHA
- current work
- blockers
- recent changes
- decisions
- next actions
- context

**Owner interactions and controls**

- ask VAN
- open DIAL hub
- Open rationale independently from the main project read

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Project truth, work, attention, decisions and context preserve independent source failures and read timestamps. Missing health/phase stays UNKNOWN; mission controls, next actions and memory provenance have concrete navigation.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/projects/{project_id}/truth | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.projectTruth |
| GET | /v1/missions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missions |
| GET | /v1/attention | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.attention |
| GET | /v1/decisions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.decisions |
| GET | /v1/context/export | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextExport |
| GET | /v1/dial-dev/projects | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.projects |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |

### van.connected — Connected

Owner goal: Inspect provider readiness and revoke Google.

Route: `connected`; interaction: `navigation_screen`; domain: `connections`.

Feature IDs: OF-GOOGLE-001, OF-GOOGLE-002, OF-KNOWLEDGE-001, OF-SETTINGS-001, OF-DIAGNOSTICS-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- Hermes health
- knowledge readiness
- Google credential planes
- DIAL fabric

**Owner interactions and controls**

- revoke Google with confirmation
- retry

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Actual Google connection status, plane and capability evidence are read independently. Workspace-only revoke requires receipt plus fresh readback; owner registration alone does not imply connected provider credentials. Live provider binding and revoke acceptance remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /health | DIRECT_OWNER_ROUTE / INGRESS_BEARER | VanGatewayClient.health |
| GET | /v1/google/planes | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.googlePlanes |
| POST | /v1/google/owner-revoke | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.googleOwnerRevoke |
| GET | /v1/dial-dev/infrastructure | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.infrastructure |
| GET | /v1/google/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.googleStatus |

### van.settings — Settings & Devices

Owner goal: Manage device capabilities and diagnose unavailable features.

Route: `settings`; interaction: `navigation_screen`; domain: `settings`.

Feature IDs: OF-PROVISION-001, OF-SETTINGS-001, OF-DIAGNOSTICS-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- local paired/hardware-bound state
- display awareness
- renderer status
- device/gateway diagnostics

**Owner interactions and controls**

- floating start/stop
- Android accessibility settings
- restore subsystem
- accept asset with biometric
- debug candidate preview
- open voice/notifications

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Automatic readiness, source diagnostics, Android permission navigation and supported installer recovery are wired. Operator release/transport binding and OS/device acceptance remain external; no owner connection configuration fields are required.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/degraded | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.degraded |
| POST | /v1/visual/acceptance | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.recordVisualAcceptance |

### van.settings.voice — Voice Settings

Owner goal: Teach personal speech corrections and pin names.

Route: `settings/voice`; interaction: `navigation_screen`; domain: `voice`.

Feature IDs: OF-VOICE-001, OF-VOICE-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- correction fields
- pinned term fields
- context selector
- generic speaker model readiness separate from authenticated profile presence
- current full owner/device/hardware/approval binding
- dedicated local consent operation/revision/model/freshness
- current clip phrase/index/energy quality/progress
- encrypted normalized embedding and retained consent metadata; no stored raw PCM
- inconclusive stale/unbound speaker evidence; no action authority
- exact offline erasure using genuine local keys and absence readback

**Owner interactions and controls**

- recordCorrection
- pinTerm
- choose context
- back
- Enroll or replace the exact device-local owner profile using dedicated biometric consent and three actual microphone clips
- Read local profile/model readiness and permit revocable similarity evidence only for the exact fresh current owner binding
- Erase precisely the retained encrypted profile after dedicated biometric consent, including when the backend is unreachable

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Generic APK acoustic delivery, exact integrity/atomic installation, selected local recognition and actual EnergyVadGate endpointing are source implemented. Dedicated actual owner enrollment/replace/readiness/erasure source is supplied; no owner profile or recording has been fabricated. Runtime readiness is observable and separate from acoustic accuracy: native constructors/decode smoke do not qualify wake/ASR/speaker performance. Physical acoustic, model performance and signed owner-release qualification remain pending.

### van.settings.notifications — Notification Policy

Owner goal: Choose apps VAN reads and quiet hours.

Route: `settings/notifications`; interaction: `navigation_screen`; domain: `notifications`.

Feature IDs: OF-NOTIFICATION-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- explicit decided package policies
- quiet config

**Owner interactions and controls**

- toggle quiet
- start/end +1h
- normal/priority/mute
- mute package by name
- Review and change explicit policy for apps actually observed

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Observed applications and explicit encrypted device-local policy remain distinct; muted applications stay visible. OS listener consent, real delivery and physical acceptance remain pending. No cross-device policy-sync contract is supplied.

### van.work.dev.home — Development Hub

Owner goal: Inspect DIAL projects and current development work and act only against the live projection.

Route: `work/dev?project={project}`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- projects and current development work

**Owner interactions and controls**

- project switch
- open child

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/projects | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.projects |
| GET | /v1/dial-dev/projects/{project_id}/home | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.home |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/dial-dev/actions/{action_id} | VanGatewayClient.dialDev.action/reconcileAction | CANDIDATE_BACKEND_AND_EXISTING_ANDROID_CONTROL_RECOVERY_SOURCE_NATIVE_ACCEPTANCE_PENDING | Exact original action read beyond recent lists; encrypted prepared request retains parameters/revision/key across restart. Reads never POST. Changed instructions, malformed/foreign/stale facts and uncertain native control errors cannot replace an original. APPLIED is a control outcome, not task success. |

### van.work.dev.plan — Stage Plan

Owner goal: Inspect DIAL stage/phase plan and act only against the live projection.

Route: `work/dev/{projectId}/plan`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- stage/phase plan

**Owner interactions and controls**

- refresh
- open task

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/projects/{project_id}/stage-plan | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.stagePlan |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/dial-dev/actions/{action_id} | VanGatewayClient.dialDev.action/reconcileAction | CANDIDATE_BACKEND_AND_EXISTING_ANDROID_CONTROL_RECOVERY_SOURCE_NATIVE_ACCEPTANCE_PENDING | Exact original action read beyond recent lists; encrypted prepared request retains parameters/revision/key across restart. Reads never POST. Changed instructions, malformed/foreign/stale facts and uncertain native control errors cannot replace an original. APPLIED is a control outcome, not task success. |

### van.work.dev.tasks — Development Tasks

Owner goal: Inspect DIAL task list and selected view and act only against the live projection.

Route: `work/dev/{projectId}/tasks?view={view}`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- task list and selected view

**Owner interactions and controls**

- choose view
- open task

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/projects/{project_id}/tasks | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.tasks |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

### van.work.dev.graph — Task Graph

Owner goal: Inspect DIAL dependency graph and act only against the live projection.

Route: `work/dev/{projectId}/graph`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- dependency graph

**Owner interactions and controls**

- open task

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/projects/{project_id}/graph | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.graph |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

### van.work.dev.task — Task Detail

Owner goal: Inspect DIAL live task state, decisions/evidence and act only against the live projection.

Route: `work/dev/tasks/{taskId}`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- live task state, decisions/evidence

**Owner interactions and controls**

- steer
- pause safely
- resume
- checkpoint
- review
- revoke
- resolve owner decision

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Action statuses and keys are remember state, so an in-flight UI status is not restored across process death.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/tasks/{task_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.task |
| POST | /v1/dial-dev/actions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.submitAction |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/dial-dev/actions/{action_id} | VanGatewayClient.dialDev.action/reconcileAction | CANDIDATE_BACKEND_AND_EXISTING_ANDROID_CONTROL_RECOVERY_SOURCE_NATIVE_ACCEPTANCE_PENDING | Exact original action read beyond recent lists; encrypted prepared request retains parameters/revision/key across restart. Reads never POST. Changed instructions, malformed/foreign/stale facts and uncertain native control errors cannot replace an original. APPLIED is a control outcome, not task success. |

### van.work.dev.agents — Agents

Owner goal: Inspect DIAL agent registry/status and act only against the live projection.

Route: `work/dev/agents`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- agent registry/status

**Owner interactions and controls**

- open related task

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/agents | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.agents |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

### van.work.dev.workspaces — Workspaces

Owner goal: Inspect DIAL workspace list and act only against the live projection.

Route: `work/dev/workspaces`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- workspace list

**Owner interactions and controls**

- open workspace

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/workspaces | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.workspaces |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

### van.work.dev.workspace — Workspace Detail

Owner goal: Inspect DIAL workspace, bounded diff and terminal tail and act only against the live projection.

Route: `work/dev/workspaces/{workspaceId}`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001, OF-DEV-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- workspace, bounded diff and terminal tail

**Owner interactions and controls**

- read diff/tail
- typed task controls

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Action statuses and keys are remember state, so an in-flight UI status is not restored across process death.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/workspaces/{workspace_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.workspace |
| GET | /v1/dial-dev/workspaces/{workspace_id}/diff | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.workspaceDiff |
| GET | /v1/dial-dev/workspaces/{workspace_id}/terminal-tail | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.workspaceTerminalTail |
| POST | /v1/dial-dev/actions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.submitAction |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/dial-dev/actions/{action_id} | VanGatewayClient.dialDev.action/reconcileAction | CANDIDATE_BACKEND_AND_EXISTING_ANDROID_CONTROL_RECOVERY_SOURCE_NATIVE_ACCEPTANCE_PENDING | Exact original action read beyond recent lists; encrypted prepared request retains parameters/revision/key across restart. Reads never POST. Changed instructions, malformed/foreign/stale facts and uncertain native control errors cannot replace an original. APPLIED is a control outcome, not task success. |

### van.work.dev.evidence — Evidence

Owner goal: Inspect DIAL evidence projection and act only against the live projection.

Route: `work/dev/evidence/{evidenceRef}`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001, OF-DEV-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- evidence projection

**Owner interactions and controls**

- open admitted evidence links

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/evidence/{evidence_ref} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.evidence |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

### van.work.dev.reviews — Development Reviews

Owner goal: Inspect authoritative DIAL reviews projection.

Route: `work/dev/reviews`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- reviews projection

**Owner interactions and controls**

- refresh
- open task/evidence where offered

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/reviews | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.section.reviews |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

### van.work.dev.memory — Development Memory

Owner goal: Inspect authoritative DIAL memory projection.

Route: `work/dev/memory`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- memory projection

**Owner interactions and controls**

- refresh
- open task/evidence where offered

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/memory | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.section.memory |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

### van.work.dev.research — Development Research

Owner goal: Inspect authoritative DIAL research projection.

Route: `work/dev/research`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- research projection

**Owner interactions and controls**

- refresh
- open task/evidence where offered

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/research | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.section.research |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

### van.work.dev.design — Development Design

Owner goal: Inspect authoritative DIAL design projection.

Route: `work/dev/design`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- design projection

**Owner interactions and controls**

- refresh
- open task/evidence where offered

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/design | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.section.design |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

### van.work.dev.ci — Development Ci

Owner goal: Inspect authoritative DIAL ci projection.

Route: `work/dev/ci`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- ci projection

**Owner interactions and controls**

- refresh
- open task/evidence where offered

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/ci | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.section.ci |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

### van.work.dev.security — Development Security

Owner goal: Inspect authoritative DIAL security projection.

Route: `work/dev/security`; interaction: `navigation_screen`; domain: `development`.

Feature IDs: OF-DEV-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- security projection

**Owner interactions and controls**

- refresh
- open task/evidence where offered

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/security | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.section.security |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |

### van.floating — Floating VAN

Owner goal: Keep VAN available over other apps.

Route: `null`; interaction: `overlay_service`; domain: `overlay`.

Feature IDs: OF-COMMAND-001, OF-OVERLAY-001, OF-SHARE-001, OF-EMBODIMENT-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- embodiment/chrome
- conversation
- trade ledger

**Owner interactions and controls**

- drag/dock/minimize/dismiss
- chat
- voice
- open owner routes
- refresh trades

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Shared controller command polling survives outside the Work composition; shared voice and trading navigation are wired. Overlay has no embedded attention queue or A4 confirmation; those actions navigate to Command Centre. Final overlay gesture/board/Rive redesign and Android OS permission acceptance remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/trading/trades | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingTrades |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/conversations/{thread_id}/messages | VanGatewayClient.convergenceThreadMessages | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_PAGING_CONSUMER_PENDING | Latest bounded history with total count, has_more and next_before_message_id. Older pages use a message identity scoped to this thread; invalid, deleted and foreign cursors are refused. Equal-time messages are paged exactly once in chronological order. Atomic message/draft/follow-up writes and original projection scope preserve current owner thread state. Late canonical replies may complete archived history without reopening it. Follow-up promotion supplies a fresh owner prompt and never dispatches a command. |

### van.voice.turn — Voice Turn

Owner goal: Speak, review transcription and interrupt safely.

Route: `null`; interaction: `inline_section`; domain: `voice`.

Feature IDs: OF-COMMAND-001, OF-VOICE-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- recognition result/state currently produced in app only
- actual generic bundle/install/runtime readiness
- selected recognition/TTS engine and offline fallback
- actual EnergyVadGate endpointing for local PCM turns
- permission/no-speech/timeout/cancel/late-final states
- declared assets are separate from prepared usable models and acoustic accuracy
- actual owner speaker enrollment controls available; owner profile absent until real capture
- generic models grant no owner identity or action authority

**Owner interactions and controls**

- beginOwnerTurn
- Cancel unsubmitted speech and reject late recognition results
- Keep the same owner envelope and acknowledgment boundary on authenticated POST/SSE fallback
- Use automatically installed generic local acoustic assets and retain honest engine/fallback readiness without phone configuration
- End the selected local Sherpa recognition turn on actual EnergyVadGate speech/silence or explicit bounded no-speech/maximum-duration state

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Generic APK acoustic delivery, exact integrity/atomic installation, selected local recognition and actual EnergyVadGate endpointing are source implemented. Dedicated actual owner enrollment/replace/readiness/erasure source is supplied; no owner profile or recording has been fabricated. Runtime readiness is observable and separate from acoustic accuracy: native constructors/decode smoke do not qualify wake/ASR/speaker performance. Physical acoustic, model performance and signed owner-release qualification remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| POST | /v1/session/messages | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.sessionUpstream |
| GET | /v1/session/events-stream | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.sessionDownstream |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/conversations/{thread_id}/messages | VanGatewayClient.convergenceThreadMessages | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_PAGING_CONSUMER_PENDING | Latest bounded history with total count, has_more and next_before_message_id. Older pages use a message identity scoped to this thread; invalid, deleted and foreign cursors are refused. Equal-time messages are paged exactly once in chronological order. Atomic message/draft/follow-up writes and original projection scope preserve current owner thread state. Late canonical replies may complete archived history without reopening it. Follow-up promotion supplies a fresh owner prompt and never dispatches a command. |

### van.browser.interactive — Remote Browser

Owner goal: Browse under an owner device lease.

Route: `null`; interaction: `native_activity`; domain: `browser`.

Feature IDs: OF-BROWSER-002, OF-BROWSER-003, OF-BROWSER-004, OF-BROWSER-001.

Wiring: `EXTERNAL_CONTRACT_OR_ASSET_REQUIRED`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- remote rendered page
- snapshot/link state
- omnibox/tabs/window state
- owned download/chooser identifiers and current target
- producer and media epoch
- filename/type/size/hash and safe origin metadata
- pending/failed/available byte effect status
- host deletion acknowledgement
- explicit clipboard effect receipt
- current native target/hostname/profile/producer epoch
- owner-prepared task/immutable plan
- exact effect parameters/observed predicates
- claimed/uncertain/observed result without re-actuation
- foreground A3 task preparation
- fresh native biometric A4 plan approval
- current profile_mutation_permitted/gateway_authorized_only posture
- exact click/fill parameters/step observations
- cancellation fence/retained result
- exact file hash/size/type/producer epoch
- safe inert local preview
- bounded source-labelled native analysis
- exact operation result/recovery
- external provider bound/executable/qualified status; unbound imports unavailable
- immutable provider request/idempotency key/digest/deadline
- current exact provider/owner/project destination
- fresh native A4 challenge and approval state
- actual one-use provider claim and independent persisted-byte receipt
- explicit OBSERVED_EXTERNAL_EFFECT versus STILL_UNKNOWN observation; original canonical outcome/fence retained
- UNKNOWN remains read-only; no content execution or truth promotion

**Owner interactions and controls**

- inspect tabs/target/events
- owner touch and keyboard
- pause/resume/close
- take control
- delegate current control to an existing mission
- review downloads and explicit save/upload/copy/paste
- Confirm the current browser viewport
- Pause this browser session
- Request remote browser closure and distinguish local disconnect
- Read current target/tab inventory and safe session event history
- Resume the exact admitted session with fresh readback
- Take control only after matching fresh owner lease and generation
- Delegate the exact current lease to an existing mission and require authoritative readback
- Review actual owned-session download records
- Remove an eligible host download record and confirm exact DELETED readback
- Save verified browser download bytes through the Android Storage Access Framework
- Choose and upload a bounded phone document only for an explicit current browser chooser
- Explicitly copy browser selection or paste phone clipboard under current owner control
- Prepare an actual browser task, review exact click/fill effects and observe the sealed result without re-actuation
- Inspect native file analysis and exact import operation readbacks, with bound hash/epoch and provider limits
- Open independently verified selected bytes in VAN's bounded inert native viewer
- Read current archive/candidate provider capability, exact admitted destination and unavailable/refused states
- Prepare and independently recover the exact immutable file/destination request before any provider effect
- Approve the exact file request with fresh native A4 and inspect separately admitted provider claim and persisted-byte evidence
- Explicitly check an already claimed external byte receipt after an uncertain effect without resubmitting or changing the original outcome

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Bounded browser mutation plans, click/fill results and exact cancellation fencing are implemented. Current native target/profile/producer and private stream/control hosts must be observed. A draft or successful transport does not prove mutation, closure or provider effect; arbitrary unsealed mutation remains refused.
- Native file inspection, inert preview, bounded analysis and exact readback are wired. Owner provider catalog/draft/recovery, canonical native A4 admission, separate attested mTLS claim/introspection and independently verified byte receipts are implemented. The proposed Oracle/VEKL production target remains unbound/unqualified; defaults are UNAVAILABLE and current capability/bindings must be supplied before owner preparation/execution. Host cleanup and actual phone byte/provider effects still require independent acceptance.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/browser/interactive-sessions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserCreate |
| GET | /v1/browser/interactive-sessions/{session_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserRead |
| POST | /v1/browser/interactive-sessions/{session_id}/stream-grant | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserStreamGrant |
| POST | /v1/browser/interactive-sessions/{session_id}/take-control | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserTakeControl |
| POST | /v1/browser/interactive-sessions/{session_id}/heartbeat | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserHeartbeat |
| POST | /v1/browser/interactive-sessions/{session_id}/viewport | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserProposeViewport |
| POST | /v1/browser/interactive-sessions/{session_id}/viewport/ack | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserAckViewport |
| POST | /v1/browser/interactive-sessions/{session_id}/suspend | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserSuspend |
| DELETE | /v1/browser/interactive-sessions/{session_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserEnd |
| GET | /v1/browser/interactive-sessions/{session_id}/downloads | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserDownloads |
| DELETE | /v1/browser/interactive-sessions/{session_id}/downloads/{download_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserDeleteDownload |
| POST | /v1/browser/interactive-sessions/{session_id}/resume | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserResume |
| GET | /v1/browser/interactive-sessions/{session_id}/tabs | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserTabs |
| GET | /v1/browser/interactive-sessions/{session_id}/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserEvents |
| POST | /v1/browser/interactive-sessions/{session_id}/delegate-control | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserDelegateControl |
| POST | /v1/browser/interactive-sessions/{session_id}/transfer-grants | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserTransferGrant |
| GET | /v1/browser/interactive-sessions/{session_id}/action-plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserActionPlans |
| POST | /v1/browser/interactive-sessions/{session_id}/action-plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.createBrowserActionPlan |
| GET | /v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserActionPlan |
| POST | /v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id}/cancel | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.cancelBrowserActionPlan |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/browser/interactive-sessions/{session_id}/downloads/{download_id}/operations | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileOperations |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-contracts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderContracts |
| POST | /v1/browser/interactive-sessions/{session_id}/file-provider-requests | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.createBrowserFileProviderRequest |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-requests | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderRequests |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderRequest |
| POST | /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/cancel | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.cancelBrowserFileProviderRequest |
| POST | /v1/browser/artifact-provider/admissions/{admission_id}/introspect | ATTESTED_ARTIFACT_PROVIDER_SERVICE_ONLY / ATTESTED_ARTIFACT_PROVIDER:CURRENT_PINNED_MTLS_AND_SIGNED_EXACT_ADMISSION | None.None |
| POST | /v1/browser/artifact-provider/admissions/{admission_id}/claim | ATTESTED_ARTIFACT_PROVIDER_SERVICE_ONLY / ATTESTED_ARTIFACT_PROVIDER:CURRENT_PINNED_MTLS_AND_SIGNED_EXACT_ADMISSION | None.None |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/observation | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderObservation |

**Service dependencies (not Android owner access)**

- VE-f6079fb6d1b5
- VE-d8b7224e92a0

### van.permissions — Standing Permissions

Owner goal: Inspect and control standing permissions.

Route: `settings/permissions`; interaction: `navigation_screen`; domain: `permissions`.

Feature IDs: OF-AUTHORITY-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- standing grants
- origin/last use/expiry
- domain earned/owner/effective ceilings
- suspensions
- policy
- supported domains and levels
- exact normalized ceiling change and expiry
- independent operation-specific stored ceiling readback
- supported action contracts/exact parameter scope
- expiry/max uses and remaining-use enforcement
- fresh native approval/separate service authority
- stored grant/use/revoke readback

**Owner interactions and controls**

- inspect grant
- revoke grant
- inspect authority descriptor and readiness
- select supported domain and S0..S4 owner ceiling
- review and biometrically approve exact sealed ceiling change
- Inspect standing permissions
- Withdraw this standing permission
- Inspect earned, owner and effective autonomy ceilings
- Inspect action gates
- Inspect automatic capability readiness
- Choose a supported domain and owner autonomy ceiling, then approve the exact sealed change with biometrics
- Select a supported action and review bounded exact scope, expiry and maximum uses before A4 approval
- Inspect the exact stored grant and independent use/remaining-scope readback; revoke it explicitly

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Exact owner permission creation, inspection/use enforcement and revocation are implemented alongside S0..S4 domain ceilings. Unsupported actions/scopes refuse; consent never creates service authority or removes fresh native approval requirements.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/permissions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.permissions |
| POST | /v1/permissions/{grant_id}/revoke | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.revokePermission |
| GET | /v1/autonomy | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.autonomy |
| GET | /v1/authority | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.authorityDescriptor |
| GET | /v1/capabilities/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.capabilityStatus |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/permissions/contracts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.permissionContracts |
| GET | /v1/permissions/grants/{grant_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.permissionGrant |

### van.autonomy — Autonomy

Owner goal: Inspect and control autonomy.

Route: `null`; interaction: `inline_section`; domain: `autonomy`.

Feature IDs: OF-AUTHORITY-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- standing grants
- origin/last use/expiry
- domain earned/owner/effective ceilings
- suspensions
- policy
- supported domains and levels
- exact normalized ceiling change and expiry
- independent operation-specific stored ceiling readback

**Owner interactions and controls**

- inspect grant
- revoke grant
- inspect authority descriptor and readiness
- select supported domain and S0..S4 owner ceiling
- review and biometrically approve exact sealed ceiling change
- Inspect earned, owner and effective autonomy ceilings
- Inspect action gates
- Inspect automatic capability readiness
- Choose a supported domain and owner autonomy ceiling, then approve the exact sealed change with biometrics

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Exact owner permission creation, inspection/use enforcement and revocation are implemented alongside S0..S4 domain ceilings. Unsupported actions/scopes refuse; consent never creates service authority or removes fresh native approval requirements.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/autonomy | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.autonomy |
| GET | /v1/authority | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.authorityDescriptor |
| GET | /v1/capabilities/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.capabilityStatus |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |

### van.understanding — Understanding & Adaptation

Owner goal: Inspect and control understanding & adaptation.

Route: `memory/understanding`; interaction: `navigation_screen`; domain: `understanding`.

Feature IDs: OF-LEARNING-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- owner assertions
- OWNER_CONFIRMED/EVIDENCE_DERIVED/TENTATIVE/REJECTED/REVOKED
- vocabulary
- calibration
- cognitive complement
- owner meaning and operationalization
- examples and counterexamples
- optional existing project scope
- owner-authored provenance and exact committed readback
- separate inferred-trait confidence; declarations grant no execution authority

**Owner interactions and controls**

- confirm
- correct
- reject
- define or edit a scoped vocabulary term
- set an explicit domain collaboration instruction
- Inspect assertions, evidence, vocabulary and communication calibration
- Confirm an assertion
- Correct and supersede an assertion
- Reject an assertion
- Define or edit a scoped shared term with exact committed definition and owner provenance readback
- Record or edit an explicit domain collaboration instruction with matching owner-authored readback

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Owner hypothesis confirm/correct/reject, communication calibration and bounded explicit vocabulary/collaboration writers are wired. Fresh committed readback distinguishes owner-authored declarations from existing unconfirmed understanding; collaboration preferences preserve separate inferred traits. Declarations never mint execution grants, certify inferred psychological claims or independently prove future model response compliance. Physical owner-session, edit and readback acceptance remains pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/understanding | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.understanding |
| POST | /v1/understanding/{assertion_id}/confirm | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.confirmUnderstanding |
| POST | /v1/understanding/{assertion_id}/correct | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.correctUnderstanding |
| POST | /v1/understanding/{assertion_id}/reject | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.rejectUnderstanding |
| POST | /v1/understanding/adaptation/{change_id}/revert | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.revertAdaptation |
| POST | /v1/understanding/adaptation/{change_id}/confirm | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.confirmAdaptation |
| GET | /v1/understanding/vocabulary | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerVocabulary |
| PUT | /v1/understanding/vocabulary | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.saveOwnerVocabulary |
| GET | /v1/understanding/complement/preferences | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerCollaborationPreferences |
| PUT | /v1/understanding/complement/preferences | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.saveOwnerCollaborationPreference |

### van.reminders.manage — Reminder Management

Owner goal: Inspect and control reminder management.

Route: `attention/reminders`; interaction: `navigation_screen`; domain: `reminders`.

Feature IDs: OF-REMINDER-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- Open reminder text, due time and overdue state
- Create/resolve/cancel receipt state
- UTC parse semantics and local due readback

**Owner interactions and controls**

- Create
- Resolve
- Cancel
- Refresh
- Read open reminders
- Create a reminder with explicit due time
- Resolve a reminder
- Cancel a reminder

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Natural due-time parsing uses UTC clock phrases; saved due times are displayed in phone local time. Device notification/delivery behavior remains unverified.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/reminders | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.reminders |
| POST | /v1/reminders/parse | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.createReminder |
| POST | /v1/reminders/{reminder_id}/resolve | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.resolveReminder |
| POST | /v1/reminders/{reminder_id}/cancel | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.cancelReminder |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/reminders | .UNWIRED | CANDIDATE_BACKEND_SOURCE_EXISTING_ANDROID_FLOW_ACCEPTANCE_PENDING | Original request-bound idempotency, atomic follow-ups with project/source retained, terminal-state conflicts and recoverable server publication. Attention preserves owner acknowledgement under concurrent reports. |
| POST /v1/reminders | .UNWIRED | CANDIDATE_BACKEND_SOURCE_EXISTING_ANDROID_FLOW_ACCEPTANCE_PENDING | Original request-bound idempotency, atomic follow-ups with project/source retained, terminal-state conflicts and recoverable server publication. Attention preserves owner acknowledgement under concurrent reports. |
| POST /v1/reminders/parse | .UNWIRED | CANDIDATE_BACKEND_SOURCE_EXISTING_ANDROID_FLOW_ACCEPTANCE_PENDING | Original request-bound idempotency, atomic follow-ups with project/source retained, terminal-state conflicts and recoverable server publication. Attention preserves owner acknowledgement under concurrent reports. |
| POST /v1/reminders/{reminder_id}/cancel | .UNWIRED | CANDIDATE_BACKEND_SOURCE_EXISTING_ANDROID_FLOW_ACCEPTANCE_PENDING | Original request-bound idempotency, atomic follow-ups with project/source retained, terminal-state conflicts and recoverable server publication. Attention preserves owner acknowledgement under concurrent reports. |
| POST /v1/reminders/{reminder_id}/resolve | .UNWIRED | CANDIDATE_BACKEND_SOURCE_EXISTING_ANDROID_FLOW_ACCEPTANCE_PENDING | Original request-bound idempotency, atomic follow-ups with project/source retained, terminal-state conflicts and recoverable server publication. Attention preserves owner acknowledgement under concurrent reports. |

### van.memory.history — Fact History

Owner goal: Inspect and control fact history.

Route: `null`; interaction: `modal`; domain: `memory`.

Feature IDs: OF-MEMORY-003.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- Scoped revisions, source/trust/authority, validity, supersession and withdrawal

**Owner interactions and controls**

- Inspect fact history
- Refresh
- Close
- Inspect a fact revision history

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/context/history | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextHistory |

### van.approval.detail — Exact-action approval and refusal

Owner goal: Approve the exact consequential effect deliberately.

Route: `null`; interaction: `inline_section`; domain: `approvals`.

Feature IDs: OF-APPROVAL-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- Original owner command
- Resolved action ID
- Approval expiry
- Biometric challenge pending/refusal

**Owner interactions and controls**

- Approve this occurrence through device biometrics
- Dismiss OS biometric prompt
- Approve the displayed command occurrence with device biometrics
- Explicitly decline the displayed occurrence without authorizing an action

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Normalized exact action parameters, safe Gmail sender/recipient/subject/body digest preview, expiry and explicit discard are supplied. Fresh biometric proof binds those exact parameters; provider, device biometric and receipt acceptance remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/authority | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.authorityDescriptor |
| GET | /v1/owner/google/gmail/drafts/{draft_id}/preview | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.googleGmailDraftPreview |

### van.learning.adaptations — Adaptation review and rollback

Owner goal: Approve or reverse learned changes.

Route: `memory/adaptations`; interaction: `navigation_screen`; domain: `memory`.

Feature IDs: OF-LEARNING-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- Awaiting/active adaptations
- Before/after behavior, reason, evidence and reversibility

**Owner interactions and controls**

- Confirm and read back
- Revert reversible change
- Refresh
- Read active and awaiting adaptations
- Confirm and read back an adaptation
- Revert a reversible adaptation

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Rollback exists only when the actual adaptation is reversible. Full device confirmation/readback remains unverified.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/understanding | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.understanding |
| POST | /v1/understanding/adaptation/{change_id}/confirm | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.confirmAdaptation |
| POST | /v1/understanding/adaptation/{change_id}/revert | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.revertAdaptation |

### van.learning.goals — Goals, unresolved threads and learned strategies

Owner goal: Inspect continuity, conflicts and learning limits.

Route: `memory/goals`; interaction: `navigation_screen`; domain: `memory`.

Feature IDs: OF-LEARNING-003.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- Standing/project goals, constraints, priority and tensions
- Decision history and inactive inference
- Strategies, external evidence, technology radar and measured/unmeasured evaluation
- independent READY/NO_DATA/PARTIAL/DEGRADED producers
- bounded observations/comparisons and unmeasured counts
- timestamps/snapshot digest/source references
- candidate support/counterexamples/unknown outcomes
- original external trust and exact scope disagreement
- advisory inference with no execution grant

**Owner interactions and controls**

- Read
- Open linked mission
- Discuss in Work
- Refresh
- Inspect standing goals, constraints and tensions
- Read decision history and stated reasons
- Inspect bounded learned strategies
- Read external observations without inferred agreement
- Inspect technology evaluation state
- Inspect measured and unmeasured evaluation dimensions
- Inspect actual independent read-time producer status, bounds, timestamps and evidence
- Inspect bounded repeated-choice candidates, counterexamples and independent outcome references
- Compare an exact cited structured source claim with the current matching owner declaration

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Observed decision and structured external comparison producers are implemented with deterministic bounded evidence and recovery. Empty/unbound provider feeds remain NO_DATA or PARTIAL; candidates are advisory and neither declarations nor patterns prove future model compliance.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/understanding/intents | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.standingIntents |
| GET | /v1/understanding/decisions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.decisionHistory |
| GET | /v1/strategies | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.learnedStrategies |
| GET | /v1/external-reality | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.externalReality |
| GET | /v1/technology-radar | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.technologyRadar |
| GET | /v1/eval | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.evalReport |
| GET | /v1/understanding/learning/producers | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.learningProducers |

### van.projects.rationale — Project rationale and decision provenance

Owner goal: Remember why choices were made and rejected.

Route: `projects/{projectId}/rationale`; interaction: `navigation_screen`; domain: `projects`.

Feature IDs: OF-PROJECT-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- rationale
- tried/rejected approaches
- evidence refs
- separation from repository truth

**Owner interactions and controls**

- inspect rationale
- record owner rationale
- Inspect project rationale, past rejected strategies and provenance
- Record owner-authored rationale and verify same-project readback

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Project rationale is independently readable and writable with matching receipt and readback. Failed mutation retains draft and requires a fresh read; no automatic retry/idempotency promise. Project Truth remains separate internal repository authority. Handset/backend integration is unverified.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/projects/{project_id}/strategic-memory | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.projectStrategicMemory |
| POST | /v1/projects/{project_id}/strategic-memory | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.recordProjectRationale |

### van.knowledge.research — Research, private knowledge and evidence

Owner goal: Obtain citable knowledge with explicit provider readiness.

Route: `owner/research`; interaction: `navigation_screen`; domain: `research`.

Feature IDs: OF-KNOWLEDGE-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- VEKL/Obsidian/Notebook/research readiness
- source/trust/time
- evidence
- notebook records
- research outcomes

**Owner interactions and controls**

- ask through command controller
- inspect citations
- inspect readiness
- request declared notebook mutation
- Inspect owner-safe research records
- Submit only an advertised exact owner command
- Inspect provider evidence, query citations and operations

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Exa and direct private-knowledge producers use actual bounded transport and truthful failures. TLS identities, credentials, egress and provider configuration remain deployment prerequisites; read availability is distinct from verified owner effect.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/runtime/knowledge/status | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| POST | /v1/runtime/knowledge/vekl/query | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| POST | /v1/runtime/knowledge/obsidian/query | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| GET | /v1/runtime/knowledge/notebook/enterprise/recent | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| GET | /v1/runtime/knowledge/notebook/enterprise/{notebook_id} | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| POST | /v1/runtime/knowledge/notebook/consumer/ask | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| POST | /v1/runtime/knowledge/actions/execute | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| GET | /v1/runtime/research/status | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| POST | /v1/runtime/research/search | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| GET | /v1/owner/research | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerResearch |
| GET | /v1/owner/knowledge | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerKnowledge |

**Service dependencies (not Android owner access)**

- VE-24c007113944
- VE-0b6118c297e7
- VE-d40e4030951b
- VE-4c9ebe3b29bf
- VE-7baac04c84f3
- VE-ca42b4c1336c
- VE-ff3ae0a0f3c1
- VE-341c2ac1a332
- VE-7c92759db8dd

### van.automation.library — Automation inventory and admission

Owner goal: Inspect bounded automation and disable standing work.

Route: `owner/automation`; interaction: `navigation_screen`; domain: `automation`.

Feature IDs: OF-AUTOMATION-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- capability/template readiness
- workflow mission/run
- authority scope
- effect receipts
- standing intent
- repair status
- supported closed IR/DSL and deployment requirements
- immutable candidate request/artifact/revision
- pinned admitted helper/parent manifests and inputs
- selected/skipped/refused step receipts
- preconditions/independent target predicates
- actual provider/worker configuration status

**Owner interactions and controls**

- request automation through controller
- inspect run/evidence
- disable standing intent through supported owner command
- Inspect owner-safe automation records
- Submit only an advertised exact owner command
- Prepare a bounded typed IR candidate, recover the exact artifact and review its declared deployment limitations
- Review deterministic supported branches, mappings, preconditions and independent success predicates
- Request only an admitted immutable artifact with pinned inputs and inspect actual run/step evidence

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Owner candidate/recovery, bounded branches/mappings/predicates and exact admitted run inspection are implemented. Actual n8n helpers, credentials, current manifests and provider canaries must be bound/read back on the authorized host. Unsupported arbitrary code and unsealed external capability writes remain refused by the closed contract.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/automation/health | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| GET | /v1/automation/templates | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:automation | .UNWIRED |
| GET | /v1/automation/capabilities/{capability_id} | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:automation | .UNWIRED |
| POST | /v1/automation/standing-intents | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:automation | .UNWIRED |
| POST | /v1/automation/standing-intents/{intent_id}/disable | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:automation | .UNWIRED |
| GET | /v1/automation/temporal/{workflow_id} | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:automation | .UNWIRED |
| GET | /v1/owner/automation | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerAutomation |
| GET | /v1/owner/automation/contracts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationContracts |
| POST | /v1/owner/automation/plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.proposeAutomationPlan |
| GET | /v1/owner/automation/plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationPlans |
| GET | /v1/owner/automation/plans/{artifact_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationPlan |
| GET | /v1/owner/automation/requests/{idempotency_key} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationPlanRequest |
| GET | /v1/owner/automation/runs/{run_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationRun |

**Service dependencies (not Android owner access)**

- VE-af180630c30f
- VE-7c1adc62cbe1
- VE-faa9efd04c69
- VE-69f29d84324b
- VE-ad21df37dc16
- VE-96ecedfcad3a

### van.automation.intent — Standing authority and workflow detail

Owner goal: Inspect bounded automation and disable standing work.

Route: `null`; interaction: `inline_section`; domain: `automation`.

Feature IDs: OF-AUTOMATION-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- capability/template readiness
- workflow mission/run
- authority scope
- effect receipts
- standing intent
- repair status
- supported closed IR/DSL and deployment requirements
- immutable candidate request/artifact/revision
- pinned admitted helper/parent manifests and inputs
- selected/skipped/refused step receipts
- preconditions/independent target predicates
- actual provider/worker configuration status

**Owner interactions and controls**

- request automation through controller
- inspect run/evidence
- disable standing intent through supported owner command
- Inspect owner-safe automation records
- Submit only an advertised exact owner command
- Prepare a bounded typed IR candidate, recover the exact artifact and review its declared deployment limitations
- Review deterministic supported branches, mappings, preconditions and independent success predicates
- Request only an admitted immutable artifact with pinned inputs and inspect actual run/step evidence

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Owner candidate/recovery, bounded branches/mappings/predicates and exact admitted run inspection are implemented. Actual n8n helpers, credentials, current manifests and provider canaries must be bound/read back on the authorized host. Unsupported arbitrary code and unsealed external capability writes remain refused by the closed contract.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/owner/automation | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerAutomation |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/owner/automation/contracts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationContracts |
| POST | /v1/owner/automation/plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.proposeAutomationPlan |
| GET | /v1/owner/automation/plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationPlans |
| GET | /v1/owner/automation/plans/{artifact_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationPlan |
| GET | /v1/owner/automation/requests/{idempotency_key} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationPlanRequest |
| GET | /v1/owner/automation/runs/{run_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationRun |

### van.browser.downloads — Downloads, uploads and content policy

Owner goal: Transfer files under explicit owner control.

Route: `null`; interaction: `modal`; domain: `browser`.

Feature IDs: OF-BROWSER-004.

Wiring: `EXTERNAL_CONTRACT_OR_ASSET_REQUIRED`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- Host download state, record ID and suggested name
- Known size/type, dangerous/quarantine/failure reason
- Record-removal confirmation derived from exact receipt and independent readback
- Explicit unsupported phone binary transfer/upload and clipboard state
- owned download/chooser identifiers and current target
- producer and media epoch
- filename/type/size/hash and safe origin metadata
- pending/failed/available byte effect status
- host deletion acknowledgement
- explicit clipboard effect receipt
- exact file hash/size/type/producer epoch
- safe inert local preview
- bounded source-labelled native analysis
- exact operation result/recovery
- external provider bound/executable/qualified status; unbound imports unavailable
- immutable provider request/idempotency key/digest/deadline
- current exact provider/owner/project destination
- fresh native A4 challenge and approval state
- actual one-use provider claim and independent persisted-byte receipt
- explicit OBSERVED_EXTERNAL_EFFECT versus STILL_UNKNOWN observation; original canonical outcome/fence retained
- UNKNOWN remains read-only; no content execution or truth promotion

**Owner interactions and controls**

- review host downloads
- save exact download to phone
- choose and upload a phone document for current browser chooser
- explicit copy browser selection
- explicit paste phone clipboard
- remove eligible host record and inspect physical cleanup acknowledgement
- Review actual owned-session download records
- Remove an eligible host download record and confirm exact DELETED readback
- Save verified browser download bytes through the Android Storage Access Framework
- Choose and upload a bounded phone document only for an explicit current browser chooser
- Explicitly copy browser selection or paste phone clipboard under current owner control
- Inspect native file analysis and exact import operation readbacks, with bound hash/epoch and provider limits
- Open independently verified selected bytes in VAN's bounded inert native viewer
- Read current archive/candidate provider capability, exact admitted destination and unavailable/refused states
- Prepare and independently recover the exact immutable file/destination request before any provider effect
- Approve the exact file request with fresh native A4 and inspect separately admitted provider claim and persisted-byte evidence
- Explicitly check an already claimed external byte receipt after an uncertain effect without resubmitting or changing the original outcome

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Native file inspection, inert preview, bounded analysis and exact readback are wired. Owner provider catalog/draft/recovery, canonical native A4 admission, separate attested mTLS claim/introspection and independently verified byte receipts are implemented. The proposed Oracle/VEKL production target remains unbound/unqualified; defaults are UNAVAILABLE and current capability/bindings must be supplied before owner preparation/execution. Host cleanup and actual phone byte/provider effects still require independent acceptance.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/browser/interactive-sessions/{session_id}/downloads | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserDownloads |
| DELETE | /v1/browser/interactive-sessions/{session_id}/downloads/{download_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserDeleteDownload |
| POST | /v1/browser/interactive-sessions/{session_id}/transfer-grants | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserTransferGrant |
| GET | /v1/browser/interactive-sessions/{session_id}/downloads/{download_id}/operations | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileOperations |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-contracts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderContracts |
| POST | /v1/browser/interactive-sessions/{session_id}/file-provider-requests | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.createBrowserFileProviderRequest |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-requests | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderRequests |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderRequest |
| POST | /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/cancel | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.cancelBrowserFileProviderRequest |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| POST | /v1/browser/artifact-provider/admissions/{admission_id}/introspect | ATTESTED_ARTIFACT_PROVIDER_SERVICE_ONLY / ATTESTED_ARTIFACT_PROVIDER:CURRENT_PINNED_MTLS_AND_SIGNED_EXACT_ADMISSION | None.None |
| POST | /v1/browser/artifact-provider/admissions/{admission_id}/claim | ATTESTED_ARTIFACT_PROVIDER_SERVICE_ONLY / ATTESTED_ARTIFACT_PROVIDER:CURRENT_PINNED_MTLS_AND_SIGNED_EXACT_ADMISSION | None.None |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/observation | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderObservation |

**Service dependencies (not Android owner access)**

- VE-f6079fb6d1b5
- VE-d8b7224e92a0

### van.devices.provision — Signed provisioning and recovery

Owner goal: Use the app only after a supported readiness journey.

Route: `null`; interaction: `inline_section`; domain: `account`.

Feature IDs: OF-PROVISION-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `AUTOMATIC_READINESS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- permissions
- signed provisioning status
- paired device
- bound hardware identity
- overlay/listener/mic/biometric
- gateway connectivity
- selected Google consent

**Owner interactions and controls**

- apply signed provisioning payload
- pair/bind
- grant Android permissions
- run readiness check
- re-enroll through supported installer flow

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Automatic signed owner-core bootstrap/recovery requires no in-app backend or Hermes connection settings. Backend, product Hermes profile van and direct phone ingress colocate on van-trading-core under CORE_ONLY_V2; dial-control supplies native Artemis/development services. Oracle Admin is excluded. Private TLS ingress, release signer/trust/bootstrap binding, owner installer delivery and physical attestation/connectivity remain unqualified.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/devices/pair | DIRECT_OWNER_ROUTE / PAIRING_TICKET_AND_ATTESTED_BOUND_DEVICE_PROOF; EXACT_RECOVERY_WITH_CLIENT_TOKEN | VanGatewayClient.pairThisDevice |
| POST | /v1/devices/bootstrap/challenge | DIRECT_OWNER_ROUTE / SINGLE_USE_BOOTSTRAP_TOKEN | VanGatewayClient.bindThisDevice.challenge |
| POST | /v1/devices/bootstrap/attest | DIRECT_OWNER_ROUTE / SINGLE_USE_BOOTSTRAP_TOKEN_AND_PINNED_ATTESTATION_CHAIN_AND_FRESH_DEVICE_PROOF | VanGatewayClient.bindThisDevice.attest |
| POST | /v1/devices/tls-certificate | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | .UNWIRED |
| GET | /v1/device-binding/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.deviceBindingStatus |
| GET | /v1/connectivity/manifest | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.connectivityManifest |
| POST | /v1/devices/bootstrap/recover | DIRECT_OWNER_ROUTE / CONSUMED_BOOTSTRAP_TOKEN_AND_EXACT_ACTIVE_DEVICE_PROOF | VanGatewayClient.recoverBootstrap |
| POST | /v1/device-binding/certify | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ensureCertifiedIdentity |
| POST | /v1/devices/provisioning-status | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:device_enrolment | .UNWIRED |

**Service dependencies (not Android owner access)**

- VE-4af2782b0c0a

### van.diagnostics — Connection health and command correlation

Owner goal: Understand a failure and inspect safe evidence.

Route: `owner/diagnostics`; interaction: `navigation_screen`; domain: `settings`.

Feature IDs: OF-DIAGNOSTICS-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- health/degraded
- transport mode/path
- queue/breaker
- trace/alerts
- mission/command/run correlation
- verification state

**Owner interactions and controls**

- inspect trace/evidence
- copy redacted diagnostic receipt
- retry supported request
- Inspect owner-safe settings records

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Recorded runtime/provider configuration, actual verification and independent source failures are supplied. Live configured services, enabled egress, diagnostics/privacy and physical acceptance remain pending; a registered provider is not proof of readiness.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /health | DIRECT_OWNER_ROUTE / INGRESS_BEARER | VanGatewayClient.health |
| GET | /v1/observability/health | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:observability | .UNWIRED |
| GET | /v1/observability/alerts | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:observability | .UNWIRED |
| GET | /v1/observability/trace/{command_id} | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:observability | .UNWIRED |
| GET | /v1/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.events |
| GET | /v1/owner/diagnostics | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerDiagnostics |

**Service dependencies (not Android owner access)**

- VE-be1d235e3e07
- VE-7b962dca04ce
- VE-b6d0fb44ce1a

### van.onboarding — Device Onboarding

Owner goal: Grant the Android capabilities needed by resident VAN.

Route: `null`; interaction: `native_activity`; domain: `settings`.

Feature IDs: OF-PROVISION-001, OF-SETTINGS-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- permission readiness
- overlay/notification/microphone/battery/biometric stages

**Owner interactions and controls**

- open Android settings
- grant microphone
- continue to Command Centre

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Activity entry outside the Command Centre route registry; verify local permission/recovery paths separately.

### van.provisioning — Signed Provisioning Intake

Owner goal: Enroll this owner device through the signed installer without an interactive setup screen.

Route: `null`; interaction: `headless_intake_activity`; domain: `settings`.

Feature IDs: OF-PROVISION-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `HEADLESS_INSTALLER_INTAKE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- safe installer intake acknowledgment/refusal reason
- safe application log after enrollment succeeds or fails

**Owner interactions and controls**

- installer invokes explicit Activity with signed envelope
- validate signature, expiry and replay
- pair and bind hardware identity on application scope
- finish intake Activity immediately

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Automatic signed owner-core bootstrap/recovery requires no in-app backend or Hermes connection settings. Backend, product Hermes profile van and direct phone ingress colocate on van-trading-core under CORE_ONLY_V2; dial-control supplies native Artemis/development services. Oracle Admin is excluded. Private TLS ingress, release signer/trust/bootstrap binding, owner installer delivery and physical attestation/connectivity remain unqualified.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/devices/pair | DIRECT_OWNER_ROUTE / PAIRING_TICKET_AND_ATTESTED_BOUND_DEVICE_PROOF; EXACT_RECOVERY_WITH_CLIENT_TOKEN | VanGatewayClient.pairThisDevice |
| POST | /v1/devices/bootstrap/challenge | DIRECT_OWNER_ROUTE / SINGLE_USE_BOOTSTRAP_TOKEN | VanGatewayClient.bindThisDevice.challenge |
| POST | /v1/devices/bootstrap/attest | DIRECT_OWNER_ROUTE / SINGLE_USE_BOOTSTRAP_TOKEN_AND_PINNED_ATTESTATION_CHAIN_AND_FRESH_DEVICE_PROOF | VanGatewayClient.bindThisDevice.attest |
| POST | /v1/devices/bootstrap/recover | DIRECT_OWNER_ROUTE / CONSUMED_BOOTSTRAP_TOKEN_AND_EXACT_ACTIVE_DEVICE_PROOF | VanGatewayClient.recoverBootstrap |
| POST | /v1/device-binding/certify | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ensureCertifiedIdentity |
| POST | /v1/devices/provisioning-status | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:device_enrolment | .UNWIRED |

**Service dependencies (not Android owner access)**

- VE-4af2782b0c0a

### van.share.intake — Shared Context Intake

Owner goal: Share owner-selected content with VAN.

Route: `null`; interaction: `transient_intake_activity`; domain: `context`.

Feature IDs: OF-SHARE-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- shared text/URL metadata
- sanitization/classification

**Owner interactions and controls**

- enqueue selected context

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Share intake feeds the owner review/controller path while external content remains DATA. Target-selection, degraded/offline presentation and physical Android share-sheet acceptance remain pending redesign/acceptance work.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/context/ingest | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ingestCapturedContext |

### van.memory.privacy — Memory privacy and retention

Owner goal: Inspect and control fact history.

Route: `null`; interaction: `modal`; domain: `memory`.

Feature IDs: OF-MEMORY-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- Actual owner-derived stores, row counts, retained record categories
- Erasure target and exact approval scope
- privacy-safe stable record identity
- declared/observed/inferred/mixed/unclassified provenance
- screened bounded fields/export
- complete stored-scope revision digest
- affected store counts/dependent identities
- retained work/audit and independent erased-identity readback

**Owner interactions and controls**

- Inspect stores
- Request forget store/all
- Cancel confirmation
- Open Work approval
- Inspect held stores and retention
- Request erasure of a listed store or all owner-derived memory
- Inspect paginated exact records, screened fields and declared/observed/inferred provenance
- Copy an independently reread screened bounded representation of the selected exact record
- Review affected record counts and request fresh biometric erasure of precisely that revision

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Per-record inspection, bounded screened export and exact immutable A4 erasure are supplied for all twelve forgettable stores. New/changed dependencies refuse stale approval; independent readback preserves unrelated rows. Direct DELETE remains refused. Physical privacy, biometric and restart acceptance remains unverified.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/context/memory | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextMemory |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/commands/{command_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.commandStatus |
| GET | /v1/context/export | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextExport |
| GET | /v1/context/records | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextRecords |
| GET | /v1/context/records/{store}/{record_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextRecord |
| GET | /v1/context/records/{store}/{record_id}/export | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.exportContextRecord |
| GET | /v1/context/records/{store}/{record_id}/erasure-plan | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextRecordErasurePlan |

### van.knowledge.sources — Private knowledge providers and citations

Owner goal: Obtain citable knowledge with explicit provider readiness.

Route: `owner/knowledge`; interaction: `navigation_screen`; domain: `research`.

Feature IDs: OF-KNOWLEDGE-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `PARTIAL_OWNER_SURFACE`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- VEKL/Obsidian/Notebook/research readiness
- source/trust/time
- evidence
- notebook records
- research outcomes

**Owner interactions and controls**

- ask through command controller
- inspect citations
- inspect readiness
- request declared notebook mutation
- Inspect provider evidence, query citations and operations

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Exa and direct private-knowledge producers use actual bounded transport and truthful failures. TLS identities, credentials, egress and provider configuration remain deployment prerequisites; read availability is distinct from verified owner effect.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/owner/knowledge | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerKnowledge |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |

### van.browser.outcome — Browser task outcome evidence

Owner goal: Inspect automation state and task evidence.

Route: `owner/browser-outcome/{taskId}`; interaction: `navigation_screen`; domain: `browser`.

Feature IDs: OF-BROWSER-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- Execution completion distinct from unverified task goal
- Worker goal proposal nullable/not persisted explanation
- Evidence kind/time/ID, source trust and injection assessment
- URL/DOM/screenshot/extraction digest summaries
- Missing postconditions and next action
- Separately authoritative mission outcome, observation time and evidence references

**Owner interactions and controls**

- Refresh task outcome
- Open linked mission
- Inspect a browser task outcome without claiming task-goal verification

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Bounded browser mutation plans, click/fill results and exact cancellation fencing are implemented. Current native target/profile/producer and private stream/control hosts must be observed. A draft or successful transport does not prove mutation, closure or provider effect; arbitrary unsealed mutation remains refused.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/owner/browser/tasks/{task_id}/outcome | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerBrowserOutcome |

### van.trading.tickets — Trading tickets and broker receipts

Owner goal: Inspect real tickets and record exact broker fills with fresh owner authority and independent receipt readback.

Route: `tickets`; interaction: `nested_navigation_screen`; domain: `trading`.

Feature IDs: OF-TRADING-005.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- ticket identifier/status
- broker fill price and quantity
- contract note reference
- normalized approval scope/expiry
- independent confirmation ledger receipt

**Owner interactions and controls**

- inspect ticket
- refresh
- confirm exact broker fill
- decline pending approval
- Read and refresh actual ticket/fill-confirmation records
- Record an exact broker fill with independent chained-ledger readback

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Actual ticket read UI and exact broker-fill confirmation sheet are wired through fresh ticket authority plus A4 biometric command; an independent chained-ledger verifier settles the receipt. Owner halt has current status readback. Confirmation records a broker receipt and never executes an order; credentials/execution/provider acceptance remain external.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/tickets | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingTickets |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |

### van.approval.trading-ticket — Exact broker-fill receipt confirmation

Owner goal: Inspect real tickets and record exact broker fills with fresh owner authority and independent receipt readback.

Route: `null`; interaction: `modal`; domain: `trading`.

Feature IDs: OF-TRADING-005, OF-APPROVAL-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- ticket identifier/status
- broker fill price and quantity
- contract note reference
- normalized approval scope/expiry
- independent confirmation ledger receipt

**Owner interactions and controls**

- inspect ticket
- refresh
- confirm exact broker fill
- decline pending approval
- Record an exact broker fill with independent chained-ledger readback

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Actual ticket read UI and exact broker-fill confirmation sheet are wired through fresh ticket authority plus A4 biometric command; an independent chained-ledger verifier settles the receipt. Owner halt has current status readback. Confirmation records a broker receipt and never executes an order; credentials/execution/provider acceptance remain external.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/tickets | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingTickets |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |

### van.attention.decision — Exact owner choice and evidence

Owner goal: Understand why owner input is needed and record a choice.

Route: `null`; interaction: `inline_section`; domain: `memory`.

Feature IDs: OF-DECISION-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- listed stable choices and proposed labels
- exact owner note/revision/expiry
- REFERENCE_ONLY versus RECORDED_EVENT evidence
- immutable answer/recovery identity; grants_action_authority=false

**Owner interactions and controls**

- Read and answer an exact owner choice with evidence, expiry, note and immutable recovery identity

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Actual typed detail, listed choices, source-labelled references, expiry, immutable answer and recovery are wired. The first authorized answer and its learning fingerprint commit together. A choice is a judgment and does not substitute for cryptographic action approval.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/decisions/{decision_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.decision |
| POST | /v1/decisions/{decision_id}/answer | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.answerDecision |

### van.work.mission-control — Mission dispatch fence and direction receipt

Owner goal: Stop or add direction to the existing mission.

Route: `null`; interaction: `inline_section`; domain: `memory`.

Feature IDs: OF-MISSION-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- current dispatch fence/generation
- exact immutable request hash and direction
- run-bound ordered worker acknowledgement
- existing command/action authority
- already-dispatched work may finish; process_stopped_verified=false

**Owner interactions and controls**

- Request exact mission pause and independently recover its ordered control receipt
- Request exact mission resume and independently recover its ordered control receipt
- Request exact mission direction and independently recover its ordered control receipt

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Durable pause/resume/direction requests, exact recovery and run-bound ordered Hermes checkpoints are implemented. The fence prevents new gateway/browser/automation effects; it does not prove an already running external OS process stopped. Direction applies at the next admitted worker checkpoint without widening authority.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/missions/{mission_id}/control | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missionControl |
| GET | /v1/missions/{mission_id}/control/requests/{request_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missionControlRequest |
| POST | /v1/missions/{mission_id}/pause | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.writeMissionControl |
| POST | /v1/missions/{mission_id}/resume | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.writeMissionControl |
| POST | /v1/missions/{mission_id}/direction | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.writeMissionControl |

### van.memory.record — Exact retained record and erasure scope

Owner goal: Read everything VAN holds and control retention.

Route: `null`; interaction: `modal`; domain: `memory`.

Feature IDs: OF-MEMORY-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- privacy-safe stable record identity
- declared/observed/inferred/mixed/unclassified provenance
- screened bounded fields/export
- complete stored-scope revision digest
- affected store counts/dependent identities
- retained work/audit and independent erased-identity readback

**Owner interactions and controls**

- Inspect paginated exact records, screened fields and declared/observed/inferred provenance
- Copy an independently reread screened bounded representation of the selected exact record
- Review affected record counts and request fresh biometric erasure of precisely that revision

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Per-record inspection, bounded screened export and exact immutable A4 erasure are supplied for all twelve forgettable stores. New/changed dependencies refuse stale approval; independent readback preserves unrelated rows. Direct DELETE remains refused. Physical privacy, biometric and restart acceptance remains unverified.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/context/records | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextRecords |
| GET | /v1/context/records/{store}/{record_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextRecord |
| GET | /v1/context/records/{store}/{record_id}/export | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.exportContextRecord |
| GET | /v1/context/records/{store}/{record_id}/erasure-plan | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextRecordErasurePlan |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |

### van.permissions.grant — Exact bounded owner consent

Owner goal: Know and revoke what VAN may do unprompted.

Route: `null`; interaction: `inline_section`; domain: `memory`.

Feature IDs: OF-AUTHORITY-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- supported action contracts/exact parameter scope
- expiry/max uses and remaining-use enforcement
- fresh native approval/separate service authority
- stored grant/use/revoke readback

**Owner interactions and controls**

- Select a supported action and review bounded exact scope, expiry and maximum uses before A4 approval
- Inspect the exact stored grant and independent use/remaining-scope readback; revoke it explicitly

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Exact owner permission creation, inspection/use enforcement and revocation are implemented alongside S0..S4 domain ceilings. Unsupported actions/scopes refuse; consent never creates service authority or removes fresh native approval requirements.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/permissions/contracts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.permissionContracts |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/permissions/grants/{grant_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.permissionGrant |
| POST | /v1/permissions/{grant_id}/revoke | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.revokePermission |

### van.automation.plan — Automation candidate, admission and exact run evidence

Owner goal: Inspect bounded automation and disable standing work.

Route: `null`; interaction: `inline_section`; domain: `memory`.

Feature IDs: OF-AUTOMATION-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- supported closed IR/DSL and deployment requirements
- immutable candidate request/artifact/revision
- pinned admitted helper/parent manifests and inputs
- selected/skipped/refused step receipts
- preconditions/independent target predicates
- actual provider/worker configuration status

**Owner interactions and controls**

- Prepare a bounded typed IR candidate, recover the exact artifact and review its declared deployment limitations
- Review deterministic supported branches, mappings, preconditions and independent success predicates
- Request only an admitted immutable artifact with pinned inputs and inspect actual run/step evidence

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Owner candidate/recovery, bounded branches/mappings/predicates and exact admitted run inspection are implemented. Actual n8n helpers, credentials, current manifests and provider canaries must be bound/read back on the authorized host. Unsupported arbitrary code and unsealed external capability writes remain refused by the closed contract.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/owner/automation/contracts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationContracts |
| POST | /v1/owner/automation/plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.proposeAutomationPlan |
| GET | /v1/owner/automation/plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationPlans |
| GET | /v1/owner/automation/plans/{artifact_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationPlan |
| GET | /v1/owner/automation/requests/{idempotency_key} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationPlanRequest |
| GET | /v1/owner/automation/runs/{run_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationRun |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |

### van.browser.action-plan — Immutable browser effect review and observation

Owner goal: Ask VAN about the visible page and keep immediate owner control.

Route: `null`; interaction: `modal`; domain: `browser`.

Feature IDs: OF-BROWSER-003, OF-BROWSER-001.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- current native target/hostname/profile/producer epoch
- owner-prepared task/immutable plan
- exact effect parameters/observed predicates
- claimed/uncertain/observed result without re-actuation
- foreground A3 task preparation
- fresh native biometric A4 plan approval
- current profile_mutation_permitted/gateway_authorized_only posture
- exact click/fill parameters/step observations
- cancellation fence/retained result

**Owner interactions and controls**

- Prepare an actual browser task, review exact click/fill effects and observe the sealed result without re-actuation

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Bounded browser mutation plans, click/fill results and exact cancellation fencing are implemented. Current native target/profile/producer and private stream/control hosts must be observed. A draft or successful transport does not prove mutation, closure or provider effect; arbitrary unsealed mutation remains refused.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/browser/interactive-sessions/{session_id}/action-plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserActionPlans |
| POST | /v1/browser/interactive-sessions/{session_id}/action-plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.createBrowserActionPlan |
| GET | /v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserActionPlan |
| POST | /v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id}/cancel | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.cancelBrowserActionPlan |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |

### van.browser.file-provider — Exact owner file destination, admission and result

Owner goal: Transfer files under explicit owner control.

Route: `null`; interaction: `modal`; domain: `browser`.

Feature IDs: OF-BROWSER-004.

Wiring: `EXTERNAL_CONTRACT_OR_ASSET_REQUIRED`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- reviewed file identity/hash/size
- exact provider/owner/project destination
- current target capability/availability
- immutable request/digest/idempotency key/deadline
- fresh exact native A4 challenge/biometric outcome
- request status and original recovery identity
- actual provider claim and independently observed persisted-byte receipt
- explicit read-only observation separate from retained canonical outcome and replacement fence
- untrusted file source; no content execution or owner/project truth promotion

**Owner interactions and controls**

- Read current archive/candidate provider capability, exact admitted destination and unavailable/refused states
- Prepare and independently recover the exact immutable file/destination request before any provider effect
- Approve the exact file request with fresh native A4 and inspect separately admitted provider claim and persisted-byte evidence
- Explicitly check an already claimed external byte receipt after an uncertain effect without resubmitting or changing the original outcome

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Native file inspection, inert preview, bounded analysis and exact readback are wired. Owner provider catalog/draft/recovery, canonical native A4 admission, separate attested mTLS claim/introspection and independently verified byte receipts are implemented. The proposed Oracle/VEKL production target remains unbound/unqualified; defaults are UNAVAILABLE and current capability/bindings must be supplied before owner preparation/execution. Host cleanup and actual phone byte/provider effects still require independent acceptance.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-contracts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderContracts |
| POST | /v1/browser/interactive-sessions/{session_id}/file-provider-requests | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.createBrowserFileProviderRequest |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-requests | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderRequests |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderRequest |
| POST | /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/cancel | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.cancelBrowserFileProviderRequest |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| POST | /v1/browser/artifact-provider/admissions/{admission_id}/introspect | ATTESTED_ARTIFACT_PROVIDER_SERVICE_ONLY / ATTESTED_ARTIFACT_PROVIDER:CURRENT_PINNED_MTLS_AND_SIGNED_EXACT_ADMISSION | None.None |
| POST | /v1/browser/artifact-provider/admissions/{admission_id}/claim | ATTESTED_ARTIFACT_PROVIDER_SERVICE_ONLY / ATTESTED_ARTIFACT_PROVIDER:CURRENT_PINNED_MTLS_AND_SIGNED_EXACT_ADMISSION | None.None |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/observation | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderObservation |

**Service dependencies (not Android owner access)**

- VE-f6079fb6d1b5
- VE-d8b7224e92a0

### van.settings.speaker-profile — Local owner speaker consent, capture and erasure

Owner goal: Correct pronunciation/recognition and control adaptation.

Route: `null`; interaction: `inline_section`; domain: `memory`.

Feature IDs: OF-VOICE-002.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; frontend integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`; acceptance evidence: `Current source review; final whole-workspace checks pending; production/provider/physical acceptance unverified.`.

**Information supplied**

- generic speaker model readiness separate from authenticated profile presence
- current full owner/device/hardware/approval binding
- dedicated local consent operation/revision/model/freshness
- current clip phrase/index/energy quality/progress
- encrypted normalized embedding and retained consent metadata; no stored raw PCM
- inconclusive stale/unbound speaker evidence; no action authority
- exact offline erasure using genuine local keys and absence readback

**Owner interactions and controls**

- Enroll owner voice or replace retained profile after dedicated native strong biometric consent
- Allow microphone and observe actual current phrase, clip index and sample progress
- Cancel pending consent or capture without replacing or erasing the existing profile
- Read current model/profile readiness with exact binding and encrypted-store readback
- Erase the exact local profile after separate fresh cryptographic consent and verify absence
- Enroll or replace the exact device-local owner profile using dedicated biometric consent and three actual microphone clips
- Read local profile/model readiness and permit revocable similarity evidence only for the exact fresh current owner binding
- Erase precisely the retained encrypted profile after dedicated biometric consent, including when the backend is unreachable

**Required acceptance states**

- happy
- error
- loading
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared gaps**

- Local enrollment/replace/readiness/erasure controls and generic native extraction are source implemented. Actual owner capture/profile, speaker discrimination, microphone permissions/audio arbitration, device cryptography and physical acoustic quality remain unverified. Speaker similarity is revocable evidence only; owner speech corrections remain explicit declarations and cannot confer action authority.

## Feature obligations

### OF-HOME-001 — Current state and briefing

Owner goal: Know what needs attention now.

Screens: van.home; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- VAN activity
- top attention
- active work
- upcoming reminders
- recent verified changes
- gateway/Hermes health
- selected project
- queue count

**Owner interactions and controls**

- open a real mission/attention/project/trade destination
- refresh
- Inspect and refresh independently bounded source health, age and concrete destinations

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Source reads are bounded independently; failed or timed-out reads retain UNKNOWN/unavailable health and available cached age. Final visual state design and physical navigation acceptance remain pending.

**Current navigation contract**

- {"description": "Fresh launch and an intent delivered to the resident singleTop Activity use the same validated destination resolver. A resident deep link navigates the existing NavHost once instead of recursively restarting the Activity. A pending known destination is saved/restored through recreation and consumed once; foreign/invalid link content is never a raw route or fallback authority. Real process/deep-link behavior remains a handset acceptance case.", "device_execution_status": "UNVERIFIED", "source_citations": [{"file": "android/app/src/main/java/com/dial/van/command/nav/VanNavModel.kt", "line": 65, "ref": "WORKSPACE_PATCH", "review_scope": "Fresh and resident Activity entry share the exact allowlisted destination resolver; foreign links do not fall through to extra-module steering.", "sha256": "187616b948c9dbf6de5a2914f9b49f6ed444bba19b9de841dac1947db695bcd2"}, {"file": "android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt", "line": 150, "ref": "WORKSPACE_PATCH", "review_scope": "Resident singleTop entry steers the existing NavHost once, with saved pending-route recovery, without restarting/redelivering the Activity.", "sha256": "14c746d2024fccf594a99227b2e1685c6f35a7045933a5eb0c69cafc0c28d032"}]}

**Located source functions (not whole-feature acceptance)**

- OF-HOME-001:independent-sources: Inspect and refresh independently bounded source health, age and concrete destinations — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /health | DIRECT_OWNER_ROUTE / INGRESS_BEARER | VanGatewayClient.health |
| GET | /v1/briefing | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.briefing |
| GET | /v1/missions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missions |
| GET | /v1/attention | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.attention |
| GET | /v1/trading/assessment | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingAssessment |

### OF-COMMAND-001 — Unified owner command and conversation

Owner goal: Instruct VAN once through text, voice or contextual control.

Screens: van.work, van.voice.turn, van.floating; required screens: .

Wiring: `EXTERNAL_CONTRACT_OR_ASSET_REQUIRED`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- thread and selected project
- delivery status
- command/mission identity
- owner-safe response
- authority target and expected effect

**Owner interactions and controls**

- draft
- submit
- mic
- retry using same identity when transport is ambiguous
- cancel where supported
- Submit owner text or final admitted speech through the existing controller
- Read accepted command through terminal owner status

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Exact prepared signed bodies survive ambiguous transport replies; one controller polls every admitted command to terminal status. RESULT_PENDING is uncertain settlement, not successful execution. Live Hermes connectivity, acoustic assets and physical acceptance remain pending.

**Located source functions (not whole-feature acceptance)**

- OF-COMMAND-001:submit: Submit owner text or final admitted speech through the existing controller — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-COMMAND-001:status: Read accepted command through terminal owner status — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/commands/{command_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.commandStatus |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/conversations/{thread_id}/messages | VanGatewayClient.convergenceThreadMessages | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_PAGING_CONSUMER_PENDING | Latest bounded history with total count, has_more and next_before_message_id. Older pages use a message identity scoped to this thread; invalid, deleted and foreign cursors are refused. Equal-time messages are paged exactly once in chronological order. Atomic message/draft/follow-up writes and original projection scope preserve current owner thread state. Late canonical replies may complete archived history without reopening it. Follow-up promotion supplies a fresh owner prompt and never dispatches a command. |

### OF-MISSION-001 — Mission detail, activity and proof

Owner goal: Inspect what VAN did and why completion is credible.

Screens: van.work, van.work.mission, van.work.activity; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- goal/status
- constraints
- authority envelope in owner language
- activities
- execution identities
- evidence refs
- verification receipt

**Owner interactions and controls**

- open mission
- open evidence
- read timeline
- Open the exact selected mission, including terminal state
- Restore the exact selected mission/project/development context

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Exact mission selection, lifecycle timeline and evidence pointers are source wired. Physical process recreation and provider evidence acceptance remain unverified.

**Located source functions (not whole-feature acceptance)**

- OF-MISSION-001:selected-record: Open the exact selected mission, including terminal state — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-MISSION-001:restore-context: Restore the exact selected mission/project/development context — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/missions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missions |
| GET | /v1/missions/{mission_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.mission |
| GET | /v1/missions/{mission_id}/activity | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missionActivity |
| GET | /v1/missions/{mission_id}/evidence | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missionEvidence |
| GET | /v1/activity | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.activityFeed |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/missions/{mission_id}/graph | .UNWIRED | CANDIDATE_BACKEND_SOURCE_ANDROID_CONSUMER_PENDING | One durable mission snapshot: stable activity and dependency identities, owner-visible stage evidence, observed executor outcomes, explicit cycles/orphans/conflicting executor claims. Critical path is dependency count only; no invented duration or verified success. Payload limits refuse rather than omit work. |

### OF-MISSION-002 — Mission intervention

Owner goal: Stop or add direction to the existing mission.

Screens: van.work.mission, van.work.mission-control; required screens: van.work.mission, van.work.mission-control.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`.

**Information supplied**

- current mission state
- whether stopping is supported
- instruction acknowledgment vs execution
- current dispatch fence/generation
- exact immutable request hash and direction
- run-bound ordered worker acknowledgement
- existing command/action authority
- already-dispatched work may finish; process_stopped_verified=false

**Owner interactions and controls**

- cancel active mission
- message existing mission
- Cancel this active mission
- Record direction on this existing mission
- Request exact mission pause and independently recover its ordered control receipt
- Request exact mission resume and independently recover its ordered control receipt
- Request exact mission direction and independently recover its ordered control receipt

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Durable pause/resume/direction requests, exact recovery and run-bound ordered Hermes checkpoints are implemented. The fence prevents new gateway/browser/automation effects; it does not prove an already running external OS process stopped. Direction applies at the next admitted worker checkpoint without widening authority.

**Located source functions (not whole-feature acceptance)**

- OF-MISSION-002:cancel: Cancel this active mission — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-MISSION-002:message: Record direction on this existing mission — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-MISSION-002:pause: Request exact mission pause and independently recover its ordered control receipt — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-MISSION-002:resume: Request exact mission resume and independently recover its ordered control receipt — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-MISSION-002:direction: Request exact mission direction and independently recover its ordered control receipt — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/missions/{mission_id}/cancel | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.cancelMission |
| POST | /v1/missions/{mission_id}/message | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.messageMission |
| GET | /v1/missions/{mission_id}/control | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missionControl |
| GET | /v1/missions/{mission_id}/control/requests/{request_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missionControlRequest |
| POST | /v1/missions/{mission_id}/pause | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.writeMissionControl |
| POST | /v1/missions/{mission_id}/resume | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.writeMissionControl |
| POST | /v1/missions/{mission_id}/direction | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.writeMissionControl |

### OF-ATTENTION-001 — Attention triage

Owner goal: Handle or defer items by urgency.

Screens: van.attention, van.home; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- INFO/FOLLOW_UP/BLOCKER/URGENT
- source/project
- state
- created/updated/snooze time
- payload and destination

**Owner interactions and controls**

- open
- acknowledge
- snooze
- Read current attention
- Acknowledge an attention item
- Snooze an attention item for one hour

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Acknowledgement/snooze mutations and failures are visible; independent refresh and reminder navigation are wired. Final visual state/Rive redesign and physical notification acceptance remain pending.

**Located source functions (not whole-feature acceptance)**

- OF-ATTENTION-001:read: Read current attention — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-ATTENTION-001:ack: Acknowledge an attention item — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-ATTENTION-001:snooze: Snooze an attention item for one hour — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/attention | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.attention |
| POST | /v1/attention/{item_id}/ack | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.attentionAck |
| POST | /v1/attention/{item_id}/snooze | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.attentionSnooze |

### OF-DECISION-001 — Owner decisions and Needs You

Owner goal: Understand why owner input is needed and record a choice.

Screens: van.attention, van.work.mission, van.attention.decision; required screens: van.attention, van.work.mission, van.attention.decision.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- origin/project
- reason
- available choices
- risk/expected effect
- evidence
- expiry
- current status
- waiting missions
- listed stable choices and proposed labels
- exact owner note/revision/expiry
- REFERENCE_ONLY versus RECORDED_EVENT evidence
- immutable answer/recovery identity; grants_action_authority=false

**Owner interactions and controls**

- inspect evidence
- approve/select
- reject
- defer through supported attention controls
- add instruction to bound mission
- Resolve or reject a displayed owner decision with visible refusal and matching readback
- Read and answer an exact owner choice with evidence, expiry, note and immutable recovery identity

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Actual typed detail, listed choices, source-labelled references, expiry, immutable answer and recovery are wired. The first authorized answer and its learning fingerprint commit together. A choice is a judgment and does not substitute for cryptographic action approval.

**Located source functions (not whole-feature acceptance)**

- OF-DECISION-001:resolve: Resolve or reject a displayed owner decision with visible refusal and matching readback — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-DECISION-001:typed-choice: Read and answer an exact owner choice with evidence, expiry, note and immutable recovery identity — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/needs-you | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.needsYou |
| GET | /v1/decisions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.decisions |
| POST | /v1/decisions/{decision_id}/resolve | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.resolveDecision |
| GET | /v1/decisions/{decision_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.decision |
| POST | /v1/decisions/{decision_id}/answer | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.answerDecision |

### OF-APPROVAL-001 — Per-occurrence elevated action approval

Owner goal: Approve the exact consequential effect deliberately.

Screens: van.attention, van.approval.detail, van.work, van.approval.trading-ticket; required screens: van.attention, van.approval.detail, van.work, van.approval.trading-ticket.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- target
- action
- risk
- expected effect
- intent digest
- approval expiry
- biometric availability

**Owner interactions and controls**

- inspect intent
- approve with bound hardware-key biometric proof
- reject/dismiss
- Approve the displayed command occurrence with device biometrics
- Explicitly decline the displayed occurrence without authorizing an action

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Normalized exact action parameters, safe Gmail sender/recipient/subject/body digest preview, expiry and explicit discard are supplied. Fresh biometric proof binds those exact parameters; provider, device biometric and receipt acceptance remain pending.

**Located source functions (not whole-feature acceptance)**

- OF-APPROVAL-001:approve: Approve the displayed command occurrence with device biometrics — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-APPROVAL-001:discard: Explicitly decline the displayed occurrence without authorizing an action — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/authority | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.authorityDescriptor |
| GET | /v1/owner/google/gmail/drafts/{draft_id}/preview | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.googleGmailDraftPreview |

### OF-REMINDER-001 — Reminder lifecycle

Owner goal: Create a timed reminder and manage it.

Screens: van.reminders.manage, van.home; required screens: van.reminders.manage.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`.

**Information supplied**

- text
- due time/timezone
- project
- owner/Hermes source
- open/resolved/cancelled
- follow-up chain

**Owner interactions and controls**

- create using explicit/natural time
- resolve
- cancel
- inspect upcoming
- Read open reminders
- Create a reminder with explicit due time
- Resolve a reminder
- Cancel a reminder

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Natural due-time parsing uses UTC clock phrases; saved due times are displayed in phone local time. Device notification/delivery behavior remains unverified.

**Located source functions (not whole-feature acceptance)**

- OF-REMINDER-001:read: Read open reminders — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-REMINDER-001:create: Create a reminder with explicit due time — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-REMINDER-001:resolve: Resolve a reminder — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-REMINDER-001:cancel: Cancel a reminder — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/reminders | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | .UNWIRED |
| POST | /v1/reminders/parse | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.createReminder |
| GET | /v1/reminders | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.reminders |
| POST | /v1/reminders/{reminder_id}/resolve | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.resolveReminder |
| POST | /v1/reminders/{reminder_id}/cancel | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.cancelReminder |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/reminders | .UNWIRED | CANDIDATE_BACKEND_SOURCE_EXISTING_ANDROID_FLOW_ACCEPTANCE_PENDING | Original request-bound idempotency, atomic follow-ups with project/source retained, terminal-state conflicts and recoverable server publication. Attention preserves owner acknowledgement under concurrent reports. |
| POST /v1/reminders | .UNWIRED | CANDIDATE_BACKEND_SOURCE_EXISTING_ANDROID_FLOW_ACCEPTANCE_PENDING | Original request-bound idempotency, atomic follow-ups with project/source retained, terminal-state conflicts and recoverable server publication. Attention preserves owner acknowledgement under concurrent reports. |
| POST /v1/reminders/parse | .UNWIRED | CANDIDATE_BACKEND_SOURCE_EXISTING_ANDROID_FLOW_ACCEPTANCE_PENDING | Original request-bound idempotency, atomic follow-ups with project/source retained, terminal-state conflicts and recoverable server publication. Attention preserves owner acknowledgement under concurrent reports. |
| POST /v1/reminders/{reminder_id}/cancel | .UNWIRED | CANDIDATE_BACKEND_SOURCE_EXISTING_ANDROID_FLOW_ACCEPTANCE_PENDING | Original request-bound idempotency, atomic follow-ups with project/source retained, terminal-state conflicts and recoverable server publication. Attention preserves owner acknowledgement under concurrent reports. |
| POST /v1/reminders/{reminder_id}/resolve | .UNWIRED | CANDIDATE_BACKEND_SOURCE_EXISTING_ANDROID_FLOW_ACCEPTANCE_PENDING | Original request-bound idempotency, atomic follow-ups with project/source retained, terminal-state conflicts and recoverable server publication. Attention preserves owner acknowledgement under concurrent reports. |

### OF-MEMORY-001 — Owner facts CRUD

Owner goal: Tell VAN a fact, correct it or make it forget.

Screens: van.memory; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`.

**Information supplied**

- subject/predicate/value/scope
- provenance
- owner-confirmed vs inferred
- validity
- fact identity

**Owner interactions and controls**

- state fact
- correct via superseding statement
- forget one fact
- Remember or correct a scoped owner fact
- Withdraw a fact while retaining its history

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Per-fact withdrawal preserves historical revisions. Full destructive erasure uses the separately approved A4 command flow. Device behavior remains unverified.

**Located source functions (not whole-feature acceptance)**

- OF-MEMORY-001:state: Remember or correct a scoped owner fact — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-MEMORY-001:withdraw: Withdraw a fact while retaining its history — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/context/facts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.stateOwnerFact |
| DELETE | /v1/context/facts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.forgetOwnerFact |

### OF-MEMORY-002 — Full memory inspection and erasure

Owner goal: Read everything VAN holds and control retention.

Screens: van.memory, van.memory.privacy, van.memory.record; required screens: van.memory, van.memory.privacy, van.memory.record.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- store inventory and counts
- actual exported records
- provenance and confidence
- retention scope
- reasoning/evidence/strategic/learned data
- privacy-safe stable record identity
- declared/observed/inferred/mixed/unclassified provenance
- screened bounded fields/export
- complete stored-scope revision digest
- affected store counts/dependent identities
- retained work/audit and independent erased-identity readback

**Owner interactions and controls**

- inspect export
- forget a store
- forget all owner-derived memory
- inspect retention
- Inspect held stores and retention
- Request erasure of a listed store or all owner-derived memory
- Inspect paginated exact records, screened fields and declared/observed/inferred provenance
- Copy an independently reread screened bounded representation of the selected exact record
- Review affected record counts and request fresh biometric erasure of precisely that revision

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Per-record inspection, bounded screened export and exact immutable A4 erasure are supplied for all twelve forgettable stores. New/changed dependencies refuse stale approval; independent readback preserves unrelated rows. Direct DELETE remains refused. Physical privacy, biometric and restart acceptance remains unverified.

**Located source functions (not whole-feature acceptance)**

- OF-MEMORY-002:inventory: Inspect held stores and retention — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-MEMORY-002:erase: Request erasure of a listed store or all owner-derived memory — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-MEMORY-002:inspect-record: Inspect paginated exact records, screened fields and declared/observed/inferred provenance — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-MEMORY-002:export-record: Copy an independently reread screened bounded representation of the selected exact record — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-MEMORY-002:erase-record: Review affected record counts and request fresh biometric erasure of precisely that revision — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/context/memory | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextMemory |
| GET | /v1/context/export | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextExport |
| DELETE | /v1/context/memory | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.eraseContextMemory |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/commands/{command_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.commandStatus |
| GET | /v1/context/records | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextRecords |
| GET | /v1/context/records/{store}/{record_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextRecord |
| GET | /v1/context/records/{store}/{record_id}/export | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.exportContextRecord |
| GET | /v1/context/records/{store}/{record_id}/erasure-plan | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextRecordErasurePlan |

### OF-MEMORY-003 — History and conflict resolution

Owner goal: See changed beliefs and unresolved contradictions.

Screens: van.memory.history, van.memory; required screens: van.memory.history.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`.

**Information supplied**

- prior versions
- supersession/expiry
- conflicting values
- authority/source/time/scope

**Owner interactions and controls**

- open fact history
- inspect each conflict side
- state correction
- Inspect a fact revision history
- Inspect conflict sides and state an owner correction

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Conflict source failure is explicit and independent from fact loading. There is no arbitrary conflict-ID dismiss endpoint; an owner states a scoped correction through the existing fact writer.

**Located source functions (not whole-feature acceptance)**

- OF-MEMORY-003:history: Inspect a fact revision history — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-MEMORY-003:conflict: Inspect conflict sides and state an owner correction — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/context/history | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextHistory |
| GET | /v1/context/conflicts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextConflicts |
| POST | /v1/context/facts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.stateOwnerFact |

### OF-LEARNING-001 — Owner understanding and corrections

Owner goal: Inspect and correct what VAN believes about the owner.

Screens: van.understanding; required screens: van.understanding.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`.

**Information supplied**

- owner assertions
- OWNER_CONFIRMED/EVIDENCE_DERIVED/TENTATIVE/REJECTED/REVOKED
- vocabulary
- calibration
- cognitive complement
- owner meaning and operationalization
- examples and counterexamples
- optional existing project scope
- owner-authored provenance and exact committed readback
- separate inferred-trait confidence; declarations grant no execution authority

**Owner interactions and controls**

- confirm
- correct
- reject
- define or edit a scoped vocabulary term
- set an explicit domain collaboration instruction
- Inspect assertions, evidence, vocabulary and communication calibration
- Confirm an assertion
- Correct and supersede an assertion
- Reject an assertion
- Define or edit a scoped shared term with exact committed definition and owner provenance readback
- Record or edit an explicit domain collaboration instruction with matching owner-authored readback

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Owner hypothesis confirm/correct/reject, communication calibration and bounded explicit vocabulary/collaboration writers are wired. Fresh committed readback distinguishes owner-authored declarations from existing unconfirmed understanding; collaboration preferences preserve separate inferred traits. Declarations never mint execution grants, certify inferred psychological claims or independently prove future model response compliance. Physical owner-session, edit and readback acceptance remains pending.

**Located source functions (not whole-feature acceptance)**

- OF-LEARNING-001:read: Inspect assertions, evidence, vocabulary and communication calibration — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-001:confirm: Confirm an assertion — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-001:correct: Correct and supersede an assertion — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-001:reject: Reject an assertion — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-001:define-vocabulary: Define or edit a scoped shared term with exact committed definition and owner provenance readback — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-001:set-collaboration-preference: Record or edit an explicit domain collaboration instruction with matching owner-authored readback — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/understanding | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.understanding |
| POST | /v1/understanding/{assertion_id}/confirm | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.confirmUnderstanding |
| POST | /v1/understanding/{assertion_id}/correct | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.correctUnderstanding |
| POST | /v1/understanding/{assertion_id}/reject | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.rejectUnderstanding |
| GET | /v1/understanding/vocabulary | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerVocabulary |
| PUT | /v1/understanding/vocabulary | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.saveOwnerVocabulary |
| GET | /v1/understanding/complement/preferences | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerCollaborationPreferences |
| PUT | /v1/understanding/complement/preferences | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.saveOwnerCollaborationPreference |

### OF-LEARNING-002 — Adaptation review and rollback

Owner goal: Approve or reverse learned changes.

Screens: van.learning.adaptations; required screens: van.learning.adaptations.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`.

**Information supplied**

- effective changes
- awaiting-owner changes
- evidence
- scope/time
- reversibility
- reason

**Owner interactions and controls**

- confirm adaptation
- revert adaptation
- Read active and awaiting adaptations
- Confirm and read back an adaptation
- Revert a reversible adaptation

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Rollback exists only when the actual adaptation is reversible. Full device confirmation/readback remains unverified.

**Located source functions (not whole-feature acceptance)**

- OF-LEARNING-002:read: Read active and awaiting adaptations — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-002:confirm: Confirm and read back an adaptation — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-002:revert: Revert a reversible adaptation — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/understanding | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.understanding |
| POST | /v1/understanding/adaptation/{change_id}/confirm | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.confirmAdaptation |
| POST | /v1/understanding/adaptation/{change_id}/revert | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.revertAdaptation |

### OF-LEARNING-003 — Goals, decisions and learned strategies

Owner goal: Inspect continuity, conflicts and learning limits.

Screens: van.learning.goals; required screens: van.learning.goals.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- standing goals vs one-off requests
- goal tensions
- decision reasons/outcomes
- strategy verified/failure/inconclusive counts
- eval evidence
- external observations vs owner beliefs
- technology changes
- independent READY/NO_DATA/PARTIAL/DEGRADED producers
- bounded observations/comparisons and unmeasured counts
- timestamps/snapshot digest/source references
- candidate support/counterexamples/unknown outcomes
- original external trust and exact scope disagreement
- advisory inference with no execution grant

**Owner interactions and controls**

- inspect goal conflict
- review decision history
- inspect evidence/eval
- Inspect standing goals, constraints and tensions
- Read decision history and stated reasons
- Inspect bounded learned strategies
- Read external observations without inferred agreement
- Inspect technology evaluation state
- Inspect measured and unmeasured evaluation dimensions
- Inspect actual independent read-time producer status, bounds, timestamps and evidence
- Inspect bounded repeated-choice candidates, counterexamples and independent outcome references
- Compare an exact cited structured source claim with the current matching owner declaration

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Observed decision and structured external comparison producers are implemented with deterministic bounded evidence and recovery. Empty/unbound provider feeds remain NO_DATA or PARTIAL; candidates are advisory and neither declarations nor patterns prove future model compliance.

**Located source functions (not whole-feature acceptance)**

- OF-LEARNING-003:goals: Inspect standing goals, constraints and tensions — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-003:decisions: Read decision history and stated reasons — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-003:strategies: Inspect bounded learned strategies — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-003:reality: Read external observations without inferred agreement — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-003:radar: Inspect technology evaluation state — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-003:eval: Inspect measured and unmeasured evaluation dimensions — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-003:producer-state: Inspect actual independent read-time producer status, bounds, timestamps and evidence — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-003:observed-pattern: Inspect bounded repeated-choice candidates, counterexamples and independent outcome references — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-LEARNING-003:external-comparison: Compare an exact cited structured source claim with the current matching owner declaration — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/understanding/intents | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.standingIntents |
| GET | /v1/understanding/decisions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.decisionHistory |
| GET | /v1/strategies | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.learnedStrategies |
| GET | /v1/external-reality | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.externalReality |
| GET | /v1/technology-radar | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.technologyRadar |
| GET | /v1/eval | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.evalReport |
| GET | /v1/understanding/learning/producers | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.learningProducers |

### OF-PROJECT-001 — Project inventory and detail

Owner goal: Know project health, current work and next decisions.

Screens: van.projects, van.projects.detail; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- authoritative project ID/name
- phase/mission
- health
- active work
- attention
- recent update
- truth provenance
- decisions/blockers

**Owner interactions and controls**

- open project
- open bound work/attention
- context-bound command
- Read project records with independent source health and concrete record navigation

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Project truth, work, attention, decisions and context preserve independent source failures and read timestamps. Missing health/phase stays UNKNOWN; mission controls, next actions and memory provenance have concrete navigation.

**Located source functions (not whole-feature acceptance)**

- OF-PROJECT-001:independent-read: Read project records with independent source health and concrete record navigation — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/projects | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.projects |
| GET | /v1/projects/{project_id}/truth | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.projectTruth |
| GET | /v1/missions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missions |
| GET | /v1/attention | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.attention |
| GET | /v1/context/export | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.contextExport |

### OF-PROJECT-002 — Strategic rationale memory

Owner goal: Remember why choices were made and rejected.

Screens: van.projects.detail, van.projects.rationale; required screens: van.projects.rationale.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`.

**Information supplied**

- rationale
- tried/rejected approaches
- evidence refs
- separation from repository truth

**Owner interactions and controls**

- inspect rationale
- record owner rationale
- Inspect project rationale, past rejected strategies and provenance
- Record owner-authored rationale and verify same-project readback

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Project rationale is independently readable and writable with matching receipt and readback. Failed mutation retains draft and requires a fresh read; no automatic retry/idempotency promise. Project Truth remains separate internal repository authority. Handset/backend integration is unverified.

**Located source functions (not whole-feature acceptance)**

- OF-PROJECT-002:read: Inspect project rationale, past rejected strategies and provenance — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-PROJECT-002:record: Record owner-authored rationale and verify same-project readback — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/projects/{project_id}/strategic-memory | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.projectStrategicMemory |
| POST | /v1/projects/{project_id}/strategic-memory | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.recordProjectRationale |

### OF-AUTHORITY-001 — Permissions and autonomy

Owner goal: Know and revoke what VAN may do unprompted.

Screens: van.permissions, van.autonomy, van.permissions.grant; required screens: van.permissions, van.autonomy, van.permissions.grant.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `OWNER_CONTROLS_SOURCE_IMPLEMENTED`.

**Information supplied**

- standing grants
- origin/last use/expiry
- domain earned/owner/effective ceilings
- suspensions
- policy
- supported domains and levels
- exact normalized ceiling change and expiry
- independent operation-specific stored ceiling readback
- supported action contracts/exact parameter scope
- expiry/max uses and remaining-use enforcement
- fresh native approval/separate service authority
- stored grant/use/revoke readback

**Owner interactions and controls**

- inspect grant
- revoke grant
- inspect authority descriptor and readiness
- select supported domain and S0..S4 owner ceiling
- review and biometrically approve exact sealed ceiling change
- Inspect standing permissions
- Withdraw this standing permission
- Inspect earned, owner and effective autonomy ceilings
- Inspect action gates
- Inspect automatic capability readiness
- Choose a supported domain and owner autonomy ceiling, then approve the exact sealed change with biometrics
- Select a supported action and review bounded exact scope, expiry and maximum uses before A4 approval
- Inspect the exact stored grant and independent use/remaining-scope readback; revoke it explicitly

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Exact owner permission creation, inspection/use enforcement and revocation are implemented alongside S0..S4 domain ceilings. Unsupported actions/scopes refuse; consent never creates service authority or removes fresh native approval requirements.

**Located source functions (not whole-feature acceptance)**

- OF-AUTHORITY-001:read: Inspect standing permissions — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-AUTHORITY-001:revoke: Withdraw this standing permission — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-AUTHORITY-001:autonomy: Inspect earned, owner and effective autonomy ceilings — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-AUTHORITY-001:authority: Inspect action gates — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-AUTHORITY-001:readiness: Inspect automatic capability readiness — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-AUTHORITY-001:set-domain-ceiling: Choose a supported domain and owner autonomy ceiling, then approve the exact sealed change with biometrics — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-AUTHORITY-001:grant-exact-consent: Select a supported action and review bounded exact scope, expiry and maximum uses before A4 approval — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-AUTHORITY-001:inspect-consent-use: Inspect the exact stored grant and independent use/remaining-scope readback; revoke it explicitly — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/permissions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.permissions |
| POST | /v1/permissions/{grant_id}/revoke | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.revokePermission |
| GET | /v1/autonomy | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.autonomy |
| GET | /v1/authority | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.authorityDescriptor |
| GET | /v1/capabilities/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.capabilityStatus |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/permissions/contracts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.permissionContracts |
| GET | /v1/permissions/grants/{grant_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.permissionGrant |

### OF-GOOGLE-001 — Google account planes and revocation

Owner goal: Know which Google capabilities work and disconnect access.

Screens: van.connected; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- Workspace/Gemini/Cloud/consumer planes
- identity aliases
- scope
- readiness evidence
- degradation
- capability availability

**Owner interactions and controls**

- inspect plane
- disconnect owner Workspace OAuth
- follow supported consent restoration
- Inspect actual Google connection and perform scoped Workspace revocation with fresh readback

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Actual Google connection status, plane and capability evidence are read independently. Workspace-only revoke requires receipt plus fresh readback; owner registration alone does not imply connected provider credentials. Live provider binding and revoke acceptance remain pending.

**Located source functions (not whole-feature acceptance)**

- OF-GOOGLE-001:connection-readback: Inspect actual Google connection and perform scoped Workspace revocation with fresh readback — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/google/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.googleStatus |
| GET | /v1/google/planes | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.googlePlanes |
| GET | /v1/google/mesh | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.googleMesh |
| GET | /v1/google/capabilities | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | .UNWIRED |
| POST | /v1/google/owner-revoke | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.googleOwnerRevoke |

### OF-GOOGLE-002 — Workspace owner operations

Owner goal: Use mail, calendar, Drive, contacts and tasks through VAN.

Screens: van.work, van.connected; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- safe search results
- draft/send state
- calendar time/details
- Drive provenance
- contact resolution
- tasks
- effect verification

**Owner interactions and controls**

- search mail/Drive
- draft mail
- send only with fresh approval
- read/insert/reschedule calendar
- resolve contact
- list tasks
- invoke declared typed action

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Gmail MIME/header validation and immutable draft preview bind exact content before A4 approval. Gmail send success requires fresh provider sent-content readback; an admitted source draft is retained when outcome is unobserved. Google credentials, grants and real provider effects require live acceptance.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/google/gmail/search | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:google | .UNWIRED |
| POST | /v1/google/gmail/draft | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:google | .UNWIRED |
| POST | /v1/google/gmail/send | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:google | .UNWIRED |
| GET | /v1/google/calendar/agenda | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:google | .UNWIRED |
| POST | /v1/google/calendar/reschedule | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:google | .UNWIRED |
| GET | /v1/google/drive/search | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:google | .UNWIRED |
| GET | /v1/google/contacts/resolve | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:google | .UNWIRED |
| GET | /v1/google/tasks | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:google | .UNWIRED |
| POST | /v1/google/actions/execute | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:google | .UNWIRED |
| GET | /v1/owner/google/gmail/drafts/{draft_id}/preview | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.googleGmailDraftPreview |

**Service dependencies (not Android owner access)**

- VE-c225e5628af2
- VE-a4decae315ba
- VE-4c628c3e5a78
- VE-23aaa05d4d7b
- VE-351f73de9c2b
- VE-a980fcccde77
- VE-79d86c59cb7d
- VE-a760f5ffdf00
- VE-592e2db652f5

### OF-KNOWLEDGE-001 — Research and knowledge providers

Owner goal: Obtain citable knowledge with explicit provider readiness.

Screens: van.work, van.connected, van.knowledge.research, van.knowledge.sources; required screens: van.knowledge.research.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- VEKL/Obsidian/Notebook/research readiness
- source/trust/time
- evidence
- notebook records
- research outcomes

**Owner interactions and controls**

- ask through command controller
- inspect citations
- inspect readiness
- request declared notebook mutation
- Inspect owner-safe research records
- Submit only an advertised exact owner command
- Inspect provider evidence, query citations and operations

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Exa and direct private-knowledge producers use actual bounded transport and truthful failures. TLS identities, credentials, egress and provider configuration remain deployment prerequisites; read availability is distinct from verified owner effect.

**Located source functions (not whole-feature acceptance)**

- OF-KNOWLEDGE-001:projection-ownerResearch: Inspect owner-safe research records — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-KNOWLEDGE-001:signed-ownerResearch: Submit only an advertised exact owner command — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-KNOWLEDGE-001:knowledge: Inspect provider evidence, query citations and operations — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/runtime/knowledge/status | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| POST | /v1/runtime/knowledge/vekl/query | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| POST | /v1/runtime/knowledge/obsidian/query | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| GET | /v1/runtime/knowledge/notebook/enterprise/recent | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| GET | /v1/runtime/knowledge/notebook/enterprise/{notebook_id} | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| POST | /v1/runtime/knowledge/notebook/consumer/ask | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| POST | /v1/runtime/knowledge/actions/execute | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| GET | /v1/runtime/research/status | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| POST | /v1/runtime/research/search | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| GET | /v1/owner/research | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerResearch |
| GET | /v1/owner/knowledge | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerKnowledge |

**Service dependencies (not Android owner access)**

- VE-24c007113944
- VE-0b6118c297e7
- VE-d40e4030951b
- VE-4c9ebe3b29bf
- VE-7baac04c84f3
- VE-ca42b4c1336c
- VE-ff3ae0a0f3c1
- VE-341c2ac1a332
- VE-7c92759db8dd

### OF-AUTOMATION-001 — Automation and standing intents

Owner goal: Inspect bounded automation and disable standing work.

Screens: van.work.browser, van.automation.library, van.automation.intent, van.automation.plan; required screens: van.work.browser, van.automation.library, van.automation.intent, van.automation.plan.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- capability/template readiness
- workflow mission/run
- authority scope
- effect receipts
- standing intent
- repair status
- supported closed IR/DSL and deployment requirements
- immutable candidate request/artifact/revision
- pinned admitted helper/parent manifests and inputs
- selected/skipped/refused step receipts
- preconditions/independent target predicates
- actual provider/worker configuration status

**Owner interactions and controls**

- request automation through controller
- inspect run/evidence
- disable standing intent through supported owner command
- Inspect owner-safe automation records
- Submit only an advertised exact owner command
- Observe supported canonical workflow runs and independently stored local effects
- Prepare a bounded typed IR candidate, recover the exact artifact and review its declared deployment limitations
- Review deterministic supported branches, mappings, preconditions and independent success predicates
- Request only an admitted immutable artifact with pinned inputs and inspect actual run/step evidence

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Owner candidate/recovery, bounded branches/mappings/predicates and exact admitted run inspection are implemented. Actual n8n helpers, credentials, current manifests and provider canaries must be bound/read back on the authorized host. Unsupported arbitrary code and unsealed external capability writes remain refused by the closed contract.

**Located source functions (not whole-feature acceptance)**

- OF-AUTOMATION-001:projection-ownerAutomation: Inspect owner-safe automation records — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-AUTOMATION-001:signed-ownerAutomation: Submit only an advertised exact owner command — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-AUTOMATION-001:canonical-runtime: Observe supported canonical workflow runs and independently stored local effects — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-AUTOMATION-001:owner-plan: Prepare a bounded typed IR candidate, recover the exact artifact and review its declared deployment limitations — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-AUTOMATION-001:bounded-dsl: Review deterministic supported branches, mappings, preconditions and independent success predicates — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-AUTOMATION-001:exact-run: Request only an admitted immutable artifact with pinned inputs and inspect actual run/step evidence — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/automation/health | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:runtime | .UNWIRED |
| GET | /v1/automation/templates | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:automation | .UNWIRED |
| GET | /v1/automation/capabilities/{capability_id} | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:automation | .UNWIRED |
| POST | /v1/automation/standing-intents | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:automation | .UNWIRED |
| POST | /v1/automation/standing-intents/{intent_id}/disable | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:automation | .UNWIRED |
| GET | /v1/automation/temporal/{workflow_id} | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:automation | .UNWIRED |
| GET | /v1/owner/automation | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerAutomation |
| POST | /v1/automation/worker/step | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:automation_worker | None.None |
| GET | /v1/owner/automation/contracts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationContracts |
| POST | /v1/owner/automation/plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.proposeAutomationPlan |
| GET | /v1/owner/automation/plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationPlans |
| GET | /v1/owner/automation/plans/{artifact_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationPlan |
| GET | /v1/owner/automation/requests/{idempotency_key} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationPlanRequest |
| GET | /v1/owner/automation/runs/{run_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.automationRun |

**Service dependencies (not Android owner access)**

- VE-af180630c30f
- VE-7c1adc62cbe1
- VE-faa9efd04c69
- VE-69f29d84324b
- VE-ad21df37dc16
- VE-96ecedfcad3a
- VE-9529af1a7c0e

### OF-BROWSER-001 — Browser task supervision and escalations

Owner goal: Review browser work and intervene when it needs the owner.

Screens: van.work.browser, van.work.browser.tasks, van.work.browser.escalations, van.work.browser.policy, van.browser.outcome, van.browser.interactive, van.browser.action-plan; required screens: van.work.browser, van.work.browser.tasks, van.work.browser.escalations, van.work.browser.policy, van.browser.outcome, van.browser.interactive, van.browser.action-plan.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- task/status
- policy/domain limits
- escalations
- evidence
- mission link
- profile/control lease
- current native target/hostname/profile/producer epoch
- owner-prepared task/immutable plan
- exact effect parameters/observed predicates
- claimed/uncertain/observed result without re-actuation

**Owner interactions and controls**

- inspect task evidence
- resolve escalation decision
- open live browser
- Inspect a browser task outcome without claiming task-goal verification
- Prepare an actual browser task, review exact click/fill effects and observe the sealed result without re-actuation

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Bounded browser mutation plans, click/fill results and exact cancellation fencing are implemented. Current native target/profile/producer and private stream/control hosts must be observed. A draft or successful transport does not prove mutation, closure or provider effect; arbitrary unsealed mutation remains refused.

**Located source functions (not whole-feature acceptance)**

- OF-BROWSER-001:outcome: Inspect a browser task outcome without claiming task-goal verification — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-001:immutable-effect-plan: Prepare an actual browser task, review exact click/fill effects and observe the sealed result without re-actuation — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/browser/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserStatus |
| GET | /v1/browser/policy | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserPolicy |
| GET | /v1/browser/tasks | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserTasks |
| GET | /v1/browser/tasks/{task_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | .UNWIRED |
| GET | /v1/browser/tasks/{task_id}/evidence | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserEvidence |
| GET | /v1/browser/escalations | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserEscalations |
| POST | /v1/decisions/{decision_id}/resolve | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.resolveDecision |
| GET | /v1/owner/browser/tasks/{task_id}/outcome | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerBrowserOutcome |
| GET | /v1/browser/interactive-sessions/{session_id}/action-plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserActionPlans |
| POST | /v1/browser/interactive-sessions/{session_id}/action-plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.createBrowserActionPlan |
| GET | /v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserActionPlan |
| POST | /v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id}/cancel | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.cancelBrowserActionPlan |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/browser/tasks/{task_id}/resume-contract | .UNWIRED | BACKEND_SOURCE_TESTED_ANDROID_CONSUMER_PENDING | One continuation of the same waiting task; advisory decisions grant no authority |

### OF-BROWSER-002 — Interactive native browser

Owner goal: Browse the real remote Chromium session from the phone.

Screens: van.browser.interactive, van.work.browser.sessions; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- omnibox
- active tab and tab list
- native keyboard
- connection/control indicators
- lease
- viewport revision
- audio
- session persistence

**Owner interactions and controls**

- navigate/search
- tabs
- back/forward/reload
- tap/swipe/fling/pinch/long press
- open shortcut
- suspend/end session
- Confirm the current browser viewport
- Pause this browser session
- Request remote browser closure and distinguish local disconnect
- Read current target/tab inventory and safe session event history
- Resume the exact admitted session with fresh readback

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Actual CDP control and WebRTC signaling/media producers are implemented. Target/tab/event inventory, aspect-fit touch mapping, Android key/IME bridge and current viewport/media-epoch guards are wired. Local media disconnect does not prove remote closure; physical negotiation, resize, takeover and producer host acceptance remain pending.

**Located source functions (not whole-feature acceptance)**

- OF-BROWSER-002:viewport: Confirm the current browser viewport — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-002:pause: Pause this browser session — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-002:close: Request remote browser closure and distinguish local disconnect — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-002:inventory: Read current target/tab inventory and safe session event history — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-002:resume: Resume the exact admitted session with fresh readback — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/browser/interactive-sessions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserCreate |
| GET | /v1/browser/interactive-sessions/{session_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserRead |
| POST | /v1/browser/interactive-sessions/{session_id}/stream-grant | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserStreamGrant |
| POST | /v1/browser/interactive-sessions/{session_id}/heartbeat | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserHeartbeat |
| POST | /v1/browser/interactive-sessions/{session_id}/viewport | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserProposeViewport |
| POST | /v1/browser/interactive-sessions/{session_id}/viewport/ack | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserAckViewport |
| POST | /v1/browser/interactive-sessions/{session_id}/suspend | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserSuspend |
| DELETE | /v1/browser/interactive-sessions/{session_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserEnd |
| GET | /v1/browser/interactive-sessions/{session_id}/tabs | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserTabs |
| GET | /v1/browser/interactive-sessions/{session_id}/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserEvents |
| POST | /v1/browser/interactive-sessions/{session_id}/resume | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserResume |

### OF-BROWSER-003 — Owner/Hermes takeover and page assistance

Owner goal: Ask VAN about the visible page and keep immediate owner control.

Screens: van.browser.interactive, van.browser.action-plan; required screens: van.browser.interactive, van.browser.action-plan.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- lease owner/epoch
- delegated goal and step budget
- active target
- analysis/voice response
- takeover status
- foreground A3 task preparation
- fresh native biometric A4 plan approval
- current profile_mutation_permitted/gateway_authorized_only posture
- exact click/fill parameters/step observations
- cancellation fence/retained result

**Owner interactions and controls**

- take control by touch
- delegate bounded work
- ask about visible page
- voice control
- Take control only after matching fresh owner lease and generation
- Delegate the exact current lease to an existing mission and require authoritative readback
- Prepare an actual browser task, review exact click/fill effects and observe the sealed result without re-actuation

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Bounded browser mutation plans, click/fill results and exact cancellation fencing are implemented. Current native target/profile/producer and private stream/control hosts must be observed. A draft or successful transport does not prove mutation, closure or provider effect; arbitrary unsealed mutation remains refused.

**Located source functions (not whole-feature acceptance)**

- OF-BROWSER-003:take-control: Take control only after matching fresh owner lease and generation — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-003:delegate-control: Delegate the exact current lease to an existing mission and require authoritative readback — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-003:immutable-effect-plan: Prepare an actual browser task, review exact click/fill effects and observe the sealed result without re-actuation — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/browser/interactive-sessions/{session_id}/take-control | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserTakeControl |
| POST | /v1/browser/interactive-sessions/{session_id}/delegate-control | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserDelegateControl |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/browser/interactive-sessions/{session_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserRead |
| GET | /v1/browser/interactive-sessions/{session_id}/action-plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserActionPlans |
| POST | /v1/browser/interactive-sessions/{session_id}/action-plans | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.createBrowserActionPlan |
| GET | /v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserActionPlan |
| POST | /v1/browser/interactive-sessions/{session_id}/action-plans/{plan_id}/cancel | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.cancelBrowserActionPlan |

### OF-BROWSER-004 — Downloads, uploads and clipboard

Owner goal: Transfer files under explicit owner control.

Screens: van.browser.interactive, van.browser.downloads, van.browser.file-provider; required screens: van.browser.interactive, van.browser.downloads, van.browser.file-provider.

Wiring: `EXTERNAL_CONTRACT_OR_ASSET_REQUIRED`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- owned download/chooser identifiers and current target
- producer and media epoch
- filename/type/size/hash and safe origin metadata
- pending/failed/available byte effect status
- host deletion acknowledgement
- explicit clipboard effect receipt
- exact file hash/size/type/producer epoch
- safe inert local preview
- bounded source-labelled native analysis
- exact operation result/recovery
- external provider bound/executable/qualified status; unbound imports unavailable
- immutable provider request/idempotency key/digest/deadline
- current exact provider/owner/project destination
- fresh native A4 challenge and approval state
- actual one-use provider claim and independent persisted-byte receipt
- explicit OBSERVED_EXTERNAL_EFFECT versus STILL_UNKNOWN observation; original canonical outcome/fence retained
- UNKNOWN remains read-only; no content execution or truth promotion

**Owner interactions and controls**

- review host downloads
- save exact download to phone
- choose and upload a phone document for current browser chooser
- explicit copy browser selection
- explicit paste phone clipboard
- remove eligible host record and inspect physical cleanup acknowledgement
- Review actual owned-session download records
- Remove an eligible host download record and confirm exact DELETED readback
- Save verified browser download bytes through the Android Storage Access Framework
- Choose and upload a bounded phone document only for an explicit current browser chooser
- Explicitly copy browser selection or paste phone clipboard under current owner control
- Inspect native file analysis and exact import operation readbacks, with bound hash/epoch and provider limits
- Open independently verified selected bytes in VAN's bounded inert native viewer
- Read current archive/candidate provider capability, exact admitted destination and unavailable/refused states
- Prepare and independently recover the exact immutable file/destination request before any provider effect
- Approve the exact file request with fresh native A4 and inspect separately admitted provider claim and persisted-byte evidence
- Explicitly check an already claimed external byte receipt after an uncertain effect without resubmitting or changing the original outcome

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Native file inspection, inert preview, bounded analysis and exact readback are wired. Owner provider catalog/draft/recovery, canonical native A4 admission, separate attested mTLS claim/introspection and independently verified byte receipts are implemented. The proposed Oracle/VEKL production target remains unbound/unqualified; defaults are UNAVAILABLE and current capability/bindings must be supplied before owner preparation/execution. Host cleanup and actual phone byte/provider effects still require independent acceptance.

**Located source functions (not whole-feature acceptance)**

- OF-BROWSER-004:review-downloads: Review actual owned-session download records — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-004:remove-download-record: Remove an eligible host download record and confirm exact DELETED readback — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-004:save-to-phone: Save verified browser download bytes through the Android Storage Access Framework — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-004:upload-from-phone: Choose and upload a bounded phone document only for an explicit current browser chooser — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-004:explicit-clipboard: Explicitly copy browser selection or paste phone clipboard under current owner control — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-004:native-file-operation: Inspect native file analysis and exact import operation readbacks, with bound hash/epoch and provider limits — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-004:open-in-van: Open independently verified selected bytes in VAN's bounded inert native viewer — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-004:external-file-contract: Read current archive/candidate provider capability, exact admitted destination and unavailable/refused states — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-004:provider-draft: Prepare and independently recover the exact immutable file/destination request before any provider effect — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-004:provider-admission: Approve the exact file request with fresh native A4 and inspect separately admitted provider claim and persisted-byte evidence — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-BROWSER-004:provider-observation: Explicitly check an already claimed external byte receipt after an uncertain effect without resubmitting or changing the original outcome — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/browser/interactive-sessions/{session_id}/downloads | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserDownloads |
| DELETE | /v1/browser/interactive-sessions/{session_id}/downloads/{download_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserDeleteDownload |
| POST | /v1/browser/interactive-sessions/{session_id}/transfer-grants | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.interactiveBrowserTransferGrant |
| GET | /v1/browser/interactive-sessions/{session_id}/downloads/{download_id}/operations | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileOperations |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-contracts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderContracts |
| POST | /v1/browser/interactive-sessions/{session_id}/file-provider-requests | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.createBrowserFileProviderRequest |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-requests | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderRequests |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderRequest |
| POST | /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/cancel | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.cancelBrowserFileProviderRequest |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| POST | /v1/browser/artifact-provider/admissions/{admission_id}/introspect | ATTESTED_ARTIFACT_PROVIDER_SERVICE_ONLY / ATTESTED_ARTIFACT_PROVIDER:CURRENT_PINNED_MTLS_AND_SIGNED_EXACT_ADMISSION | None.None |
| POST | /v1/browser/artifact-provider/admissions/{admission_id}/claim | ATTESTED_ARTIFACT_PROVIDER_SERVICE_ONLY / ATTESTED_ARTIFACT_PROVIDER:CURRENT_PINNED_MTLS_AND_SIGNED_EXACT_ADMISSION | None.None |
| GET | /v1/browser/interactive-sessions/{session_id}/file-provider-requests/{request_id}/observation | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.browserFileProviderObservation |

**Service dependencies (not Android owner access)**

- VE-f6079fb6d1b5
- VE-d8b7224e92a0

### OF-VOICE-001 — Wake, recognition, interruption and spoken result

Owner goal: Use Hey Van and receive an audible safe answer.

Screens: van.voice.turn, van.settings.voice; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- wake/ack/listening
- partial/final transcript
- routing/queued status
- response segments
- speaking/heard cursor
- ASR/TTS asset readiness
- recognition errors
- actual generic bundle/install/runtime readiness
- selected recognition/TTS engine and offline fallback
- actual EnergyVadGate endpointing for local PCM turns
- permission/no-speech/timeout/cancel/late-final states
- declared assets are separate from prepared usable models and acoustic accuracy
- actual owner speaker enrollment controls available; owner profile absent until real capture
- generic models grant no owner identity or action authority

**Owner interactions and controls**

- start/end listening
- stop speaking
- barge in
- correct/reissue
- continue same mission
- repeat cached answer
- Cancel unsubmitted speech and reject late recognition results
- Keep the same owner envelope and acknowledgment boundary on authenticated POST/SSE fallback
- Automatically admit an installed offline Android voice and refuse network-required/unavailable fallback
- Use automatically installed generic local acoustic assets and retain honest engine/fallback readiness without phone configuration
- End the selected local Sherpa recognition turn on actual EnergyVadGate speech/silence or explicit bounded no-speech/maximum-duration state

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Generic APK acoustic delivery, exact integrity/atomic installation, selected local recognition and actual EnergyVadGate endpointing are source implemented. Dedicated actual owner enrollment/replace/readiness/erasure source is supplied; no owner profile or recording has been fabricated. Runtime readiness is observable and separate from acoustic accuracy: native constructors/decode smoke do not qualify wake/ASR/speaker performance. Physical acoustic, model performance and signed owner-release qualification remain pending.

**Located source functions (not whole-feature acceptance)**

- OF-VOICE-001:cancel-turn: Cancel unsubmitted speech and reject late recognition results — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-VOICE-001:fallback-carrier: Keep the same owner envelope and acknowledgment boundary on authenticated POST/SSE fallback — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-VOICE-001:automatic-offline-tts: Automatically admit an installed offline Android voice and refuse network-required/unavailable fallback — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-VOICE-001:embedded-generic-voice: Use automatically installed generic local acoustic assets and retain honest engine/fallback readiness without phone configuration — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-VOICE-001:bounded-local-endpointing: End the selected local Sherpa recognition turn on actual EnergyVadGate speech/silence or explicit bounded no-speech/maximum-duration state — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| POST | /v1/session/open | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.sessionOpen |
| POST | /v1/session/resume | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.sessionResume |
| GET | /v1/session/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.sessionStatus |
| POST | /v1/session/messages | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.sessionUpstream |
| GET | /v1/session/events-stream | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.sessionDownstream |
| WEBSOCKET | /v1/session/ws | DIRECT_OWNER_ROUTE / PAIRED_DEVICE_TOKEN_AND_OWNED_SESSION | VanGatewayClient.sessionSocketUrl |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| POST /v1/voice/responses | VanGatewayClient.openSpokenResult | CANDIDATE_SOURCE_TESTED_NATIVE_ACCEPTANCE_PENDING | Exact result reference and playback request; actual heard cursor; local-first interruption; current owner voice context |
| GET /v1/voice/streams/{stream_id} | VanGatewayClient.speechStream | CANDIDATE_SOURCE_TESTED_NATIVE_ACCEPTANCE_PENDING | Exact result reference and playback request; actual heard cursor; local-first interruption; current owner voice context |
| POST /v1/voice/streams/{stream_id}/cursors | VanGatewayClient.reportSpeechCursors | CANDIDATE_SOURCE_TESTED_NATIVE_ACCEPTANCE_PENDING | Exact result reference and playback request; actual heard cursor; local-first interruption; current owner voice context |
| POST /v1/voice/streams/{stream_id}/interrupt | VanGatewayClient.interruptSpeech | CANDIDATE_SOURCE_TESTED_NATIVE_ACCEPTANCE_PENDING | Exact result reference and playback request; actual heard cursor; local-first interruption; current owner voice context |

### OF-VOICE-002 — Speech personalization

Owner goal: Correct pronunciation/recognition and control adaptation.

Screens: van.settings.voice, van.settings.speaker-profile; required screens: van.settings.voice, van.settings.speaker-profile.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- personal correction record
- speaker profile status
- adaptation evidence
- local asset readiness
- generic speaker model readiness separate from authenticated profile presence
- current full owner/device/hardware/approval binding
- dedicated local consent operation/revision/model/freshness
- current clip phrase/index/energy quality/progress
- encrypted normalized embedding and retained consent metadata; no stored raw PCM
- inconclusive stale/unbound speaker evidence; no action authority
- exact offline erasure using genuine local keys and absence readback

**Owner interactions and controls**

- capture correction
- inspect/reset personal speech model when supported
- Enroll or replace the exact device-local owner profile using dedicated biometric consent and three actual microphone clips
- Read local profile/model readiness and permit revocable similarity evidence only for the exact fresh current owner binding
- Erase precisely the retained encrypted profile after dedicated biometric consent, including when the backend is unreachable

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Local enrollment/replace/readiness/erasure controls and generic native extraction are source implemented. Actual owner capture/profile, speaker discrimination, microphone permissions/audio arbitration, device cryptography and physical acoustic quality remain unverified. Speaker similarity is revocable evidence only; owner speech corrections remain explicit declarations and cannot confer action authority.

**Located source functions (not whole-feature acceptance)**

- OF-VOICE-002:local-owner-enrollment: Enroll or replace the exact device-local owner profile using dedicated biometric consent and three actual microphone clips — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-VOICE-002:local-profile-readback: Read local profile/model readiness and permit revocable similarity evidence only for the exact fresh current owner binding — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-VOICE-002:local-profile-erasure: Erase precisely the retained encrypted profile after dedicated biometric consent, including when the backend is unreachable — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

### OF-OVERLAY-001 — Floating assistant and contextual workboard

Owner goal: Access current work and immediate controls while using other apps.

Screens: van.floating; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- durable activity/health/attention/speech
- context/chat/voice/approval/task mode
- compact/expanded/maximized/minimized/docked state

**Owner interactions and controls**

- single tap board toggle
- double tap Command Centre
- long press quick controls
- drag/dock
- bottom-X dismiss
- minimize/restore
- context command/voice

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Shared voice and trading navigation producers are wired. Final gesture/board/Rive visual redesign and physical overlay/OS-permission acceptance remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/attention | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.attention |
| GET | /v1/missions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.missions |
| GET | /v1/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.events |

### OF-NOTIFICATION-001 — Notification capture and privacy policy

Owner goal: Choose which apps VAN reads and when it interrupts.

Screens: van.settings.notifications; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- observed app inventory
- NORMAL/PRIORITY/MUTE
- quiet hours
- listener permission
- redaction/deduplication
- attention result

**Owner interactions and controls**

- set app policy
- configure quiet hours
- open Android listener permission
- inspect generated attention
- Review and change explicit policy for apps actually observed

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Observed applications and explicit encrypted device-local policy remain distinct; muted applications stay visible. OS listener consent, real delivery and physical acceptance remain pending. No cross-device policy-sync contract is supplied.

**Located source functions (not whole-feature acceptance)**

- OF-NOTIFICATION-001:observed-apps: Review and change explicit policy for apps actually observed — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/context/ingest | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ingestCapturedContext |
| POST | /v1/notifications/ingest | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | .UNWIRED |
| GET | /v1/attention | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.attention |

### OF-SHARE-001 — Share to VAN

Owner goal: Bring external text/images/files into context safely.

Screens: van.work, van.floating, van.share.intake; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- shared payload/provenance/type
- capture delivery
- target context/mission
- owner confirmation boundary

**Owner interactions and controls**

- Android share intake
- inspect imported context
- explicit separate owner instruction

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Share intake feeds the owner review/controller path while external content remains DATA. Target-selection, degraded/offline presentation and physical Android share-sheet acceptance remain pending redesign/acceptance work.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/context/ingest | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ingestCapturedContext |

### OF-PROVISION-001 — Owner device onboarding and identity

Owner goal: Use the app only after a supported readiness journey.

Screens: van.settings, van.devices.provision, van.onboarding, van.provisioning; required screens: van.devices.provision.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- permissions
- signed provisioning status
- paired device
- bound hardware identity
- overlay/listener/mic/biometric
- gateway connectivity
- selected Google consent

**Owner interactions and controls**

- Grant Android permissions
- Inspect automatic readiness
- Restore through supported installer

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Automatic signed owner-core bootstrap/recovery requires no in-app backend or Hermes connection settings. Backend, product Hermes profile van and direct phone ingress colocate on van-trading-core under CORE_ONLY_V2; dial-control supplies native Artemis/development services. Oracle Admin is excluded. Private TLS ingress, release signer/trust/bootstrap binding, owner installer delivery and physical attestation/connectivity remain unqualified.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/devices/pair | DIRECT_OWNER_ROUTE / PAIRING_TICKET_AND_ATTESTED_BOUND_DEVICE_PROOF; EXACT_RECOVERY_WITH_CLIENT_TOKEN | VanGatewayClient.pairThisDevice |
| POST | /v1/devices/bootstrap/challenge | DIRECT_OWNER_ROUTE / SINGLE_USE_BOOTSTRAP_TOKEN | VanGatewayClient.bindThisDevice.challenge |
| POST | /v1/devices/bootstrap/attest | DIRECT_OWNER_ROUTE / SINGLE_USE_BOOTSTRAP_TOKEN_AND_PINNED_ATTESTATION_CHAIN_AND_FRESH_DEVICE_PROOF | VanGatewayClient.bindThisDevice.attest |
| POST | /v1/devices/tls-certificate | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | .UNWIRED |
| GET | /v1/device-binding/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.deviceBindingStatus |
| GET | /v1/connectivity/manifest | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.connectivityManifest |
| POST | /v1/devices/bootstrap/recover | DIRECT_OWNER_ROUTE / CONSUMED_BOOTSTRAP_TOKEN_AND_EXACT_ACTIVE_DEVICE_PROOF | VanGatewayClient.recoverBootstrap |
| POST | /v1/device-binding/certify | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ensureCertifiedIdentity |
| POST | /v1/devices/provisioning-status | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:device_enrolment | .UNWIRED |

**Service dependencies (not Android owner access)**

- VE-4af2782b0c0a

### OF-SETTINGS-001 — Settings, security and device readiness

Owner goal: Adjust local preferences and restore degraded capability.

Screens: van.settings, van.connected, van.onboarding; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- voice/notifications/quiet hours
- renderer/accessibility/theme
- permissions/biometric
- overlay/queue/voice/gateway/trading/knowledge/Google/browser signals
- restore instruction

**Owner interactions and controls**

- change supported local preference
- open system permission settings
- start/stop supported local services
- perform explicit restore action

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Automatic readiness, source diagnostics, Android permission navigation and supported installer recovery are wired. Operator release/transport binding and OS/device acceptance remain external; no owner connection configuration fields are required.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /health | DIRECT_OWNER_ROUTE / INGRESS_BEARER | VanGatewayClient.health |
| GET | /v1/degraded | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.degraded |
| GET | /v1/device-binding/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.deviceBindingStatus |

### OF-DIAGNOSTICS-001 — Owner diagnostics and correlation

Owner goal: Understand a failure and inspect safe evidence.

Screens: van.connected, van.settings, van.diagnostics; required screens: van.diagnostics.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- health/degraded
- transport mode/path
- queue/breaker
- trace/alerts
- mission/command/run correlation
- verification state

**Owner interactions and controls**

- inspect trace/evidence
- copy redacted diagnostic receipt
- retry supported request
- Inspect owner-safe settings records

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Recorded runtime/provider configuration, actual verification and independent source failures are supplied. Live configured services, enabled egress, diagnostics/privacy and physical acceptance remain pending; a registered provider is not proof of readiness.

**Located source functions (not whole-feature acceptance)**

- OF-DIAGNOSTICS-001:projection-ownerDiagnostics: Inspect owner-safe settings records — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /health | DIRECT_OWNER_ROUTE / INGRESS_BEARER | VanGatewayClient.health |
| GET | /v1/observability/health | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:observability | .UNWIRED |
| GET | /v1/observability/alerts | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:observability | .UNWIRED |
| GET | /v1/observability/trace/{command_id} | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:observability | .UNWIRED |
| GET | /v1/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.events |
| GET | /v1/owner/diagnostics | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.ownerDiagnostics |

**Service dependencies (not Android owner access)**

- VE-be1d235e3e07
- VE-7b962dca04ce
- VE-b6d0fb44ce1a

### OF-TRADING-001 — Trading overview, portfolio and risk

Owner goal: Know current market/trading health and exposure.

Screens: van.trading, van.trading.overview; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- status/assessment
- portfolio
- positions
- risk/heat/margin
- market freshness
- cognition
- significant thesis state
- broker/account readiness

**Owner interactions and controls**

- open position/account/risk/history detail
- refresh
- Inspect trading freshness, integrity, owner halt and independent source availability

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Overview reads actual runtime integrity/freshness/halt status and independent per-source failures. Missing time/data/failed chain shows UNKNOWN; refresh and concrete navigation are wired. Final visual state parity and real broker/provider data acceptance remain pending.

**Located source functions (not whole-feature acceptance)**

- OF-TRADING-001:runtime-status: Inspect trading freshness, integrity, owner halt and independent source availability — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingStatus |
| GET | /v1/trading/assessment | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingAssessment |
| GET | /v1/trading/portfolio | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPortfolio |
| GET | /v1/trading/positions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPositions |
| GET | /v1/trading/risk | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingRisk |
| GET | /v1/trading/market-state | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingMarketState |
| GET | /v1/trading/cognition | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingCognition |

### OF-TRADING-002 — Positions, charts, history and opportunity intelligence

Owner goal: Inspect a trade rationale and its verified outcome.

Screens: van.trading.positions, van.trading.positions.detail, van.trading.potential, van.trading.history, van.trading.cognition; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- position direction/exposure/protection/R
- thesis/invalidation/confirmation
- bars/chart
- events
- potential
- history
- decision/outcome quality

**Owner interactions and controls**

- open trade
- pan/zoom/crosshair
- inspect evidence/history/opportunity
- Resolve supported legacy trade/view links to actual trading routes

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Actual nested position/potential/history routes and legacy route arguments are wired. Read-source failure is explicit; final cached/degraded/access visual parity and real broker/pricing data acceptance remain pending.

**Located source functions (not whole-feature acceptance)**

- OF-TRADING-002:legacy-links: Resolve supported legacy trade/view links to actual trading routes — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/trades | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingTrades |
| GET | /v1/trading/trades/{trade_intent_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingTradeDetail |
| GET | /v1/trading/bars | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingBars |
| GET | /v1/trading/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingEvents |
| GET | /v1/trading/potential | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPotential |
| GET | /v1/trading/history | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingHistory |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/trading/market/depth-history | .UNWIRED | CANDIDATE_HISTORICAL_SOURCE_READ_ANDROID_CONSUMER_PENDING | Original partial-depth captures by exact native realm/account/symbol scope, revision or as-of boundary. Configured server storage, cumulative byte verification and two original read slots; cancellation cannot reopen capacity before completion. No broker refresh or query-supplied path/policy. Unavailable/corrupt/over-budget sources refuse and missing captures remain null. Complete original versioned capture/receipt retained; no current freshness, normalized price, complete book, provider right or frontend implementation is claimed. |
| DELETE /v1/trading/charts/workspaces/{workspace_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| GET /v1/trading/charts/capabilities | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| GET /v1/trading/charts/operations/{request_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| GET /v1/trading/charts/workspaces | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| GET /v1/trading/charts/workspaces/{workspace_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| GET /v1/trading/charts/workspaces/{workspace_id}/revisions | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| POST /v1/trading/charts/workspaces | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| POST /v1/trading/charts/workspaces/{workspace_id}/restore | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| PUT /v1/trading/charts/workspaces/{workspace_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_ANDROID_CONSUMER_PENDING | Typed renderer-independent workspace settings, exact native product references as owner context, price/time drawing anchors and presentation/research indicator parameters. Immutable revisions, expected-revision conflicts and restore-as-new-revision. Stable request IDs and exact original readback across uncertain writes; minimal receipts contain no notes/settings. Delete removes all stored revision bodies. Settings do not verify native instrument binding, calculate certified VATI indicators or qualify a renderer. No new UI or client consumption is claimed. |
| DELETE /v1/trading/monitors/alerts/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| DELETE /v1/trading/monitors/screen-rules/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| DELETE /v1/trading/monitors/watchlists/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/alerts | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/alerts/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/capabilities | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/operations/{request_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/screen-rules | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/screen-rules/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/watchlists | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| GET /v1/trading/monitors/watchlists/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/alerts | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/alerts/{object_id}/pause | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/alerts/{object_id}/restart | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/screen | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/screen-rules | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/screen-rules/{object_id}/run | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/watchlists | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| POST /v1/trading/monitors/watchlists/{object_id}/market | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| PUT /v1/trading/monitors/alerts/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| PUT /v1/trading/monitors/screen-rules/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |
| PUT /v1/trading/monitors/watchlists/{object_id} | .UNWIRED | CANDIDATE_BACKEND_COMPONENT_NATIVE_FEED_AND_ANDROID_CONSUMER_PENDING | Durable owner watchlists, exact native instrument selections, favourites and sorting; CAS/idempotent alert controls, pause/restart/delete; one canonical trigger per explicit arm, atomic existing event stream and recoverable Attention projection. Server closed-bar price/indicator/pinned-level-or-trend measurements and literal news-keyword checks. Typed bounded level screening with persistent quotas and saved-screen CRUD; running requires an exact revision and binds results to that captured rule hash. Saved selections do not prove native feed binding. Revision-bound watchlist market rows apply saved ordering/favourites and literal search/native identity filters. Closed-bar close/previous-bar change include exact basis, reference interval, age and source hashes; unavailable quotes/spreads remain null. A symbol-only bar lake cannot trigger a live technical fact. Exact signed owner pause/restart/delete commands bind alert ID and expected revision, use original command identity for replay, recheck expiry under the SQL writer lock and verify the original durable control receipt independently of current lifecycle. No order path exists. Remaining prerequisites: Full qualified native feed and quote binding; Tick-price alerts and native quote/spread/session-change row producers; Dynamic watchlists; Voice discovery/selection and Android command consumers beyond exact typed alert controls; Provider and Android consumer qualification. |

### OF-TRADING-003 — Trading account setup and controlled actions

Owner goal: Connect/manage supported trading accounts securely.

Screens: van.trading.accounts, van.trading.accounts.add; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- broker/platform
- connection state
- credential reference
- capabilities
- live/readiness status
- pending challenge
- Original physical-account/valuation facts, credit qualification and exact observation clocks remain distinct from cash-history coverage, settled funds and execution permission.

**Owner interactions and controls**

- request exact account challenge
- perform supported signed account action
- complete broker OAuth privately

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Account projections and exact gated account controls are wired. Final scoped access/offline/stale visual parity and actual broker receipt/credential admission acceptance remain pending; credentials stay on the trading host.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/accounts | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingAccounts |
| POST | /v1/trading/accounts/challenge | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingAccountChallenge |
| POST | /v1/trading/accounts/action | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingAccountAction |
| GET | /v1/trading/oauth/{broker}/callback | DIRECT_OWNER_ROUTE / BROKER_OAUTH_CALLBACK_STATE | .UNWIRED |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/trading/accounts/operations/{operation_id} | VanGatewayClient.tradingAccountOperation | CANDIDATE_SOURCE_ANDROID_REPAIR_NATIVE_ACCEPTANCE_PENDING | Native journal for account_upsert/account_credentials/account_remove/mt5_ea_issue_key; original non-secret operation identity survives Android restart; absence and incomplete effects stay UNKNOWN |
| GET /v1/trading/accounts/catalog | VanGatewayClient.tradingAccountCatalog | CANDIDATE_SOURCE_ANDROID_REPAIR_NATIVE_ACCEPTANCE_PENDING | Exact existing action fields, credential-key names, approval and original-result capabilities. Partial account edits preserve omitted settings. Generic edits require native resolved before/after review bound to the biometric proof and checked again by the native writer. |
| GET /v1/trading/accounts | VanGatewayClient.tradingAccounts | CANDIDATE_NATIVE_FACTS_ANDROID_DTO_SOURCE_TESTED | native_account_observation preserves current physical identity, original equity/balance/credit, credit-excluded risk valuation or explicit unknown/liability, source/read clocks and original snapshot references independently of cash-history coverage. Invalid evidence or changed profiles withhold financial values. Exact Kotlin decimal text and 64-bit identity/clock parsing; existing AccountCard DTO only, no new UI. Response schema: trading/vati/contracts/schemas/native_account_observation.schema.json |
| GET /v1/trading/portfolio | VanGatewayClient.tradingPortfolio | CANDIDATE_NATIVE_FACTS_ANDROID_DTO_SOURCE_TESTED | native_account_observation preserves current physical identity, original equity/balance/credit, credit-excluded risk valuation or explicit unknown/liability, source/read clocks and original snapshot references independently of cash-history coverage. Invalid evidence or changed profiles withhold financial values. Exact Kotlin decimal text and 64-bit identity/clock parsing; existing AccountCard DTO only, no new UI. Response schema: trading/vati/contracts/schemas/native_account_observation.schema.json |
| GET /v1/trading/funding/drafts/{request_id} | .UNWIRED | CANDIDATE_UNAPPROVED_FUNDING_DRAFT_ANDROID_CONSUMER_PENDING | Immutable exact owner/request funding inputs and original committed receipts in the existing VATI ledger. Current payment eligibility remains NOT_ADMITTED. Quote/beneficiary digests are unverified references; strict wire, retention, original-request, expiry and capacity refusal apply. Bound request proof stores a draft and does not authorize a payment. Existing provider admission and unsupported funding states remain required. No frontend implementation or native financial effect is claimed. |
| GET /v1/trading/funding/drafts/{request_id}/receipt | .UNWIRED | CANDIDATE_UNAPPROVED_FUNDING_DRAFT_ANDROID_CONSUMER_PENDING | Immutable exact owner/request funding inputs and original committed receipts in the existing VATI ledger. Current payment eligibility remains NOT_ADMITTED. Quote/beneficiary digests are unverified references; strict wire, retention, original-request, expiry and capacity refusal apply. Bound request proof stores a draft and does not authorize a payment. Existing provider admission and unsupported funding states remain required. No frontend implementation or native financial effect is claimed. |
| POST /v1/trading/funding/drafts | .UNWIRED | CANDIDATE_UNAPPROVED_FUNDING_DRAFT_ANDROID_CONSUMER_PENDING | Immutable exact owner/request funding inputs and original committed receipts in the existing VATI ledger. Current payment eligibility remains NOT_ADMITTED. Quote/beneficiary digests are unverified references; strict wire, retention, original-request, expiry and capacity refusal apply. Bound request proof stores a draft and does not authorize a payment. Existing provider admission and unsupported funding states remain required. No frontend implementation or native financial effect is claimed. |

**External dependencies**

- VE-78837b67b4b1

### OF-TRADING-004 — Strategy certificate promotion

Owner goal: Promote only a currently validated strategy under owner authority.

Screens: van.trading.strategies; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- promotion candidate
- certificate/evidence/current hash
- target state
- authority/approval challenge
- capsule-state readback

**Owner interactions and controls**

- inspect validation
- biometric approve exact certificate
- promote
- verify authoritative readback

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Strategy/runtime certificate readback is supplied; absent or obsolete evidence remains unavailable. Final visual state parity and live strategy/certificate qualification remain pending.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/trading/strategies/promotion-candidates | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPromotionCandidates |
| POST | /v1/trading/strategies/promotion-challenge | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPromotionChallenge |
| POST | /v1/trading/strategies/promote | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingPromoteStrategy |

### OF-TRADING-005 — Trading halt and ticket decisions

Owner goal: See risk halt state and perform only permitted protection actions.

Screens: van.trading.halt, van.trading.tickets, van.approval.trading-ticket; required screens: van.trading.halt, van.trading.tickets, van.approval.trading-ticket.

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- halt reason/action semantics
- risk authority
- ticket exact intent
- protection state
- receipt

**Owner interactions and controls**

- halt through supported signed owner command
- inspect/confirm supported ticket with fresh proof
- Read and refresh actual ticket/fill-confirmation records
- Record an exact broker fill with independent chained-ledger readback
- Request owner halt and read the fresh owner-halt runtime receipt

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Actual ticket read UI and exact broker-fill confirmation sheet are wired through fresh ticket authority plus A4 biometric command; an independent chained-ledger verifier settles the receipt. Owner halt has current status readback. Confirmation records a broker receipt and never executes an order; credentials/execution/provider acceptance remain external.

**Located source functions (not whole-feature acceptance)**

- OF-TRADING-005:ticket-list: Read and refresh actual ticket/fill-confirmation records — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-TRADING-005:confirm-fill: Record an exact broker fill with independent chained-ledger readback — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED
- OF-TRADING-005:halt-readback: Request owner halt and read the fresh owner-halt runtime receipt — SOURCE_IMPLEMENTED_DEVICE_UNVERIFIED

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/trading/halt | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:trading | .UNWIRED |
| GET | /v1/trading/tickets | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingTickets |
| POST | /v1/trading/tickets/{ticket_id}/confirm | HERMES_SERVICE_ONLY / INTERNAL_CONTROL:trading | .UNWIRED |
| POST | /v1/commands | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.dispatchCommand |
| GET | /v1/trading/status | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.tradingStatus |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/trading/runtime/recovery/catalog | VanGatewayClient.tradingRuntimeRecoveryCatalog | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_CONSUMER_PENDING | Single-session and multi-instrument account kill clear, loss-scope reset and drawdown rebaseline. The native account actor publishes its opaque session identity; symbol/contract configuration and lease changes invalidate an old review. Original approval ID and durable public proof survive uncertain dispatch. Reads never dispatch. APPLIED is not blanket entry authority; all other holds, unresolved original orders, profile and final native fences remain. |
| GET /v1/trading/runtime/recovery/operations/{operation_id} | VanGatewayClient.tradingRuntimeRecoveryOperation | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_CONSUMER_PENDING | Single-session and multi-instrument account kill clear, loss-scope reset and drawdown rebaseline. The native account actor publishes its opaque session identity; symbol/contract configuration and lease changes invalidate an old review. Original approval ID and durable public proof survive uncertain dispatch. Reads never dispatch. APPLIED is not blanket entry authority; all other holds, unresolved original orders, profile and final native fences remain. |
| GET /v1/trading/runtime/recovery/state | VanGatewayClient.tradingRuntimeRecoveryState | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_CONSUMER_PENDING | Single-session and multi-instrument account kill clear, loss-scope reset and drawdown rebaseline. The native account actor publishes its opaque session identity; symbol/contract configuration and lease changes invalidate an old review. Original approval ID and durable public proof survive uncertain dispatch. Reads never dispatch. APPLIED is not blanket entry authority; all other holds, unresolved original orders, profile and final native fences remain. |
| POST /v1/trading/runtime/recovery/challenge | VanGatewayClient.tradingRuntimeRecoveryChallenge | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_CONSUMER_PENDING | Single-session and multi-instrument account kill clear, loss-scope reset and drawdown rebaseline. The native account actor publishes its opaque session identity; symbol/contract configuration and lease changes invalidate an old review. Original approval ID and durable public proof survive uncertain dispatch. Reads never dispatch. APPLIED is not blanket entry authority; all other holds, unresolved original orders, profile and final native fences remain. |
| POST /v1/trading/runtime/recovery/request | VanGatewayClient.tradingRuntimeRecoveryRequest | CANDIDATE_BACKEND_AND_ANDROID_CLIENT_SOURCE_UI_CONSUMER_PENDING | Single-session and multi-instrument account kill clear, loss-scope reset and drawdown rebaseline. The native account actor publishes its opaque session identity; symbol/contract configuration and lease changes invalidate an old review. Original approval ID and durable public proof survive uncertain dispatch. Reads never dispatch. APPLIED is not blanket entry authority; all other holds, unresolved original orders, profile and final native fences remain. |

**Service dependencies (not Android owner access)**

- VE-ad4fc9e37cb1
- VE-c30a0ba46d55

### OF-DEV-001 — Development project hub and task control

Owner goal: Inspect and steer bounded project work.

Screens: van.work.dev.home, van.work.dev.plan, van.work.dev.tasks, van.work.dev.graph, van.work.dev.task, van.work.dev.agents, van.work.dev.workspaces, van.work.dev.workspace, van.work.dev.evidence, van.work.dev.reviews, van.work.dev.memory, van.work.dev.research, van.work.dev.design, van.work.dev.ci, van.work.dev.security; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- project home/stage plan
- task lifecycle/graph
- agents
- evidence
- review/memory/research/design/CI/security/infrastructure sections
- projection revision

**Owner interactions and controls**

- inspect project/task/evidence
- submit only actions advertised by upstream contract
- owner steer/pause/resume/cancel/retry where allowed

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Dedicated contract-driven DDS owner projections/actions are wired over verified product mTLS. Optional independently configured GitHub branch/CI observers use exact allowlisted remote repositories and fresh attempt readback; absent bindings report unobservable. Live Commander/DDS/GitHub execution acceptance remains pending; phone shell/SSH is not exposed.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/projects | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.projects |
| GET | /v1/dial-dev/projects/{project_id}/home | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.home |
| GET | /v1/dial-dev/projects/{project_id}/stage-plan | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.stagePlan |
| GET | /v1/dial-dev/projects/{project_id}/tasks | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.tasks |
| GET | /v1/dial-dev/projects/{project_id}/graph | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.graph |
| GET | /v1/dial-dev/tasks/{task_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.task |
| GET | /v1/dial-dev/agents | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.agents |
| GET | /v1/dial-dev/reviews | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.section.reviews |
| GET | /v1/dial-dev/memory | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.section.memory |
| GET | /v1/dial-dev/research | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.section.research |
| GET | /v1/dial-dev/design | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.section.design |
| GET | /v1/dial-dev/ci | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.section.ci |
| GET | /v1/dial-dev/security | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.section.security |
| GET | /v1/dial-dev/infrastructure | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.infrastructure |
| GET | /v1/dial-dev/evidence/{evidence_ref} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.evidence |
| GET | /v1/dial-dev/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.events |
| POST | /v1/dial-dev/actions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.submitAction |

**Backend/client extensions — consumer status is explicit**

| Method / path | Client | Status | Scope |
| --- | --- | --- | --- |
| GET /v1/dial-dev/actions/{action_id} | VanGatewayClient.dialDev.action/reconcileAction | CANDIDATE_BACKEND_AND_EXISTING_ANDROID_CONTROL_RECOVERY_SOURCE_NATIVE_ACCEPTANCE_PENDING | Exact original action read beyond recent lists; encrypted prepared request retains parameters/revision/key across restart. Reads never POST. Changed instructions, malformed/foreign/stale facts and uncertain native control errors cannot replace an original. APPLIED is a control outcome, not task success. |

### OF-DEV-002 — Workspace evidence and terminal views

Owner goal: Inspect bounded implementation evidence without a second execution agent.

Screens: van.work.dev.workspace, van.work.dev.evidence; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `PARTIAL_OWNER_SURFACE`.

**Information supplied**

- workspace state
- diff
- bounded terminal tail
- evidence refs
- staleness

**Owner interactions and controls**

- open workspace
- inspect diff/log/evidence
- invoke only supported upstream actions

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Bounded workspace/log evidence projections are source wired and read-only. Final evidence readability and process-recreation visual state are redesign/acceptance work; no phone shell or SSH authority is supplied.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/dial-dev/workspaces | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.workspaces |
| GET | /v1/dial-dev/workspaces/{workspace_id} | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.workspace |
| GET | /v1/dial-dev/workspaces/{workspace_id}/diff | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.workspaceDiff |
| GET | /v1/dial-dev/workspaces/{workspace_id}/terminal-tail | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.workspaceTerminalTail |
| POST | /v1/dial-dev/actions | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.DialDevClient.dialDev.submitAction |

### OF-ARTEMIS-001 — ARTEMIS test console

Owner goal: Open the governed Android test surface.

Screens: van.work.artemis; required screens: .

Wiring: `SOURCE_WIRED_REQUIRES_ACCEPTANCE`; integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`.

**Information supplied**

- console admission/session
- safe launch URL
- connection/access status

**Owner interactions and controls**

- request device-proved console session
- open governed embedded console

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Governed Android console/session source is wired. S24 Ultra USB authorization on Windows was owner-reported, not independently observed; no callable Global DIAL/Artemis device channel exists here. Physical Android cases executed: 0; acceptance is deferred until complete wiring/release provisioning.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| POST | /v1/artemis/console/session | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.artemisConsoleSession |

### OF-EMBODIMENT-001 — Functional Rive state projection

Owner goal: Read VAN state through motion plus accessible information.

Screens: van.floating, van.home; required screens: .

Wiring: `EXTERNAL_CONTRACT_OR_ASSET_REQUIRED`; integration: `SOURCE_PRESENT_REQUIRES_ACCEPTANCE`.

**Information supplied**

- durable activity
- orthogonal health/authority
- listening/speaking
- attention vector/urgency
- viseme/mouth
- finite action

**Owner interactions and controls**

- board gesture parity
- reduced-motion mode
- renderer diagnostic/acceptance

**Required acceptance states**

- happy
- loading
- error
- degraded
- offline
- stale
- access
- empty
- cancelled

**Declared integration gaps**

- Functional renderer adapter preserves the fixed 9-input/8-trigger/18-state contract. Rive runtime native arm64 libraries are now 16KiB aligned and owner release gates reject bad ELF/ZIP alignment. Authored redesigned Rive bytes, visual acceptance and device renderer qualification remain external.

**Declared endpoint contracts**

| Method | Path | Access / authentication | Android client |
| --- | --- | --- | --- |
| GET | /v1/events | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.events |
| POST | /v1/visual/acceptance | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.recordVisualAcceptance |
| GET | /v1/visual/acceptance | DIRECT_OWNER_ROUTE / INGRESS_BEARER_AND_PAIRED_DEVICE | VanGatewayClient.latestVisualAcceptance |

## Complete frozen planned feature scope

All **93 planned features** are copied below from the frozen registry. These are distinct from the 42 current-source feature groups above. A frozen stage or provisional surface is a planning statement, not implementation, visual design, endpoint coverage or acceptance.

Source: [REV2_FEATURE_REGISTRY.json](../../../review-inputs/van-rev115/package/reference/REV2_FEATURE_REGISTRY.json); SHA-256 `9748ff23550847816fb2a909921002f9d13248f2bfb45e482586b814c91aedb5`.

| Planned ID | Domain | Feature | Primary / provisional surface | Frozen stage |
| --- | --- | --- | --- | --- |
| VNX-F-HOME-01 | HOME | Spatial Home | VNX-S-HOME-01 / VNX-S-HOME-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-HOME-02 | HOME | State-aware metallic orb | VNX-S-HOME-02 / VNX-S-HOME-02 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-HOME-03 | HOME | Home quick hub | VNX-S-HOME-02 / VNX-S-HOME-02 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-HOME-04 | HOME | Attention preview | VNX-S-HOME-03 / VNX-S-HOME-03 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-HOME-05 | HOME | Smart briefing | VNX-S-HOME-01 / VNX-S-HOME-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-HOME-06 | HOME | Semantic deep links | VNX-S-HOME-01 / VNX-S-HOME-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-HOME-07 | HOME | Home state fallbacks | VNX-S-HOME-01 / VNX-S-HOME-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-TRADE-01 | TRADE | Trading Home | VNX-S-TRADE-01 / VNX-S-TRADE-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-TRADE-02 | TRADE | Portfolio summary | VNX-S-TRADE-02 / VNX-S-TRADE-02 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-TRADE-03 | TRADE | Markets overview | VNX-S-TRADE-03 / VNX-S-TRADE-03 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-TRADE-04 | TRADE | Watchlists | VNX-S-TRADE-06 / VNX-S-TRADE-06 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-TRADE-05 | TRADE | Opportunity discovery | VNX-S-TRADE-01 / VNX-S-TRADE-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-TRADE-06 | TRADE | Charts entry | VNX-S-TRADE-09 / VNX-S-TRADE-09 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-TRADE-07 | TRADE | Intelligence entry | VNX-S-TRADE-10 / VNX-S-TRADE-10 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-TRADE-08 | TRADE | Account context entry | VNX-S-TRADE-10 / VNX-S-TRADE-10 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-01 | CHART | Native chart previews | VNX-S-CHART-20 / VNX-S-CHART-20 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-02 | CHART | Rich chart terminal | VNX-S-CHART-02 / VNX-S-CHART-02 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-03 | CHART | Instrument search and alias mapping | VNX-S-CHART-01 / VNX-S-CHART-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-04 | CHART | Price and timeframe precision | VNX-S-CHART-08 / VNX-S-CHART-08 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-05 | CHART | Indicators and parameters | VNX-S-CHART-01 / VNX-S-CHART-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-06 | CHART | Drawing tools and persistence | VNX-S-CHART-05 / VNX-S-CHART-05 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-07 | CHART | Chart overlays and crosshair | VNX-S-CHART-17 / VNX-S-CHART-17 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-08 | CHART | Bar replay sandbox | VNX-S-CHART-12 / VNX-S-CHART-12 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-09 | CHART | Multi-chart layouts | VNX-S-CHART-01 / VNX-S-CHART-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-10 | CHART | Orderbook market depth | VNX-S-CHART-15 / VNX-S-CHART-15 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-11 | CHART | Chart alert creation | VNX-S-CHART-01 / VNX-S-CHART-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-12 | CHART | Order and position overlays | VNX-S-CHART-01 / VNX-S-CHART-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-13 | CHART | Chart source integrity | VNX-S-CHART-01 / VNX-S-CHART-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-14 | CHART | Chart observation export | VNX-S-CHART-19 / VNX-S-CHART-19 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-CHART-15 | CHART | Chart renderer failover | VNX-S-CHART-01 / VNX-S-CHART-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ORDERS-01 | ORDERS | Open positions | VNX-S-ORDERS-01 / VNX-S-ORDERS-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ORDERS-02 | ORDERS | Position details | VNX-S-ORDERS-02 / VNX-S-ORDERS-02 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ORDERS-03 | ORDERS | Pending orders | VNX-S-ORDERS-04 / VNX-S-ORDERS-04 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ORDERS-04 | ORDERS | Order creation proposals | VNX-S-ORDERS-05 / VNX-S-ORDERS-05 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ORDERS-05 | ORDERS | Owner order approval | VNX-S-ORDERS-07 / VNX-S-ORDERS-07 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ORDERS-06 | ORDERS | Broker order receipt | VNX-S-ORDERS-08 / VNX-S-ORDERS-08 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ORDERS-07 | ORDERS | Stop loss take profit management | VNX-S-ORDERS-09 / VNX-S-ORDERS-09 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ORDERS-08 | ORDERS | Partial reduction intents | VNX-S-ORDERS-10 / VNX-S-ORDERS-10 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ORDERS-09 | ORDERS | Trade history and TCA | VNX-S-ORDERS-11 / VNX-S-ORDERS-11 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ORDERS-10 | ORDERS | Risk command centre | VNX-S-ORDERS-06 / VNX-S-ORDERS-06 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-01 | ACCOUNTS | Accounts overview | VNX-S-ACCOUNTS-01 / VNX-S-ACCOUNTS-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-02 | ACCOUNTS | Link existing broker account | VNX-S-ACCOUNTS-05 / VNX-S-ACCOUNTS-05 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-03 | ACCOUNTS | Create demo account | VNX-S-ACCOUNTS-03 / VNX-S-ACCOUNTS-03 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-04 | ACCOUNTS | Apply for live broker account | VNX-S-ACCOUNTS-04 / VNX-S-ACCOUNTS-04 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-05 | ACCOUNTS | Edit local account configuration | VNX-S-ACCOUNTS-07 / VNX-S-ACCOUNTS-07 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-06 | ACCOUNTS | Edit broker account details | VNX-S-ACCOUNTS-08 / VNX-S-ACCOUNTS-08 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-07 | ACCOUNTS | Credential rotation | VNX-S-ACCOUNTS-01 / VNX-S-ACCOUNTS-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-08 | ACCOUNTS | Account connection validation | VNX-S-ACCOUNTS-02 / VNX-S-ACCOUNTS-02 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-09 | ACCOUNTS | Unlink local account | VNX-S-ACCOUNTS-07 / VNX-S-ACCOUNTS-07 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-10 | ACCOUNTS | Close remote broker account | VNX-S-ACCOUNTS-02 / VNX-S-ACCOUNTS-02 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-11 | ACCOUNTS | Deposit funds | VNX-S-ACCOUNTS-01 / VNX-S-ACCOUNTS-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-12 | ACCOUNTS | Withdraw funds | VNX-S-ACCOUNTS-01 / VNX-S-ACCOUNTS-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-13 | ACCOUNTS | Transfer between accounts | VNX-S-ACCOUNTS-01 / VNX-S-ACCOUNTS-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-14 | ACCOUNTS | Payment methods | VNX-S-ACCOUNTS-01 / VNX-S-ACCOUNTS-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-15 | ACCOUNTS | Transaction and settlement history | VNX-S-ACCOUNTS-01 / VNX-S-ACCOUNTS-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-16 | ACCOUNTS | KYC account restrictions | VNX-S-ACCOUNTS-01 / VNX-S-ACCOUNTS-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-ACCOUNTS-17 | ACCOUNTS | Leverage and account permissions | VNX-S-ACCOUNTS-01 / VNX-S-ACCOUNTS-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-INTEL-01 | INTEL | Intelligence overview | VNX-S-INTEL-01 / VNX-S-INTEL-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-INTEL-02 | INTEL | News feed | VNX-S-INTEL-02 / VNX-S-INTEL-02 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-INTEL-03 | INTEL | Full article analysis | VNX-S-INTEL-03 / VNX-S-INTEL-03 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-INTEL-04 | INTEL | Economic calendar | VNX-S-INTEL-04 / VNX-S-INTEL-04 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-INTEL-05 | INTEL | Instrument and portfolio impact | VNX-S-INTEL-06 / VNX-S-INTEL-06 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-INTEL-06 | INTEL | Source verification and contradictions | VNX-S-INTEL-09 / VNX-S-INTEL-09 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-INTEL-07 | INTEL | Live VAN trading analyst | VNX-S-INTEL-11 / VNX-S-INTEL-11 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-INTEL-08 | INTEL | Strategy evidence analysis | VNX-S-INTEL-08 / VNX-S-INTEL-08 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-INTEL-09 | INTEL | Trading opportunity reasoning | VNX-S-INTEL-12 / VNX-S-INTEL-12 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-INTEL-10 | INTEL | Cross-signal intelligence packet | VNX-S-INTEL-01 / VNX-S-INTEL-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-INTEL-11 | INTEL | Learning and outcome review | VNX-S-INTEL-01 / VNX-S-INTEL-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-WORK-01 | WORK | Work command centre | VNX-S-WORK-01 / VNX-S-WORK-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-WORK-02 | WORK | Projects overview | VNX-S-WORK-02 / VNX-S-WORK-02 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-WORK-03 | WORK | Task lists | VNX-S-WORK-04 / VNX-S-WORK-04 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-WORK-04 | WORK | Live dependency graph | VNX-S-WORK-06 / VNX-S-WORK-06 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-WORK-05 | WORK | Agent relationship graph | VNX-S-WORK-07 / VNX-S-WORK-07 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-WORK-06 | WORK | Evidence-based progress | VNX-S-WORK-09 / VNX-S-WORK-09 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-WORK-07 | WORK | Muse native control | VNX-S-WORK-11 / VNX-S-WORK-11 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-WORK-08 | WORK | ARTEMIS testing surface | VNX-S-WORK-13 / VNX-S-WORK-13 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-WORK-09 | WORK | Review and approval queue | VNX-S-WORK-14 / VNX-S-WORK-14 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-WORK-10 | WORK | Blocker and handoff tracking | VNX-S-WORK-08 / VNX-S-WORK-08 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-WORK-11 | WORK | Activity and execution receipts | VNX-S-WORK-16 / VNX-S-WORK-16 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-WORK-12 | WORK | Workflow accessibility parity | VNX-S-WORK-01 / VNX-S-WORK-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-PRESENCE-01 | PRESENCE | Floating VAN service | VNX-S-PRESENCE-01 / VNX-S-PRESENCE-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-PRESENCE-02 | PRESENCE | Floating workboard | VNX-S-PRESENCE-02 / VNX-S-PRESENCE-02 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-PRESENCE-03 | PRESENCE | Voice and conversation | VNX-S-PRESENCE-05 / VNX-S-PRESENCE-05 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-PRESENCE-04 | PRESENCE | Floating gestures and recovery | VNX-S-PRESENCE-06 / VNX-S-PRESENCE-06 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-PRESENCE-05 | PRESENCE | Shared orb presence projection | VNX-S-PRESENCE-01 / VNX-S-PRESENCE-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-MEMORY-01 | MEMORY | Memory and record search | VNX-S-MEMORY-02 / VNX-S-MEMORY-02 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-MEMORY-02 | MEMORY | Research and sources | VNX-S-MEMORY-03 / VNX-S-MEMORY-03 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-MEMORY-03 | MEMORY | Memory privacy and erasure | VNX-S-MEMORY-04 / VNX-S-MEMORY-04 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-MEMORY-04 | MEMORY | Learning goals and adaptations | VNX-S-MEMORY-01 / VNX-S-MEMORY-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-MORE-01 | MORE | Connected services | VNX-S-MORE-02 / VNX-S-MORE-02 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-MORE-02 | MORE | Permissions and device authority | VNX-S-MORE-03 / VNX-S-MORE-03 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-MORE-03 | MORE | Automation and schedules | VNX-S-MORE-01 / VNX-S-MORE-01 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |
| VNX-F-MORE-04 | MORE | Settings diagnostics appearance | VNX-S-MORE-04 / VNX-S-MORE-04 | DESIGN_CANDIDATE_NOT_IMPLEMENTED |

#### VNX-F-HOME-01 — Spatial Home

Provide a correctly state-bound, accessible spatial home capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-001
- VNX-R-014
- VNX-R-018
- VNX-R-019
- VNX-R-143
- VNX-R-165
- VNX-R-166
- VNX-R-168
- VNX-R-169
- VNX-R-170
- VNX-R-171

#### VNX-F-HOME-02 — State-aware metallic orb

Provide a correctly state-bound, accessible state-aware metallic orb capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-002
- VNX-R-020
- VNX-R-142
- VNX-R-145
- VNX-R-146
- VNX-R-164
- VNX-R-167

#### VNX-F-HOME-03 — Home quick hub

Provide a correctly state-bound, accessible home quick hub capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-003
- VNX-R-021
- VNX-R-144

#### VNX-F-HOME-04 — Attention preview

Provide a correctly state-bound, accessible attention preview capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-022

#### VNX-F-HOME-05 — Smart briefing

Provide a correctly state-bound, accessible smart briefing capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-023

#### VNX-F-HOME-06 — Semantic deep links

Provide a correctly state-bound, accessible semantic deep links capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-024

#### VNX-F-HOME-07 — Home state fallbacks

Provide a correctly state-bound, accessible home state fallbacks capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-025

#### VNX-F-TRADE-01 — Trading Home

Provide a correctly state-bound, accessible trading home capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-005
- VNX-R-026

#### VNX-F-TRADE-02 — Portfolio summary

Provide a correctly state-bound, accessible portfolio summary capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-027

#### VNX-F-TRADE-03 — Markets overview

Provide a correctly state-bound, accessible markets overview capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-028

#### VNX-F-TRADE-04 — Watchlists

Provide a correctly state-bound, accessible watchlists capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-029

#### VNX-F-TRADE-05 — Opportunity discovery

Provide a correctly state-bound, accessible opportunity discovery capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-030

#### VNX-F-TRADE-06 — Charts entry

Provide a correctly state-bound, accessible charts entry capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-031

#### VNX-F-TRADE-07 — Intelligence entry

Provide a correctly state-bound, accessible intelligence entry capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-032

#### VNX-F-TRADE-08 — Account context entry

Provide a correctly state-bound, accessible account context entry capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-033

#### VNX-F-CHART-01 — Native chart previews

Provide a correctly state-bound, accessible native chart previews capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-034
- VNX-R-132
- VNX-R-135
- VNX-R-136
- VNX-R-138
- VNX-R-139

#### VNX-F-CHART-02 — Rich chart terminal

Keep full toolset hidden in contextual sheets while preserving precision and interaction.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-035
- VNX-R-134

#### VNX-F-CHART-03 — Instrument search and alias mapping

Provide a correctly state-bound, accessible instrument search and alias mapping capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-036

#### VNX-F-CHART-04 — Price and timeframe precision

Provide a correctly state-bound, accessible price and timeframe precision capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-037

#### VNX-F-CHART-05 — Indicators and parameters

Provide a correctly state-bound, accessible indicators and parameters capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-038

#### VNX-F-CHART-06 — Drawing tools and persistence

Provide a correctly state-bound, accessible drawing tools and persistence capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-039
- VNX-R-133

#### VNX-F-CHART-07 — Chart overlays and crosshair

Provide a correctly state-bound, accessible chart overlays and crosshair capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-040

#### VNX-F-CHART-08 — Bar replay sandbox

Provide a correctly state-bound, accessible bar replay sandbox capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-041
- VNX-R-137

#### VNX-F-CHART-09 — Multi-chart layouts

Provide a correctly state-bound, accessible multi-chart layouts capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-042

#### VNX-F-CHART-10 — Orderbook market depth

Provide a correctly state-bound, accessible orderbook market depth capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-043
- VNX-R-140

#### VNX-F-CHART-11 — Chart alert creation

Provide a correctly state-bound, accessible chart alert creation capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-044

#### VNX-F-CHART-12 — Order and position overlays

Provide a correctly state-bound, accessible order and position overlays capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-006
- VNX-R-045

#### VNX-F-CHART-13 — Chart source integrity

Provide a correctly state-bound, accessible chart source integrity capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-046

#### VNX-F-CHART-14 — Chart observation export

Emit provenance-bound drawing/crosshair/annotation observations as non-authoritative analyst inputs.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-047
- VNX-R-141

#### VNX-F-CHART-15 — Chart renderer failover

Provide a correctly state-bound, accessible chart renderer failover capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-048

#### VNX-F-ORDERS-01 — Open positions

Provide a correctly state-bound, accessible open positions capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VATI_RISK_EXECUTION`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-049

#### VNX-F-ORDERS-02 — Position details

Provide a correctly state-bound, accessible position details capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VATI_RISK_EXECUTION`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-050

#### VNX-F-ORDERS-03 — Pending orders

Provide a correctly state-bound, accessible pending orders capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VATI_RISK_EXECUTION`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-007
- VNX-R-051

#### VNX-F-ORDERS-04 — Order creation proposals

Chart/assistant can draft order but only VATI and owner mandate can authorize execution.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VATI_RISK_EXECUTION`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-052

#### VNX-F-ORDERS-05 — Owner order approval

Provide a correctly state-bound, accessible owner order approval capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VATI_RISK_EXECUTION`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-053

#### VNX-F-ORDERS-06 — Broker order receipt

Provide a correctly state-bound, accessible broker order receipt capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VATI_RISK_EXECUTION`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-054

#### VNX-F-ORDERS-07 — Stop loss take profit management

Provide a correctly state-bound, accessible stop loss take profit management capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VATI_RISK_EXECUTION`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-055

#### VNX-F-ORDERS-08 — Partial reduction intents

Provide a correctly state-bound, accessible partial reduction intents capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VATI_RISK_EXECUTION`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-056

#### VNX-F-ORDERS-09 — Trade history and TCA

Provide a correctly state-bound, accessible trade history and tca capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VATI_RISK_EXECUTION`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-057

#### VNX-F-ORDERS-10 — Risk command centre

Provide a correctly state-bound, accessible risk command centre capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VATI_RISK_EXECUTION`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-058

#### VNX-F-ACCOUNTS-01 — Accounts overview

Provide a correctly state-bound, accessible accounts overview capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-059
- VNX-R-116
- VNX-R-117
- VNX-R-122
- VNX-R-123
- VNX-R-124
- VNX-R-130
- VNX-R-154
- VNX-R-155
- VNX-R-156
- VNX-R-157
- VNX-R-158
- VNX-R-159
- VNX-R-160
- VNX-R-162
- VNX-R-163

#### VNX-F-ACCOUNTS-02 — Link existing broker account

Provide a correctly state-bound, accessible link existing broker account capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `BROKER_MONEY_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-009
- VNX-R-060
- VNX-R-119
- VNX-R-129

#### VNX-F-ACCOUNTS-03 — Create demo account

Provide a correctly state-bound, accessible create demo account capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-061
- VNX-R-112
- VNX-R-127

#### VNX-F-ACCOUNTS-04 — Apply for live broker account

Provide a correctly state-bound, accessible apply for live broker account capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `BROKER_MONEY_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-015
- VNX-R-062

#### VNX-F-ACCOUNTS-05 — Edit local account configuration

Validate immutable account identity and use atomic write before reporting success.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-063
- VNX-R-114
- VNX-R-115
- VNX-R-128

#### VNX-F-ACCOUNTS-06 — Edit broker account details

Provide a correctly state-bound, accessible edit broker account details capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `BROKER_MONEY_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-064

#### VNX-F-ACCOUNTS-07 — Credential rotation

Provide a correctly state-bound, accessible credential rotation capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-065
- VNX-R-118
- VNX-R-161

#### VNX-F-ACCOUNTS-08 — Account connection validation

Read fresh broker/account heartbeat, credentials valid and independent state.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-016
- VNX-R-066

#### VNX-F-ACCOUNTS-09 — Unlink local account

Provide a correctly state-bound, accessible unlink local account capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-067
- VNX-R-113

#### VNX-F-ACCOUNTS-10 — Close remote broker account

Only broker can close external account; local unlink alone must never mark remote closure.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `BROKER_MONEY_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-068
- VNX-R-125

#### VNX-F-ACCOUNTS-11 — Deposit funds

Issue only provider-authorized deposit intent; require provider settlement readback and owner context.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `BROKER_MONEY_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-069
- VNX-R-120
- VNX-R-121
- VNX-R-126

#### VNX-F-ACCOUNTS-12 — Withdraw funds

Require account and beneficiary binding, amount/fee quote, A4, provider receipt and eventual settlement.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `BROKER_MONEY_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-070

#### VNX-F-ACCOUNTS-13 — Transfer between accounts

Bind exact source/destination/currency/fees and independent transfer reconciliation.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `BROKER_MONEY_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-071

#### VNX-F-ACCOUNTS-14 — Payment methods

Provide a correctly state-bound, accessible payment methods capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-072
- VNX-R-131

#### VNX-F-ACCOUNTS-15 — Transaction and settlement history

Provide a correctly state-bound, accessible transaction and settlement history capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-073

#### VNX-F-ACCOUNTS-16 — KYC account restrictions

Provide a correctly state-bound, accessible kyc account restrictions capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-074

#### VNX-F-ACCOUNTS-17 — Leverage and account permissions

Provide a correctly state-bound, accessible leverage and account permissions capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-075

#### VNX-F-INTEL-01 — Intelligence overview

Provide a correctly state-bound, accessible intelligence overview capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-008
- VNX-R-076

#### VNX-F-INTEL-02 — News feed

Use source age, dedupe, relevance and trust evidence; do not fabricate articles or timestamps.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-077

#### VNX-F-INTEL-03 — Full article analysis

Separate verified claims, counterevidence, uncertainty, prices and account impact.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-078

#### VNX-F-INTEL-04 — Economic calendar

Provide a correctly state-bound, accessible economic calendar capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-079

#### VNX-F-INTEL-05 — Instrument and portfolio impact

Provide a correctly state-bound, accessible instrument and portfolio impact capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-080

#### VNX-F-INTEL-06 — Source verification and contradictions

Provide a correctly state-bound, accessible source verification and contradictions capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-081

#### VNX-F-INTEL-07 — Live VAN trading analyst

Provide a correctly state-bound, accessible live van trading analyst capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-082

#### VNX-F-INTEL-08 — Strategy evidence analysis

Provide a correctly state-bound, accessible strategy evidence analysis capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-083

#### VNX-F-INTEL-09 — Trading opportunity reasoning

Provide a correctly state-bound, accessible trading opportunity reasoning capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-084

#### VNX-F-INTEL-10 — Cross-signal intelligence packet

Provide a correctly state-bound, accessible cross-signal intelligence packet capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-085

#### VNX-F-INTEL-11 — Learning and outcome review

Reject lookahead bias and preserve outcomes, counterfactuals and owner annotations.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `VAN_DISPLAY_EVIDENCE`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-086

#### VNX-F-WORK-01 — Work command centre

Provide a correctly state-bound, accessible work command centre capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-017
- VNX-R-087

#### VNX-F-WORK-02 — Projects overview

Provide a correctly state-bound, accessible projects overview capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-088

#### VNX-F-WORK-03 — Task lists

Provide a correctly state-bound, accessible task lists capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-089

#### VNX-F-WORK-04 — Live dependency graph

Render typed task edges, owner restrictions, proof counts, revision and accessibility list.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-090
- VNX-R-147
- VNX-R-150

#### VNX-F-WORK-05 — Agent relationship graph

Show live actor responsibilities, lease, handoff, contention and independently verified status.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-091
- VNX-R-148

#### VNX-F-WORK-06 — Evidence-based progress

Provide a correctly state-bound, accessible evidence-based progress capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-011
- VNX-R-092
- VNX-R-149

#### VNX-F-WORK-07 — Muse native control

Provide a correctly state-bound, accessible muse native control capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-093
- VNX-R-151

#### VNX-F-WORK-08 — ARTEMIS testing surface

Provide a correctly state-bound, accessible artemis testing surface capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-094
- VNX-R-152

#### VNX-F-WORK-09 — Review and approval queue

Provide a correctly state-bound, accessible review and approval queue capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-095

#### VNX-F-WORK-10 — Blocker and handoff tracking

Provide a correctly state-bound, accessible blocker and handoff tracking capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-096

#### VNX-F-WORK-11 — Activity and execution receipts

Provide a correctly state-bound, accessible activity and execution receipts capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-010
- VNX-R-097

#### VNX-F-WORK-12 — Workflow accessibility parity

Provide a correctly state-bound, accessible workflow accessibility parity capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `OWNER_A4_GATEWAY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-098
- VNX-R-153

#### VNX-F-PRESENCE-01 — Floating VAN service

Provide a correctly state-bound, accessible floating van service capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `PRODUCT_CONSENT_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-099

#### VNX-F-PRESENCE-02 — Floating workboard

Provide a correctly state-bound, accessible floating workboard capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `PRODUCT_CONSENT_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-100

#### VNX-F-PRESENCE-03 — Voice and conversation

Provide a correctly state-bound, accessible voice and conversation capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `PRODUCT_CONSENT_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-101

#### VNX-F-PRESENCE-04 — Floating gestures and recovery

Provide a correctly state-bound, accessible floating gestures and recovery capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `PRODUCT_CONSENT_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-004
- VNX-R-102

#### VNX-F-PRESENCE-05 — Shared orb presence projection

Separate operational state from animation; priority and expiry must be deterministic.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `PRODUCT_CONSENT_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-103

#### VNX-F-MEMORY-01 — Memory and record search

Provide a correctly state-bound, accessible memory and record search capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `PRODUCT_CONSENT_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-012
- VNX-R-104

#### VNX-F-MEMORY-02 — Research and sources

Provide a correctly state-bound, accessible research and sources capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `PRODUCT_CONSENT_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-105

#### VNX-F-MEMORY-03 — Memory privacy and erasure

Provide a correctly state-bound, accessible memory privacy and erasure capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `PRODUCT_CONSENT_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-106

#### VNX-F-MEMORY-04 — Learning goals and adaptations

Provide a correctly state-bound, accessible learning goals and adaptations capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `PRODUCT_CONSENT_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-107

#### VNX-F-MORE-01 — Connected services

Provide a correctly state-bound, accessible connected services capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `PRODUCT_CONSENT_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-108

#### VNX-F-MORE-02 — Permissions and device authority

Provide a correctly state-bound, accessible permissions and device authority capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `PRODUCT_CONSENT_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-013
- VNX-R-109

#### VNX-F-MORE-03 — Automation and schedules

Provide a correctly state-bound, accessible automation and schedules capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `PRODUCT_CONSENT_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-110

#### VNX-F-MORE-04 — Settings diagnostics appearance

Provide a correctly state-bound, accessible settings diagnostics appearance capability in VAN Next without importing legacy visual code.

Technology: Android Jetpack Compose + typed gateway adapters; functional authority: `PRODUCT_CONSENT_AUTHORITY`; visual authority: `VAN_LOCKED_DARK_LIGHT`.

**Required states**

- LOADING
- READY
- EMPTY
- STALE
- OFFLINE
- ERROR
- UNKNOWN

**Required identities**

- VNX-R-111
