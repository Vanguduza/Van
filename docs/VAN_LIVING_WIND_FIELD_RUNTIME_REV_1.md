# VAN Living Wind Field Runtime — Rev 1.1

Status: implementation companion to canonical visual authority Rev 2.3  
Baseline: `a6756df`  
Scope: floating overlay, Command Centre, owner-art/Canvas/Rive-compatible inputs, shared field geometry, reduced-motion and power fallbacks

## 1. Purpose

Rev 2.2 established correct three-zone semantic ownership but still allowed broken orbital geometry to read as a halo. Rev 2.3 replaces that with a compact, continuously animated windy electrical field and removes a second architectural flaw exposed during review: activity, health, owner-decision authority and speech can be true at the same time and therefore must not compete for one enum.

“Lifelike” and “attention-aware” describe animation behaviour only. They do not claim that VAN is conscious.

## 2. Canonical state model

Runtime truth is now represented by `VanPresenceFrame` with orthogonal channels:

- `activity`: IDLE, THINKING, SEARCHING, WORKING, DELEGATING, etc.;
- `health`: NOMINAL, DEGRADED, OFFLINE;
- `authority`: NONE, WAITING_FOR_OWNER, WARNING, ERROR, URGENT;
- `speech`: QUIET, LISTENING, SPEAKING;
- `turn`: IDLE, CAPTURING, THINKING, DISPATCHING;
- attention, mouth/viseme, urgency and finite action data.

This permits truthful combinations such as:

```text
activity = LISTENING
health   = DEGRADED     # Google mesh not yet verified
```

The character therefore listens while Zone C/chrome still shows degraded truth. Uplink OFFLINE remains stronger and forces an offline pose. `VanVisualState.semanticState` carries outer-field truth separately from `durableState`, which continues to drive the character/Rive pose contract.

## 3. Owner-turn lifecycle

Speech capture ending is no longer treated as owner-turn completion.

```text
microphone ready/partial -> CAPTURING / LISTENING
capture end               -> microphone quiet only
final transcript          -> THINKING
command dispatch begins   -> DISPATCHING / DELEGATING
accepted/in_flight        -> brief WORKING acknowledgement, then ambient
approval_required         -> WAITING_FOR_OWNER
```

Callback ordering can therefore vary without erasing THINKING. `speechFrame()` updates articulation but does not replace health or authority truth, so TTS cannot hide WAITING_FOR_OWNER, ERROR or URGENT.

## 4. Three-zone field

- **Zone A — identity presence:** restrained cyan bloom and shallow ground crescent.
- **Zone B — interaction field:** detached windy ribbons, ion fragments and orb-link energy.
- **Zone C — semantic envelope:** sparse, detached, state-specific directional flow carrying semantic colour.

Full rings and concentric orbit geometry are forbidden. Zone B/C paths are clipped away from a body-safe ellipse.

## 5. Shared renderer-neutral geometry

`VanFieldGeometryEngine` is the canonical Zone B/C geometry source. It has no Compose, Android or AWT dependency and outputs strokes/dots from:

```text
VanAuraSpec + phase + VanEffectBudget + body bounds
```

Both renderers consume it:

- shipping Compose: `VanAura.kt`;
- JVM evidence renderer: `GlassPainter.kt`.

This removes the previous dual-painter drift. Owner preview boards generated after Rev 2.3 now represent the same Zone B/C geometry that ships on device.

## 6. Wind motion

`VanWindFieldMotion` produces a deterministic, phase-seamless motion frame. Each ribbon combines multiple temporal harmonics:

```text
w(u,t) = A · [ sin(2π(2u − 2t + s))
             + 0.38 sin(2π(3u + 3t + 1.71s))
             + 0.14 sin(2π(5u − t + 0.47s)) ]
```

The field frame also supplies bounded breathing, prevailing wind, meander, turbulence, pulse energy, particle advection and budget-driven field scale.

## 7. State-specific semantic topology

Zone C no longer maps every state onto the same wind axis. Each authored envelope segment rotates and shapes a local flow direction from its `startDeg`, `sweepDeg` and `node` properties. This preserves topology distinction in geometry as well as colour.

