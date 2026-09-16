# VAN Production Visual, Floating UX & Owner-Admin Control System

## Canonical Reconciliation & Implementation Blueprint — Rev 3.0

**Repository:** `Vanguduza/Van`  
**Implementation baseline:** PR #5 / `feature/living-windy-aura`  
**Owner-device authority:** the physical Samsung verification that exposed character transparency, body-hugging aura, static workboard behavior and non-interactive control surfaces supersedes preview-only acceptance.  
**Status:** mandatory corrective implementation; owner visual/UX acceptance remains open until a corrected APK is reverified on-device.

---

## 1. Product invariant

VAN is not a floating dashboard mascot. VAN is the owner's persistent mobile administrative control surface into Hermes, DIAL, projects, tasks, decisions, approvals, system health, conversations, execution commands and privileged operational actions.

The floating character is the smallest expression of that control system. The same owner-command authority must be available through:

```text
Floating VAN
  ├─ Workboard
  │   ├─ Chat
  │   ├─ Voice
  │   ├─ Current work / response
  │   └─ Context actions
  ├─ Long-press quick controls
  └─ Command Centre
      ├─ Overview
      ├─ Chat
      ├─ Decisions
      ├─ Tasks
      ├─ Projects
      ├─ Activity
      ├─ Systems / Hermes
      ├─ Connections
      └─ Settings
```

Every production surface must operate on real authoritative state. Production UI must not present hard-coded projects, fake progress, fabricated decisions or synthetic success as live truth.

---

## 2. Confirmed device failures

The current installed build exposed six blocker classes:

| Area | Current symptom | Required production result |
| --- | --- | --- |
| Character | VAN appears glassified / overly transparent | VAN body remains optically solid |
| Aura | body-hugging, weakly animated, little electrical life | detached, wavy, windy, continuously animated electric atmosphere |
| Workboard | opens but lacks intuitive close/resize/scroll behavior | single-tap toggle, scroll, expand, maximize |
| Gesture UX | missing deterministic double-tap / long-press / dismiss semantics | one canonical gesture state machine |
| Command Centre | primarily static information panels | real navigable admin console with actions |
| VAN animation | character can appear frozen after board opens | body + attention + face + field animation continue regardless of board |

These are architecture defects, not cosmetic polish.

---

## 3. State architecture: orthogonal domains

Keep state concerns independent.

```kotlin
data class VanRuntimeState(
    val presence: VanPresenceFrame,
    val overlay: VanOverlayUiState,
    val animation: VanAnimationState,
    val conversation: VanConversationUiState,
    val admin: VanAdminUiState,
)
```

`VanPresenceFrame` remains authoritative for activity, health, authority, speech, turn, attention, mouth/viseme, urgency and finite action. Overlay presentation must never overwrite presence.

Valid simultaneous state example:

```text
activity      = WORKING
speech        = SPEAKING
health        = DEGRADED
board         = WORKBOARD_EXPANDED
authority     = NONE
```

Opening a board must not change activity. Speaking must not erase WORKING. Non-uplink degradation must not suppress local LISTENING/THINKING/SPEAKING/WORKING. Minimizing is a presentation change only.

---

## 4. Floating presentation states

Use explicit UI presentation state:

```kotlin
enum class VanOverlayPresentation {
    FULL_FLOATING,
    WORKBOARD_COMPACT,
    WORKBOARD_EXPANDED,
    WORKBOARD_MAXIMIZED,
    MINIMIZED,
    DOCKED,
}

enum class VanQuickControlsState { HIDDEN, VISIBLE }

data class VanOverlayUiState(
    val presentation: VanOverlayPresentation = VanOverlayPresentation.FULL_FLOATING,
    val quickControls: VanQuickControlsState = VanQuickControlsState.HIDDEN,
    val dragging: Boolean = false,
    val dismissTargetVisible: Boolean = false,
    val dismissTargetArmed: Boolean = false,
    val xPx: Int = 0,
    val yPx: Int = 0,
)
```

Persist only position, presentation, dock edge, running state and last sensible non-minimized anchor. Do not persist transient drag/gesture state.

---

## 5. Canonical gesture contract

Gesture behavior is locked:

