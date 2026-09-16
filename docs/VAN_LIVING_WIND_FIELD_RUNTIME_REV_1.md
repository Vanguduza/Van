# VAN Living Wind Field Runtime — Rev 1

Status: implementation companion to commit `a6756df` / Rev 2.2 aura topology  
Scope: Android floating overlay, Canvas/owner-art/Rive-compatible state inputs, reduced-motion and power fallbacks

## 1. Purpose

The Rev 2.2 aura in `a6756df` established the correct three-zone semantic ownership, but its shipping Canvas implementation still used broken ellipses/arcs. Even when fragmented, those arcs shared a common centre and radius, so the eye reconstructed a halo around VAN.

Rev 1 changes the runtime model from **orbit geometry** to a **directional living field**. VAN is now visually located inside a small windy electrical atmosphere. The field is continuously sampled from deterministic time/state parameters; it is not a GIF, sprite loop or pre-rendered video.

“Lifelike” and “attention-aware” in this document describe animation behaviour only. They do not assert that VAN is conscious.

## 2. Runtime layers

The field keeps the existing three semantic zones:

- **Zone A — identity presence:** restrained cyan radiance and a shallow ground crescent. It breathes by only a few percent so it never becomes a pulsing disk.
- **Zone B — interaction field:** detached travelling ribbons, ion streaks, small sparks and the orb bridge. This is the main windy/electrical motion layer.
- **Zone C — semantic envelope:** sparse outer flow ribbons carrying warning/error/success/waiting colour. Semantic colour remains outside the body.

No renderer may reconstruct a full circular ring. Zone B/C strands are directional flow lines and are cut away inside a body-safe ellipse.

## 3. Motion equation

`VanWindFieldMotion` produces one deterministic `VanWindFieldFrame` from `(VanAuraSpec, phase, VanEffectBudget)`.

Each ribbon is sampled along a wind-aligned axis. Its cross-flow displacement combines several harmonics:

```text
w(u,t) = A · [ sin(2π(2u − 2t + s))
             + 0.38 sin(2π(3u + 3t + 1.71s))
             + 0.14 sin(2π(5u − t + 0.47s)) ]
```

A lower-amplitude curl term bends the longitudinal direction. Because every temporal term uses integer cycles, phase `0` and phase `1` are identical: the Compose infinite transition can wrap without a visible seam.

The field frame also supplies:

- slow breathing;
- prevailing wind direction plus bounded meander;
- state-derived wind strength;
- turbulence;
- wave amplitude;
- electrical pulse intensity;
- particle advection;
- effect-budget field scale.

## 4. State semantics

The existing `VanAuraSpecs.forState()` remains the authority for state meaning. The same motion system therefore changes character by parameter rather than swapping animations:

| State family | Motion behaviour |
| --- | --- |
| IDLE / WAITING | low wind, low turbulence, sparse ion movement |
| ATTENTIVE / LISTENING | stronger convergent-looking flow and orb activity |
| THINKING / SEARCHING | moderate travelling waves and information-like particle motion |
| WORKING | highest normal wind, wave amplitude, filament count and spark density |
| SPEAKING | moderate field while mouth/viseme inputs animate VAN |
| WAITING_FOR_OWNER | amber semantic envelope, deliberate low-frequency motion |
| WARNING / ERROR / URGENT | semantic outer colour plus sparse electrical branching |
| SUCCESS | green semantic outer flow; calm positive field rather than an alert flash |
| OFFLINE / SLEEPING | very low energy; readable field remains |

## 5. Lifelike character motion

The field is not the only moving layer.

- The procedural Canvas rig already animates body bob, head bob, blink, orb drift, gaze, mouth/visemes and finite actions.
- Owner bitmap poses now pass through `VanCharacterMotion`, which applies tiny state-aware bob, lateral drift, sway and breathing scale. This prevents the owner-art fallback from looking like a frozen sticker inside a moving field.
- Reduced-motion removes autonomous owner-art motion while preserving a tiny explicit attention offset.
- The future authored Rive artboard remains responsible for its internal articulated animation and must consume the same `VanVisualState` contract rather than creating a second state model.

Whole-character motion is deliberately small. VAN remains the stable visual anchor while the field carries most semantic energy.

## 6. Live visual-state arbiter

`VanLiveVisualState` is the Android runtime bridge between real activity and visual state. It is Compose snapshot state. `FloatingOverlayService` reads it during composition, so live state changes recompose the full floating shell without polling.

It provides:

- state priority so weak cosmetic changes cannot immediately erase a stronger state;
- short minimum readable holds to prevent flicker;
- a 420 ms idle settle so LISTENING/SPEAKING do not snap to IDLE between callbacks;
- direct attention X/Y inputs for future pointer/vision/voice-direction gaze control;
- finite action code support;
- speech frame updates for mouth opening and visemes.