Expected readings include:

| State | Geometry intent |
| --- | --- |
| LISTENING | inward-attentive cyan flow |
| SEARCHING | probing lateral streams |
| WORKING | higher-throughput directional transport |
| WAITING_FOR_OWNER | amber converging/bracketing flow |
| WARNING | interrupted amber disturbance |
| ERROR | fractured/diverging red flow |
| URGENT | compressed directional red flow |
| SUCCESS | green release/expansion flow |

## 8. Character motion

The procedural Canvas rig retains body/head bob, blink, gaze, orb drift, speech articulation and finite actions. Owner bitmap poses receive bounded `VanCharacterMotion` micro-motion. Reduced-motion freezes autonomous motion. The authored Rive asset remains external/not READY unless repository evidence changes that status.

## 9. Truth composition

`VanPresence` is a pure resolver and remains fail-closed:

- gateway/Hermes uplink loss -> OFFLINE pose and semantic state;
- non-uplink degraded truth -> semantic/chrome DEGRADED while local activity can remain visible;
- owner-decision/error authority -> authority semantic/pose state;
- speech remains an orthogonal articulation channel.

The floating overlay and Command Centre both observe the same application-scoped `VanLiveVisualState.frame`, preventing surface-local state forks.

## 10. Performance and accessibility

`VanEffectBudget` remains authoritative:

- `FULL`: full field motion and particles;
- `REDUCED`: fewer filaments, smaller field;
- `LOW`: tighter field and fewer effects;
- `REDUCED_MOTION`: designed still field, semantics preserved;
- `STATIC`: thermal floor, still readable field.

Critical semantic information is preserved before decorative effects.

## 11. Acceptance requirements

The implementation is mergeable only when all are true:

1. no full or implied concentric ring is visible in a frozen frame;
2. Zone B/C remain detached from the body-safe region;
3. semantic states have distinct geometry, not only distinct colour;
4. phase wrapping is seamless;
5. Google-unverified + LISTENING renders a LISTENING pose with DEGRADED semantic field/chrome;
6. microphone-end ordering cannot erase THINKING;
7. TTS speech frames cannot replace WAITING_FOR_OWNER/ERROR/URGENT authority;
8. OFFLINE uplink truth still forces OFFLINE;
9. Compose and Java2D evidence use `VanFieldGeometryEngine`;
10. reduced-motion produces stable geometry;
11. gateway `accepted` never displays SUCCESS;
12. Android and visual-evidence Gradle gates pass.

## 12. CI / evidence gates

`.github/workflows/van-ci.yml` runs:

```text
pytest backend
pytest tests/contracts
:app:testDebugUnitTest
:app:assembleDebug
:app:lintDebug
:visual-preview:test
:visual-preview:renderVanPreviews
```

Generated preview evidence is uploaded as the `van-visual-evidence` workflow artifact. PR promotion must use those results, not descriptive claims.

## 13. Key files

- `visual-authority/van-visual-authority-v2.yaml` — canonical Rev 2.3 authority
- `android/app/src/main/java/com/dial/van/visual/VanPresenceFrame.kt`
- `android/app/src/main/java/com/dial/van/visual/VanLiveVisualState.kt`
- `android/app/src/main/java/com/dial/van/visual/VanPresence.kt`
- `android/app/src/main/java/com/dial/van/visual/VanWindFieldMotion.kt`
- `android/app/src/main/java/com/dial/van/visual/VanFieldGeometry.kt`
- `android/app/src/main/java/com/dial/van/visual/VanAura.kt`
- `android/visual-preview/src/main/kotlin/com/dial/van/preview/GlassPainter.kt`
- `android/app/src/main/java/com/dial/van/VanApplication.kt`
- `android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt`
- `android/app/src/main/java/com/dial/van/overlay/FloatingOverlayService.kt`
- `android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt`

## 14. Renderer truth

The authored `van.riv` remains external/not READY. Renderer selection stays fail-closed: usable Rive artboard -> complete owner art -> procedural Canvas fallback. The living field is rendered independently behind whichever character renderer is active.