| Gesture on VAN | Result |
| --- | --- |
| Single tap while board closed | open compact workboard |
| Single tap while any workboard is open | close workboard |
| Double tap | open Command Centre |
| Long press | open quick controls |
| Drag | reposition VAN |
| Drag into bottom dismiss target | stop floating VAN |
| Tap minimized VAN | restore full floating VAN |
| Double tap minimized VAN | open Command Centre |

A double tap must not first execute the single-tap action. Long press must not emit tap. Drag must not emit tap.

Use one canonical event model:

```kotlin
sealed interface VanGestureEvent {
    data object SingleTap : VanGestureEvent
    data object DoubleTap : VanGestureEvent
    data object LongPress : VanGestureEvent
    data class DragStart(val screenX: Float, val screenY: Float) : VanGestureEvent
    data class DragDelta(val dx: Float, val dy: Float) : VanGestureEvent
    data class DragEnd(val screenX: Float, val screenY: Float) : VanGestureEvent
}
```

Only VAN or an explicit drag handle may move the overlay. Never put global drag handling around the workboard; board scroll/touch gestures belong to the board.

---

## 6. Tap reducer contract

```kotlin
object VanOverlayReducer {
    fun singleTap(s: VanOverlayUiState): VanOverlayUiState = when (s.presentation) {
        VanOverlayPresentation.FULL_FLOATING ->
            s.copy(presentation = VanOverlayPresentation.WORKBOARD_COMPACT)

        VanOverlayPresentation.WORKBOARD_COMPACT,
        VanOverlayPresentation.WORKBOARD_EXPANDED,
        VanOverlayPresentation.WORKBOARD_MAXIMIZED ->
            s.copy(presentation = VanOverlayPresentation.FULL_FLOATING)

        VanOverlayPresentation.MINIMIZED,
        VanOverlayPresentation.DOCKED ->
            s.copy(presentation = VanOverlayPresentation.FULL_FLOATING)
    }.copy(quickControls = VanQuickControlsState.HIDDEN)
}
```

Double tap produces navigation (`OpenCommandCentre`) and does not mutate the board first.

---

## 7. Long-press controls

Long press reveals real controls:

- Chat
- Voice
- Minimize
- Command Centre
- Dock
- Close

Behavior:

- **Chat:** open workboard in chat mode and focus text input.
- **Voice:** open voice mode and begin the owner turn.
- **Minimize:** animate full VAN into a circular face icon.
- **Command Centre:** launch the full admin console.
- **Dock:** enter edge-docked presentation.
- **Close:** explicit secondary dismissal path; drag-to-X remains the natural physical gesture.

Every control must execute real behavior.

---

## 8. Drag-to-dismiss

Because VAN uses a custom application overlay, implement an Android-native-style bottom-centre dismiss target as a second overlay/window rather than assuming the system Bubble target is available.

State sequence:

```text
DRAG START
  → show bottom X

VAN enters target
  → enlarge target
  → haptic tick
  → dismissTargetArmed = true

VAN leaves target
  → shrink target
  → dismissTargetArmed = false

release inside
  → stop overlay service
  → remove all overlay windows
  → persist running=false

release outside
  → hide target
  → snap/dock normally
```

Recommended target: 64–76 dp visual, 96–120 dp hit region, positioned above navigation insets.

---

## 9. Minimized VAN

Minimized VAN is a circular portrait, not a narrow dock strip and not a generic cyan bubble.

Suggested geometry:

```text
visual circle    58–64 dp
touch target     >= 64 dp
face occupation  70–82% of diameter
```

Identity priorities:

1. silver/white swept hair;
2. medium-brown face;
3. cyan visor;
4. readable blue-eye region where scale permits;
5. recognisable headband / facial silhouette.

Minimized motion must be quiet but alive: blink, tiny gaze shift and restrained cyan rim pulse. No bouncing bubble or rotating ring.

Single tap restores full VAN. Double tap opens Command Centre. Drag repositions. Drag to X closes.

Transition full→minimized and minimized→full should animate over roughly 180–280 ms by collapsing/expanding around the face anchor; underlying activity state is preserved.

---

## 10. Launcher icon

The Android launcher icon must use the same canonical VAN face identity as minimized VAN.