`VanPresence` remains a pure fail-closed mapper because the JVM visual-preview module compiles the same source. `FloatingOverlayService` explicitly supplies the live state to it. OFFLINE/DEGRADED subsystem truth always overrides optimistic live activity. When system truth is nominal, live state drives character, aura, caption, glass style and semantic accent together.

## 7. Voice and command lifecycle wiring

`VanApplication` forwards actual voice callbacks into the live visual state:

```text
recognizer ready/partial  -> LISTENING
final transcript          -> THINKING
TTS start/frame           -> SPEAKING + mouth/viseme
TTS completion            -> eased IDLE
recognizer failure        -> transient WARNING, then eased IDLE
```

`VanGatewayClient.dispatchCommand()` also publishes truthful local lifecycle cues:

```text
starting hand-off          -> DELEGATING
approval_required          -> WAITING_FOR_OWNER
accepted / in_flight       -> brief DELEGATING acknowledgement, then ambient
protocol reject/conflict   -> transient WARNING
transport exception        -> transient WARNING
backend degraded           -> DEGRADED
```

`accepted` is intentionally **not** mapped to SUCCESS. The gateway response only proves that Hermes accepted the run. A future run-status stream must own long-running WORKING/SUCCESS completion states.

## 8. Power, thermal and accessibility behaviour

The field obeys `VanEffectBudget` rather than running a second independent performance policy:

- `FULL`: complete field motion and particles.
- `REDUCED`: fewer filaments and a slightly smaller field.
- `LOW`: tighter field, fewer effects, motion retained.
- `REDUCED_MOTION`: designed still field; semantic state remains readable.
- `STATIC`: severe thermal floor; field freezes but does not disappear.

`budget.bloomScale` now affects the actual field footprint. State meaning and critical semantic colour are never removed to save effects.

## 9. Acceptance requirements

The implementation is acceptable only when all of the following hold:

1. No full or implied concentric aura ring is visible in a frozen frame.
2. Zone B/C strands are visibly detached from VAN and are clipped away from the body-safe ellipse.
3. Phase 0 and phase 1 produce the same motion frame, so infinite animation has no restart jump.
4. WORKING has greater wind strength, turbulence and wave amplitude than IDLE.
5. LOW/STATIC reduce footprint/effects before removing semantic information.
6. Reduced motion freezes autonomous motion while retaining a composed readable field.
7. Broken gateway/Hermes truth still forces OFFLINE regardless of optimistic live activity.
8. Live voice events cause visible LISTENING/THINKING/SPEAKING transitions without overlay polling.
9. Owner bitmap poses remain subtly alive without competing with aura motion.
10. Gateway acceptance never falsely displays SUCCESS.
11. The field remains compact enough for the floating overlay and must not expand into the large cinematic poster-scale aura.

## 10. Files

Runtime implementation:

- `android/app/src/main/java/com/dial/van/visual/VanWindFieldMotion.kt`
- `android/app/src/main/java/com/dial/van/visual/VanAura.kt`
- `android/app/src/main/java/com/dial/van/visual/VanCharacterMotion.kt`
- `android/app/src/main/java/com/dial/van/visual/VanLiveVisualState.kt`
- `android/app/src/main/java/com/dial/van/visual/VanPresence.kt`
- `android/app/src/main/java/com/dial/van/visual/VanCanvasFallback.kt`
- `android/app/src/main/java/com/dial/van/visual/VanLivingFieldPreviews.kt`
- `android/app/src/main/java/com/dial/van/overlay/FloatingOverlayService.kt`
- `android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt`
- `android/app/src/main/java/com/dial/van/VanApplication.kt`

Tests:

- `android/app/src/test/java/com/dial/van/visual/VanWindFieldMotionTest.kt`
- `android/app/src/test/java/com/dial/van/visual/VanCharacterMotionTest.kt`
- `android/app/src/test/java/com/dial/van/visual/VanPresenceTest.kt`

## 11. Preview truth

`VanLivingFieldPreviews.kt` provides Android Studio previews of the actual shipping Compose aura renderer for IDLE, WORKING, WARNING and REDUCED_MOTION.

The existing JVM `visual-preview` Java2D aura painter is a separate certification surface and still uses the older Rev 2.2 geometry. It must not be cited as pixel evidence for this new runtime field until that painter is migrated to the same directional-flow algorithm. This limitation is explicit rather than silently claiming the old sheets represent the new runtime.

## 12. Renderer truth

The authored `van.riv` remains external unless repository evidence changes that status. The renderer selection remains fail-closed: valid Rive artboard -> complete owner art -> procedural Canvas fallback. This revision does not claim Rive READY.

The live windy field itself is drawn by Compose behind whichever character renderer is selected, so the field does not depend on the authored Rive asset being present. Character-level motion is richest in the Canvas rig today; owner art now has bounded micro-motion; the future Rive artboard should implement the same durable-state, attention, speech and finite-action contract.
