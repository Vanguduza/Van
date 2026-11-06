# VAN floating assistant: industry usability and functionality audit

**Audit date:** 5 November 2026. **Baseline:** PR105 source 2b1da2775ea7b0e8c3893cc259e469bd78e1c2bd. **Scope:** original floating character, native aura, overlay window and workboard, chat/voice/trade presentation, accessibility, animation-state updates and device-validation readiness. Existing Rive artwork/layer admission and VAN Next architecture remain authoritative.

## Executive assessment

VAN has a differentiated candidate: an expressive character and independently animated companion, task/state-aware presentation, owned-interface pointing, space-aware workboards and a genuinely functional application behind the character. That does not yet establish industry-leading usability. The best feature set is irrelevant if users cannot confidently stop voice, escape the board, recover a draft, read older replies, or move the assistant without a precise drag.

This review treats incumbents as references for particular interaction patterns, not as identical products. Apple/Samsung accessibility menus are not reasoning agents. Gemini Live is a conversational reference. Copilot's vision controls are an explicit-sharing/control reference. Android bubbles establish platform expectations, not a requirement to replace VAN's character with a notification bubble. Hardware and operating-system privileges differ. No numerical product ranking, competitor latency measurement, or claim that VAN surpasses these products is made.

**Current conclusion:** several material usability defects are repaired in source and covered by regression checks. Character distinctiveness and richer workflow presentation are promising advantages. Full native interaction, accessibility, frame pacing, thermal/power behavior and owner visual acceptance on the actual S24 are still required before claiming parity or superiority.

## Reference baseline and what it means for VAN

| Reference | Relevant documented behavior | Requirement adopted for VAN | Evidence boundary |
|---|---|---|---|
| Gemini Live | Natural interruption, explicit hold/end/mute, voice/text switching. [1] | Start/stop capture and speech must be discoverable; selected Voice tab is not proof of a live microphone. | VAN source producer/control paths audited; physical audio route/latency comparison not performed. |
| Copilot vision | User explicitly starts sharing; stopping screen sharing is distinct from ending voice. [2] | Each stop control says what it stops. Closing presentation, stopping voice and cancelling a task are separate operations. | VAN does not silently inspect external app controls or add screen-sharing authority. |
| Apple AssistiveTouch | Configurable direct actions and a movable persistent menu; idle visibility can be adjusted. [3] | Basic actions must not require learning hidden double taps or precision dragging; unobtrusiveness must be user-controlled. | Existing minimize/dock/close and named accessible actions are present. Customizable idle opacity/gesture mapping is not newly claimed. |
| Samsung Assistant menu | Quick accessible navigation, adjustable transparency and app-contextual menu choices. [4] | Actions remain readable and reachable in a small viewport; non-gesture alternatives are first-class. | Named custom actions and bounded menu repairs are source-level; actual TalkBack/Switch Access test remains open. |
| Android bubbles | User-controlled expansion/collapse and restrained automatic expansion. [5] | A task update must not constantly force a board open or steal the underlying app's interaction. | VAN retains its own overlay; this is an interaction benchmark, not a bubble migration. |
| Compose accessibility guidance | Meaningful roles/state, accessible custom actions and minimum48dp interactive sizes. [6][7] | Visible state, target size and accessible navigation must be correct, not just visually attractive. | Code/test evidence does not replace actual accessibility-service testing. |
| Android rendering guidance | Frame deadlines depend on display cadence; release-like traces/visual checks are needed to assess jank. [8] | Measure actual window/render deadlines on the S24, not tick counts or compile speed. | No handset FPS, power or superiority claim is made. |

Sources are official product/platform documentation retrieved for this review. Rollout, region, account and device restrictions can affect which comparator features are available. The comparator test must record those conditions.

## Audited findings and implemented repair batch

### U01 — Voice mode could restart recording

The Voice tab previously invoked the same action as beginning a new owner turn. Selecting a view is not the same intent as starting or restarting microphone capture. The repaired tab changes the presentation only. An explicit Start listening control invokes the existing voice owner, guarded against an already active turn. Microphone-on, microphone-off, processing and speaking labels derive from real capture/playback state, not the tab label.

Visible Send voice and Stop voice controls now sit alongside the current transcript. Stop voice cancels the local capture/pending speech context and playback; the UI explicitly states that submitted tasks continue. It does not impersonate a provider-side task-cancellation receipt. Input failures expose a retry-or-type alternative instead of silently leaving a misleading Listening label.

### U02 — Back and Escape were not a complete exit path

A keyboard Back/Escape first releases the input method, then returns the workboard to the resting character. API33+ system Back is bound to VAN's own window only when the board is active and the keyboard is not taking first refusal. Attachment/disposal listeners unregister the callback. A passive floating/docked character does not intercept another app's Back action. Dismissal preserves the in-process draft/selection and does not cancel a provider operation.