Do not use a generic AI glyph, letter V, holographic orb or crude robot head.

Create one portrait authority and derive launcher/minimized resources from it. Keep important facial features inside adaptive-icon safe zones. Test circle, squircle, rounded-square and Samsung One UI masks.

Launcher icon is static; minimized floating VAN may be subtly animated.

---

## 11. Character opacity contract

VAN himself is not glass.

Only visor optics, holographic elements, aura and UI glass may use substantial translucency.

```kotlin
enum class VanVisualLayer {
    CHARACTER_BODY,
    HAIR,
    EYES,
    VISOR_GLASS,
    HOLOGRAM,
    AURA,
    UI_GLASS,
}
```

Nominal skin/hair/jacket/eye alpha must remain effectively 1.0. DEGRADED/OFFLINE should use desaturation, lower luminance, muted accents and semantic field changes rather than character transparency.

Owner-art images may have transparent background, but interior body pixels must not be globally faded.

---

## 12. Rendering composition

Canonical draw order:

```text
background application / Android content
outer semantic field
middle identity/activity field
rear particles
glass workboard
solid VAN character
front-safe particles / sparse electric accents
interactive controls
```

Never place VAN's full character inside a compositing group whose alpha exists to make the board glass.

---

## 13. Baby-blue cyan glass

Canonical optical palette:

```text
Baby Cyan          #BDEFFF
Bright Ice Cyan    #D9FAFF
Structural Cyan    #62EAF7
Deep Optical Navy  #071722
Dark Backing       #051018
Primary Text       #F6FDFF
Secondary Text     #BCD1D8
```

With live blur, use roughly 0.50–0.64 absorber alpha plus 0.10–0.18 cyan optical tint. Without blur, use a stronger backing (roughly 0.76–0.88) so the board remains readable.

Use selective inner highlight, fine grain, local cyan contamination and restrained specular edges. Avoid uniform neon outlines.

---

## 14. Living aura Rev 3

Retain orthogonal identity/activity Zone B and semantic Zone C, but replace the visually body-hugging result with a real detached field.

The field must be:

- continuously advecting;
- visibly wavy;
- asymmetric;
- non-ring topology;
- detached from body silhouette;
- electrically alive;
- state-sensitive;
- deterministic enough for reproducible evidence.

Extend the aura specification with physical controls such as:

```kotlin
data class VanAuraDynamics(
    val fieldRadius: Float,
    val windDirectionRad: Float,
    val windStrength: Float,
    val turbulence: Float,
    val curlStrength: Float,
    val waveAmplitude: Float,
    val waveFrequency: Float,
    val waveSpeed: Float,
    val particleDensity: Float,
    val electricalActivity: Float,
    val electricalBranching: Float,
    val interactionAttractorX: Float,
    val interactionAttractorY: Float,
    val glassCondensation: Float,
)
```

---

## 15. Silhouette-aware exclusion

Do not rely only on a single central ellipse. Approximate head/hair, torso and visible limbs with renderer-neutral exclusion primitives and inflate by a visible air gap.

```kotlin
sealed interface ExclusionPrimitive {
    data class Ellipse(
        val cx: Float,
        val cy: Float,
        val rx: Float,
        val ry: Float,
    ) : ExclusionPrimitive

    data class Capsule(
        val ax: Float,
        val ay: Float,
        val bx: Float,
        val by: Float,
        val radius: Float,
    ) : ExclusionPrimitive
}
```

For a ~92 dp floating character, target roughly:

- minimum visible aura/body gap: 10–14 dp;
- normal middle-field gap: 16–28 dp;
- outer-field excursions: 30–48 dp.

No main field strand may continuously trace the body outline.

---

## 16. Vector-field motion

Each seeded filament should combine base streamline, directional wind, low-frequency wave, higher-frequency ripple, curl and state-specific attraction.

Illustrative formulation:

```kotlin
fun flowPoint(
    origin: Vec2,
    tangent: Vec2,
    normal: Vec2,
    u: Float,
    t: Float,
    p: FieldParams,
    seed: Float,
): Vec2 {
    val advected = u + t * p.advectionSpeed
    val waveLow = sin(TAU * (p.waveFrequency * u - p.waveSpeed * t + seed))
    val waveHigh = sin(TAU * (p.waveFrequency * 2.7f * u + p.waveSpeed * 1.4f * t + seed * 1.91f))
    val curl = sin(TAU * (u * 1.3f + t * 0.31f + seed * 0.73f)) * p.curlStrength
    val across = p.waveAmplitude * (waveLow + waveHigh * 0.22f) + curl
    return origin + tangent * ((advected - 0.5f) * p.length) + normal * across
}
```

Use stable seeds. Motion must deform/travel rather than merely pulse opacity.

---

## 17. Non-ring invariant

A full or broken halo is forbidden. Major strands must vary origin, curvature, radial distance, phase, length, local wind angle and velocity.

Automated evidence should reject geometry that collapses onto a common radius around the character. A frozen still must read as atmospheric flow, not as `( VAN )`.

---

## 18. Electrical-life subsystem

Add explicit short-lived electric structures rather than representing all electricity as dots.

```kotlin
data class VanElectricalBranch(
    val trunk: List<VanFieldPoint>,
    val children: List<List<VanFieldPoint>>,
    val intensity: Float,
    val lifetime: Float,
    val progress: Float,
    val ink: VanFieldInk,
)
```

Events appear, propagate along field strands, fork irregularly, bloom, fade and die. They must not remain as a permanent body outline.

State behavior:

- IDLE: rare micro-discharge;
- LISTENING: directional pulses;
- THINKING: travelling computation-like pulses;
- SEARCHING: scanning bursts;
- WORKING: stronger active propagation;
- WAITING_FOR_OWNER: sparse amber tension;
- WARNING: sharper amber forks;
- ERROR: fractured red branches;
- URGENT: denser/faster red impulses;
- SUCCESS: short green outward release.

No strobing or full-field flashes.

---

## 19. Particle lifecycle

Particles require deterministic lifetimes: spawn → advect → curl → fade → expire. Do not leave them as static points.

Cache stable topology and update only dynamic coordinates/age each frame to avoid excessive allocation.

---

## 20. Glass condensation from field

Opening a board should visually condense selected field strands into cyan optical glass while residual field remains alive.

Conceptual progression:

```text
0.0  field independent
0.2  selected strands curve toward future board boundary
0.5  strands broaden / slow / refract
0.75 optical material appears
1.0  board glass fully formed; residual aura continues
```

Closing reverses this process. Board existence must never turn the aura off.

---

## 21. Character animation system

VAN must be continuously alive whenever visible.

Create an independent animation frame:

```kotlin
data class VanCharacterAnimationFrame(
    val timeSeconds: Float,
    val hoverY: Float,
    val breathing: Float,
    val torsoTiltDeg: Float,
    val headTiltDeg: Float,
    val gazeX: Float,
    val gazeY: Float,
    val blink: Float,
    val leftHandPose: Float,
    val rightHandPose: Float,
    val mouthOpen: Float,
    val viseme: Int,
    val stateBlend: Float,
)
```

Character animation and board presentation are independent. Opening a board must not choose a static "board pose" or restart animation phase.

---

## 22. Monotonic animation clock

Use one monotonic visual clock for character, aura, particles and transient electric events. Do not restart it on recomposition or board transitions.

A Compose frame clock or application animation runtime is acceptable; continuity is mandatory.

---

## 23. Baseline lifelike motion

Idle life combines asynchronous low-amplitude movement:

- hover drift (~3.5–5.5 s period);
- breathing (~3–4.5 s);
- counter-motion head stabilization;
- seeded blink intervals (~2.6–6.4 s) with rare double blink;
- small gaze changes;
- minor hand/posture settling;
- subtle hair/visor secondary motion;
- orb drift.

Do not synchronize all phases.

The interim owner-art transform must remain within 1.6 dp horizontal displacement, 2.5 dp
vertical displacement, 1.65 degrees of rotation, scale 0.992–1.008 and 0.5 degrees of head
counter-motion across all states, attention directions and urgency levels. These bounds preserve
the stronger phone-visible Rev 3 motion without allowing cartoon bouncing.