### U03 — A focused workboard could unnecessarily block outside taps

The native window now requests NOT_TOUCH_MODAL while retaining normal focus behavior for editable workboards. This means touches outside the window can belong to the underlying app. It does not promise click-through underneath covered pixels or evade Android's untrusted-overlay restrictions. Physical tap-routing and keyboard behavior remain part of acceptance.

### U04 — Hidden gestures were the only route to important actions

The character is identified as an actionable button with a state description and named alternatives for chat, Command Centre, voice, stop voice, minimize, dock and close. Four explicit accessible movement actions provide left/right/up/down steps without a fling or accidental dismiss gesture. Movement uses the same measured safe screen/keyboard bounds as direct dragging. Headers also expose movement alternatives.

Controls retain at least48dp interactive dimensions and meaningful roles. The minimized character's outer touch area, rather than only its smaller artwork, owns its interaction. A discovered overlapping draft implementation was reconciled to one canonical movement/submission/back owner; no duplicate listeners or competing helper classes are intentionally retained.

### U05 — Long conversations opened at the wrong place or lost useful history

The board now renders a virtualized complete history instead of truncating it to eight/fifty entries. First opening jumps directly to the current tail rather than animating from the beginning. Appended or updated replies follow only when the reader was already following. Deliberately reading older messages takes precedence over new replies. A visible Latest messages action resumes following and clears the unread marker.

A generation token prevents a cancelled programmatic scroll's cleanup from marking a newer scroll as user input. Streaming updates to the same message ID are included. A tall final reply now exposes its measured bottom instead of repeatedly aligning its top outside the readable tail; this uses one post-layout adjustment, not a new animation loop. Source tests exercise five thousand appended replies without moving a reader away from their chosen history position. Physical touch/fling/text-selection behavior is still a device test, not inferred from this policy test.

### U06 — Stale send callbacks could resubmit or erase the wrong draft

Submission is now bound to an observed local draft revision. Empty, busy, stale and duplicate callbacks cannot record another local owner message. Before clearing the draft, the UI checks that the existing command owner synchronously recorded the exact new OWNER message. A failed local record or synchronous error keeps the draft. A deliberate clear-and-retype permits intentionally repeating the same text.

This is a UI duplicate guard, not a substitute for command idempotency, approval or ambiguous remote-effect reconciliation. Network failures do not trigger automatic retries. In-flight, approval-needed and attention-needed feedback is visible and politely announced. Message authors are labelled, and text supports ordinary selection/copying.

### U07 — A trade tab could temporarily display stale results

Changing trade view or refreshing immediately restores Loading. Cancellation propagates, and an obsolete request rechecks coroutine activity before publishing its result. The board must not keep old-account/filter rows under a newly selected label or display a superseded cancellation as a new error. No order/execution authority or financial decision logic changed.

### U08 — Quick controls could fall beyond a narrow screen

The old fixed right-hand popup is replaced by a bounded, scrollable panel of the existing actions. It has a clear return-to-character control and preserves the original route semantics. The board still uses the previously implemented measured right/left/above/below placement planner, insets, keyboard bounds and restoration of the resting character position.

The source fixture set covers narrow/split/landscape spaces and larger font metrics. It does not prove device rendering or touch-target non-overlap at every font/display setting. The physical matrix below deliberately includes those cases.

### U09 — Lip and gaze samples could invalidate the whole workboard

Chrome now observes a derived semantic snapshot with transient mouth, viseme and gaze values removed. A separate character composable observes those live samples. Real health, task, approval, speech-mode and finite-action changes still update the board. A ten-thousand-sample test proves those transient values do not change the chrome snapshot while a separate check preserves the character samples and authoritative warning/offline behavior.

This is an architectural reduction in unnecessary invalidation, not a measured S24 speedup. Compose runtime measurements and actual GPU/window traces still have to establish the frame and power effects.

### U10 — User-rejected visual conventions must stay removed

The earlier line-free aura repair remains in place. This audit does not reintroduce field arcs, outline rings or oval specular strokes. Existing reduced-motion, visibility, thermal and performance policies remain binding. The native aura and companion orb are distinct. Character fingers/pointing/contextual motions remain the separately reviewed R5 candidate; source usability repairs do not promote that asset.

## Functionality review: what is and is not demonstrated

The overlay has concrete routes to Chat, Voice, Trades, Projects, Tasks, Decisions, Systems and Command Centre. Those are application routes, not cosmetic menu labels. The owner command/controller, voice coordinator and trading parser remain the functional owners. UI controls do not declare a command complete merely because an animation played.