Reduced motion removes all phase-driven hover, breathing, sway and tension. A static owner-facing
attention pose may retain up to 0.45 dp horizontal lean and 0.12 degrees of tilt, clamped to the
attention input. Vertical displacement and head counter-motion are zero and scale remains 1.0.
The neutral attention pose has zero lean and tilt. Advancing animation time must not change the pose.

---

## 24. State-specific body behavior

**LISTENING:** slight forward inclination, owner-facing gaze, restrained acknowledgement.  
**THINKING:** more stable torso, small eye/head motion, stronger computation-like field dynamics.  
**SEARCHING:** gaze/head scan with directional field sweep.  
**WORKING:** deliberate posture, slightly higher energy and subtle hand activity.  
**DELEGATING:** short outward/presenting gesture.  
**SPEAKING:** viseme/mouth motion, subtle head emphasis, occasional hand gesture.  
**WAITING_FOR_OWNER:** attentive hold and restrained prompt gesture.  
**SUCCESS:** short nod/release then smooth return to underlying activity.  
**WARNING/ERROR/URGENT:** posture tension and stronger field dynamics, never frantic cartoon shaking.

---

## 25. Smooth pose transitions

Pose/state changes must blend rather than snap.

Suggested ranges:

```text
IDLE → LISTENING       180–280 ms
LISTENING → THINKING   220–360 ms
THINKING → WORKING     220–420 ms
WORKING → SPEAKING     160–240 ms
ANY → URGENT           120–200 ms
```

Use restrained fast-out-slow-in or low-overshoot spring behavior.

---

## 26. Workboard architecture

The floating workboard is current context + immediate action, not a miniature static dashboard.

```kotlin
enum class VanWorkboardMode {
    CONTEXT,
    CHAT,
    VOICE,
    APPROVAL,
    TASK,
}
```

**Compact:** status, current work/response, health cue, quick actions, expand handle.  
**Expanded:** header, scrollable body, contextual controls, input area.  
**Maximized:** near-full-height glass surface for deep conversation/task/detail work while remaining visually attached to VAN.

Use bounded dynamic height rather than fixed ~148 dp expanded content.

---

## 27. Board scrolling and resizing

Use `LazyColumn`/`verticalScroll` inside the board. Board scrolling must never move VAN.

Explicit affordances handle expand/collapse/maximize. Single-tap VAN remains reserved for board open/close.

Recommended bounds:

- compact width ~280–320 dp, content-driven bounded height;
- expanded width `min(screenWidth - 24dp, ~360dp)`, max ~55–65% usable height;
- maximized height ~80–88% usable screen.

---

## 28. Typed chat

Typed chat is a real owner-control interface, not a local demo.

```kotlin
data class VanMessage(
    val id: String,
    val threadId: String,
    val role: VanMessageRole,
    val text: String,
    val projectId: String?,
    val commandId: String?,
    val delivery: VanMessageDelivery,
    val createdAtEpochMs: Long,
)
```

Conversation UI requires thread, text entry, send, mic, selected project/context, command delivery state, response state, retry and cancellation where supported.

Never persist gateway secrets, biometric tokens, passwords or OAuth access tokens in conversation history.

---

## 29. Voice

Existing Android SpeechRecognizer/TTS may remain, but final transcript must enter the same command pipeline as typed input.

```kotlin
data class VanVoiceUiState(
    val listening: Boolean = false,
    val partialTranscript: String = "",
    val finalTranscript: String? = null,
    val error: VanVoiceError? = null,
)
```

Flow:

```text
Voice selected
→ LISTENING
→ partial transcript visible
→ final transcript
→ THINKING
→ unified command submit
→ gateway / Hermes
→ response/status
→ optional TTS / SPEAKING
```

---

## 30. Unified owner-command controller

All command sources converge through one controller.

```kotlin
enum class VanCommandSource {
    CHAT,
    VOICE,
    QUICK_ACTION,
    DECISION,
    TASK,
    PROJECT,
    SYSTEM,
}

data class VanOwnerCommand(
    val text: String,
    val source: VanCommandSource,
    val projectId: String? = null,
    val actionClass: String = "A1",
    val approvalToken: String? = null,
    val idempotencyKey: String,
)
```

Typed chat, voice transcript and module actions all call `VanCommandController.submit`. There must be no parallel insecure path.

---

## 31. Security boundary

Do not give Android UI direct shell/SSH execution.