Owned-interface guidance is a genuine existing candidate mechanism: current rectangles, same-window checks and live Rive direction inputs. It is not proof of arbitrary-app understanding. External-app recognition/clicking requires an explicitly authorized separate integration, and nothing in this audit expands that access.

In-process draft retention is checked across board changes; durable recovery after process death, clear task-specific progress at every VAN Next surface, and every extended contextual producer need separate evidence. Those gaps are not closed by the number of gestures or menu routes.

## Proposed physical acceptance protocol

These are proposed targets for qualification, not observed results and not universal industry standards. Use the exact installed APK/source/Rive hashes and compare equivalent tasks under recorded device/settings/network conditions.

| Scenario | Acceptance evidence required |
|---|---|
| Open near every edge/corner; portrait/landscape; keyboard open | Board remains usable in available space, controls accessible, resting anchor restored; no unintended app touch interception. |
| Back with editor focused; then Back again; floating-only Back | Keyboard closes first, board closes next, underlying app receives Back when VAN is passive; draft remains intact. |
| TalkBack, Switch Access, keyboard, large font | Named actions can open/move/dismiss without dragging; focus/order/state announcements are correct; no critical label truncation. |
| Voice-to-text, interrupt, error, hide and close | Actual mic indicator tracks capture; stop is immediate enough for the owner; no orphan recording/playback; tasks are not falsely cancelled. |
| Rapid Send/IME; edit draft while status changes | One local submission per draft lease; no stale text, erased unsubmitted draft or automated remote replay. |
| Long and streaming conversation; copy old text | Latest opens correctly; reading older content is stable; explicit Latest resumes; selection is not stolen by arrivals. |
| Trade filter/refresh during a pending read | Loading is clear; obsolete responses cannot be mislabeled; no stale data used as current. |
| Drag/dock/open/close plus speaking and aura | Proposed warm local feedback p95≤80ms; eligible local event visible p95≤100ms; declared gesture-admission target≤150ms except priority holds. Measure on device rather than assume. |
|60/120Hz active character with board | Record actual frame deadlines and p95/p99 frame durations; proposed ≤5% missed deadlines in a fixed repeatable workload, no sustained visible stutter. |
| Idle, hidden, screen-off, reduced motion, thermal pressure | No unnecessary hidden animation; effects reduce truthfully; no restored burst of missed animation time. |
|30-minute mixed use and repeated lifecycle changes | No monotonically growing retained memory; record thermal/power/battery baseline-vs-enabled comparison, not a fabricated consumption limit. |
| Owner visual assessment | No rejected aura arc lines; joints/fingers/expressions remain convincing at48/96/320dp; motion does not compete with the workboard for attention. |

For competitor comparisons, use repeated tasks on the same handset where products are available, record versions/account conditions and separate network/model latency from local UI feedback. Desktop Copilot and iPhone AssistiveTouch offer design references; their device timing is not an S24 apples-to-apples benchmark. A stronger VAN result must be demonstrated per axis rather than asserted globally.

## Release decision and remaining gaps

The audit supports continued integration of the repaired candidate. It does not support shipping as an already industry-superior product. Required remaining evidence includes an installable native APK with the admitted character, actual S24 overlay/voice/accessibility traces, source/asset identity readback, lifecycle and power testing, and the original owner artwork/character acceptance. Current ADB availability and exact compiler/test totals belong in the accompanying receipt, not assumptions embedded here.

Pending product-quality items include per-surface contextual adapters, durable interrupted-draft recovery, user-configurable unobtrusiveness/gesture preferences where admitted, completion of the planned micro-motion/finger repertoire, and acting polish. The correct differentiator is useful, controllable, smoothly animated guidance—not more constant movement or more screen coverage.

## Sources (official, retrieved5November2026)

[1] Google, Talk naturally with Gemini Live: https://support.google.com/gemini/answer/15274899?hl=en

[2] Microsoft, Get started with vision in Microsoft Copilot: https://support.microsoft.com/en-au/microsoft-365-copilot/get-started-vision-microsoft-365-copilot

[3] Apple, Use AssistiveTouch on iPhone: https://support.apple.com/en-lamr/guide/iphone/-iph96b21954/ios

[4] Samsung, Use Interaction & Dexterity Features (updated30June2026): https://www.samsung.com/ae/support/mobile-devices/how-to-use-interaction-and-dexterity-enhancement-features-on-your-galaxy-phone/

[5] Android Developers, Use notification bubbles for conversations: https://developer.android.com/develop/ui/compose/notifications/bubbles

[6] Android Developers, Compose semantics: https://developer.android.com/develop/ui/compose/accessibility/semantics

[7] Android Developers, Accessibility API defaults: https://developer.android.com/develop/ui/compose/accessibility/api-defaults

[8] Android Developers, Slow rendering: https://developer.android.com/topic/performance/issues/render