Canonical path:

```text
VAN UI
→ VanCommandController
→ authority policy
→ signed VanGatewayClient
→ gateway
→ Hermes
→ workers / project systems
```

Preserve action classes:

```text
A1 read / observation
A2 bounded reversible action
A3 significant operational change
A4 destructive / high-impact privileged action
```

A4 remains biometric-gated. Elevated confirmation must show target, action, risk class and expected effect.

---

## 32. Truthful command lifecycle

Never treat `accepted` or `in_flight` as success.

```kotlin
enum class VanCommandStatus {
    LOCAL_DRAFT,
    SUBMITTING,
    APPROVAL_REQUIRED,
    ACCEPTED,
    IN_FLIGHT,
    SUCCEEDED,
    FAILED,
    CANCELLED,
    EXPIRED,
}
```

Consume authoritative completion through SSE, WebSocket or bounded authenticated polling when backend support exists. SUCCESS visual semantics only follow confirmed completion.

---

## 33. Command Centre navigation

Replace the single static scrolling board with real destinations:

```text
Overview
Chat
Decisions
Tasks
Projects
Activity
Systems / Hermes
Connections
Settings
```

For phones, use a compact bottom-navigation / "More" arrangement rather than desktop density.

---

## 34. Overview

Aggregate live truth:

- VAN current state;
- active work;
- pending owner decisions;
- important tasks;
- recent failures;
- Hermes and gateway health;
- selected project context;
- background queue count.

Every meaningful item must lead to a real destination/action.

---

## 35. Decisions

A decision record should include ID, origin/project, summary, reason owner input is required, action/risk class, available choices, supporting evidence, expiry where applicable and current status.

Owner actions: inspect evidence, select/approve, reject, defer and add instruction. Use authoritative gateway/backend data.

---

## 36. Tasks

Task model should expose real execution work:

```kotlin
data class VanTask(
    val id: String,
    val projectId: String?,
    val title: String,
    val status: VanTaskStatus,
    val progress: Float?,
    val startedAt: Long?,
    val updatedAt: Long,
    val executionTarget: String?,
    val ownerActionRequired: Boolean,
)
```

Only expose inspect/instruct/pause/resume/cancel/retry controls when the backend actually supports them.

---

## 37. Projects

Projects must be discovered from authoritative system/project registries, not hard-coded Android lists.

Each project should expose name/ID, mission/status, active work, attention count, recent update and health. Project detail provides active tasks, decisions, activity, health and a context-bound chat/instruction field that propagates `projectId` through the owner-command pipeline.

---

## 38. Systems / Hermes

Expose real gateway/Hermes/device/queue/worker/Google-mesh/degraded-subsystem truth without exposing secrets.

---

## 39. Shared repositories

Floating workboard and Command Centre must consume the same application-scoped repositories:

```text
VanConversationRepository
VanDecisionRepository
VanTaskRepository
VanProjectRepository
VanSystemRepository
VanCommandRepository
VanPresenceRepository
```

All modules support explicit loading, ready, empty and error states.

---

## 40. Production placeholder prohibition

Production source must not masquerade fixtures as live truth. Remove hard-coded project arrays, fake progress, fake connection health and placeholder decision/task content.

Test/preview source sets may use fixtures. Production empty/error states must say truthful things such as `No decisions returned`, `Gateway unavailable`, or `Projects could not be loaded`.

---

## 41. Lifecycle split

Keep `FloatingOverlayService` responsible for WindowManager/service lifecycle, not all domain state.

Recommended split:

```text
FloatingOverlayService      overlay windows / foreground service
VanOverlayController        UI presentation + gestures
application repositories    domain truth
VanAnimationRuntime         monotonic animation clock + pose dynamics
```

---

## 42. Performance and power policy

Normal target: 60 fps; gracefully degrade toward 30 fps under thermal/power pressure.

Avoid rebuilding stable topology every frame, unbounded particle lists and excessive full-window blur.

Render budgets should reduce particle/branch density and blur before freezing core body life. Reduced-motion accessibility remains separate from battery saving and may remove autonomous hover/advection while preserving essential state, speech and attention changes.

---

## 43. Rive compatibility

Rive remains external/not READY until the real asset exists and passes device certification. When it lands, it must obey this same Rev 3.0 product contract: opaque body, continuous animation, attention, mouth/viseme, state transitions, board independence and identical interaction semantics.

Rive is a renderer, not a different product behavior path.

---

## 44. Required source boundaries

Recommended conceptual source structure:

```text
animation/
  VanAnimationClock.kt
  VanCharacterAnimator.kt
  VanPoseTransition.kt
  VanBlinkScheduler.kt
visual/
  VanEmbodiment.kt
  VanCharacter.kt
  VanAura.kt
  VanAuraSpec.kt
  VanFieldTopology.kt
  VanFieldGeometry.kt
  VanElectricalField.kt
  VanBodyExclusionProfile.kt
  VanGlassSurface.kt
  VanGlassTokens.kt
overlay/
  FloatingOverlayService.kt
  VanOverlayUiState.kt
  VanOverlayReducer.kt
  VanGestureController.kt
  VanWorkboard.kt
  VanQuickControls.kt
  VanDismissTarget.kt
  VanMinimizedAvatar.kt
control/
  VanCommandController.kt
  VanOwnerCommand.kt
chat/
  VanMessage.kt
  VanConversationRepository.kt
voice/
  VoiceInterfaces.kt
command/
  CommandCentreActivity.kt
  CommandCentreNav.kt
projects/ tasks/ decisions/ system/
  authoritative repositories and models
```

Agents may consolidate files, but must preserve these responsibility boundaries.

---

## 45. Automated test requirements

### Overlay / gestures

- full floating + single tap → compact board;
- compact/expanded/maximized + single tap → full floating;
- minimized + single tap → full floating;
- double tap opens Command Centre with zero board-toggle side effect;
- long press emits no tap;
- drag emits no tap;
- Minimize preserves `VanPresenceFrame`;
- board scrolling does not move overlay;
- drag-target enter/exit/armed/dismiss behavior works.

### Character

- body opacity invariant;
- degraded/offline cannot globally fade character;
- animation clock advances while board is open;
- opening/closing board cannot mutate activity;
- state transitions interpolate rather than snap.

### Aura

- no main field sample enters the inflated body exclusion profile;
- motion-enabled phase samples differ;
- reduced-motion/static budgets obey policy;
- common-radius ring reconstruction is rejected;
- electrical branches appear only where required and remain outside protected face/body regions;
- electrical branches have finite lifetime.

### Command path

- typed chat and voice final transcript call the same command controller;
- `projectId` propagates;
- idempotency key is present;
- A4 cannot bypass approval;
- ACCEPTED/IN_FLIGHT do not become SUCCEEDED.

### Command Centre

Every module must expose loading/ready/empty/error and real navigation.

---

## 46. Rev 3.0 visual evidence

Generate under `artifacts/release/preview/rev30/`:

```text
van_character_opacity.png
van_character_motion_strip.png
van_aura_detachment.png
van_aura_motion_strip.png
van_electric_life_strip.png
van_field_with_workboard.png
van_workboard_compact.png
van_workboard_expanded.png
van_workboard_maximized.png
van_quick_controls.png
van_minimized_face.png
van_launcher_icon_masks.png
van_chat.png
van_voice.png
van_command_centre_modules.png
van_drag_dismiss.png
```

Motion evidence must contain multiple timestamps; a single still cannot certify animation.

---

## 47. Physical Samsung acceptance

Final owner acceptance requires device verification:

1. VAN remains solid over light, dark and busy backgrounds.
2. Aura is visibly detached, wavy and continuously changing for at least 30 seconds.
3. Electrical pulses/branches are visible without strobing or halo reconstruction.
4. Single tap opens/closes board.
5. Double tap opens Command Centre from full, board-open and minimized states.
6. Long press exposes working quick controls.
7. Minimize produces a clear circular VAN-face icon; single tap restores full VAN.
8. Launcher icon unmistakably shows VAN's face.
9. Board scroll/expand/maximize works without moving VAN.
10. Drag shows a bottom dismiss target and drop closes floating VAN cleanly.
11. VAN continues blinking, hovering, gazing, changing state and animating aura while the board is open.
12. Chat dispatches a harmless real owner command through the signed gateway.
13. Voice shows transcript and enters the same command lifecycle.
14. Decisions, Tasks, Projects and Systems are navigable and backed by authoritative data.

Only the owner may mark final device visual/UX acceptance.

---

## 48. CI gates

Required gates:

```text
:app:testDebugUnitTest
:app:lintDebug
:app:assembleDebug
:visual-preview:test
:visual-preview:renderVanPreviews
```

Add Compose/instrumentation tests where runner support exists. CI should fail if required evidence or launcher identity assets are missing or if production source contains prohibited placeholder patterns outside explicit test/preview fixtures.

---

## 49. Implementation order

### Phase A — visual correctness

1. remove global body alpha/glassification;
2. isolate character and glass layers;
3. update baby-cyan glass material;
4. strengthen silhouette exclusion;
5. rebuild wavy field motion;
6. add electrical branches/particle lifetime;
7. implement field→glass condensation.

### Phase B — character life

8. monotonic animation clock;
9. body micro-motion;
10. gaze/blink;
11. state pose interpolation;
12. prove board-open animation continuity.

### Phase C — overlay UX

13. explicit overlay presentation state;
14. deterministic gesture arbitration;
15. single-tap toggle;
16. double-tap Command Centre;
17. long-press controls;
18. minimized circular face;
19. drag-to-dismiss;
20. explicit board expansion/maximize;
21. board scrolling.

### Phase D — owner control

22. unified command controller;
23. typed chat;
24. voice dispatch;
25. conversation state;
26. truthful command lifecycle.

### Phase E — admin console

27. module navigation;
28. decisions;
29. tasks;
30. projects;
31. systems;
32. shared repositories.

### Phase F — certification

33. tests;
34. Rev 3.0 evidence;
35. Samsung device verification;
36. owner sign-off.

---

## 50. Hard prohibitions

The implementation must never:

- glassify VAN's body;
- solve the aura by drawing a larger ring;
- freeze VAN because a workboard opened;
- use GIF/video loops as aura motion;
- use color alone for semantic state;
- let board scroll gestures drag the overlay;
- cycle board sizes from single-tapping VAN;
- use a generic minimized bubble instead of VAN's face;
- use an unrelated launcher icon;
- fake project/task/decision/system data;
- make Chat a disconnected demo;
- make Voice transcript-only;
- bypass gateway authority;
- call accepted/in-flight work success;
- weaken A4 biometric policy;
- claim Rive READY without a real `.riv` loading and binding on-device.

---

## 51. Definition of done

Rev 3.0 is complete only when all are true:

```text
VAN character     solid, recognisable, continuously alive
Aura              detached, wavy, windy, electrically active
Glass             baby-cyan optical UI material only
Single tap        opens/closes workboard
Double tap        opens Command Centre
Long press        real quick controls
Minimize          circular live VAN-face icon
Launcher          canonical VAN-face icon
Drag              reposition + bottom-X dismissal
Workboard          scrollable, expandable, maximizable, actionable
Chat              real owner command pipeline
Voice             same owner command pipeline
Command Centre    interactive admin console
Projects/tasks/
decisions/systems authoritative live data
Security           signed gateway + action classes + biometric high-risk gates
Results            truthful lifecycle through authoritative completion
Animation          continuous across every visible presentation
Evidence           Rev 3.0 generated and inspected
Device             owner accepts corrected Samsung build
```

---

## 52. Canonical implementation statement

> **VAN is a continuously alive, optically solid character—not a translucent status widget. He exists inside a detached, wavy, continuously advecting electrical atmosphere. Cyan glass UI condenses from that field only when interaction requires it and never glassifies VAN himself. Single tap toggles the workboard, double tap opens the full administrative Command Centre, long press exposes quick controls, drag repositions VAN and enables bottom-X dismissal, and Minimize collapses VAN into a circular live portrait of his face. The launcher icon uses the same canonical face. The workboard, typed chat, voice interaction and Command Centre are all secure interfaces into one unified owner-command path through the signed VAN gateway to Hermes and the wider system. VAN's body animation, attention, speech motion and living field continue regardless of whether the workboard is open. No static placeholder board, fake module data, fake success state, body-hugging halo, disconnected chat path or visual-only control is acceptable.**
