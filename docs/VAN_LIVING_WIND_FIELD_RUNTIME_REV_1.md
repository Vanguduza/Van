# VAN Living Wind Field Runtime — Rev 1.2

Status: implementation companion to canonical visual authority Rev 2.3  
Baseline: `a6756df`  
Scope: floating overlay, Command Centre, owner-art/Canvas/Rive-compatible inputs, shared field geometry, reduced-motion and power fallbacks

## 1. Purpose

Rev 2.2 established correct three-zone semantic ownership but still allowed broken orbital geometry to read as a halo. Rev 2.3 replaces that with a compact, continuously animated windy electrical field and removes a second architectural flaw exposed during review: activity, health, owner-decision authority and speech can be true at the same time and therefore must not compete for one enum.

“Lifelike” and “attention-aware” describe animation behaviour only. They do not claim that VAN is conscious.

## 2. Canonical state model

Runtime truth is represented by `VanPresenceFrame` with orthogonal channels:

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

The character and primary interaction copy therefore remain LISTENING while Zone C and the secondary health line communicate DEGRADED truth. Uplink OFFLINE remains stronger and takes over pose, semantic field and primary chrome. `VanVisualState.semanticState` carries outer-field truth separately from `durableState`, which continues to drive the character/Rive pose contract.

## 3. Observable subsystem truth

`DegradedMode` remains a pure renderer-neutral data model. Android observation lives in a separate `DegradedModeStore`, backed by `StateFlow<DegradedMode>`.

The floating overlay and Command Centre both collect the same health stream and both read the same application-scoped `VanLiveVisualState.frame`. A gateway/Google health update therefore recomposes both surfaces immediately; neither relies on a coincidental voice animation or a one-time snapshot to discover changed subsystem truth.

`VanPresence.healthCue()` exposes subsystem truth separately from activity copy. The overlay uses `VanOverlayChrome` so non-uplink degradation remains visible without relabelling a functioning LISTENING/THINKING/SPEAKING/WORKING Van as “Degraded.” OFFLINE and critical owner-authority states are allowed to take over the primary chrome.

## 4. Owner-turn lifecycle

Speech capture ending is not owner-turn completion.

```text
microphone ready/partial -> CAPTURING / LISTENING
capture end               -> microphone quiet only
final transcript          -> THINKING
command dispatch begins   -> DISPATCHING / DELEGATING
accepted/in_flight        -> brief WORKING acknowledgement, then ambient
approval_required         -> WAITING_FOR_OWNER
```

Callback ordering can therefore vary without erasing THINKING.

TTS is an articulation channel, not an activity transition. `speechStarted()` / `speechFrame()` temporarily give the pose SPEAKING precedence but do not mutate the underlying activity. When TTS ends, the previous THINKING, DELEGATING or WORKING activity automatically reappears. Speech also cannot hide WAITING_FOR_OWNER, ERROR or URGENT authority.

## 5. Three-zone field

- **Zone A — identity presence:** restrained cyan bloom and shallow ground crescent.
- **Zone B — interaction field:** detached windy ribbons, ion fragments and orb-link energy driven by local activity.
- **Zone C — semantic envelope:** sparse, detached, state-specific directional flow driven independently by health/authority semantic truth.

Full rings and concentric orbit geometry are forbidden. Zone B/C paths are clipped away from a body-safe ellipse.

## 6. Shared renderer-neutral geometry

`VanFieldGeometryEngine` is the canonical Zone B/C geometry source. It has no Compose, Android or AWT dependency and accepts independent activity and semantic specs:

```text
activity VanAuraSpec + semantic VanAuraSpec + phase + VanEffectBudget + body bounds
```

Both renderers consume it with the same composition contract:

- shipping Compose: `VanAura.kt`;
- JVM evidence renderer: `GlassPainter.kt`.

This removes the previous dual-painter drift and allows evidence for the exact orthogonal combinations introduced by Rev 2.3, not only single-state boards.

## 7. Wind motion

`VanWindFieldMotion` produces a deterministic, phase-seamless motion frame. Each ribbon combines multiple temporal harmonics:

```text
w(u,t) = A · [ sin(2π(2u − 2t + s))
             + 0.38 sin(2π(3u + 3t + 1.71s))
             + 0.14 sin(2π(5u − t + 0.47s)) ]
```

The field frame also supplies bounded breathing, prevailing wind, meander, turbulence, pulse energy, particle advection and budget-driven field scale.

## 8. State-specific semantic topology

Zone C does not map every state onto the same wind axis. Each authored envelope segment rotates and shapes a local flow direction from its `startDeg`, `sweepDeg` and `node` properties. This preserves topology distinction in geometry as well as colour.

Expected readings include:

| State | Geometry intent |
| --- | --- |
| LISTENING | inward-attentive cyan Zone B flow |
| SEARCHING | probing lateral streams |
| WORKING | higher-throughput directional transport |
| WAITING_FOR_OWNER | amber converging/bracketing Zone C flow |
| WARNING | interrupted amber disturbance |
| ERROR | fractured/diverging red flow |
| URGENT | compressed directional red flow |
| SUCCESS | green release/expansion flow |

## 9. Character motion

The procedural Canvas rig retains body/head bob, blink, gaze, orb drift, speech articulation and finite actions. Owner bitmap poses receive bounded `VanCharacterMotion` micro-motion. Reduced-motion freezes autonomous motion. The authored Rive asset remains external/not READY unless repository evidence changes that status.

## 10. Truth composition

`VanPresence` is a pure resolver and remains fail-closed:

- gateway/Hermes uplink loss -> OFFLINE pose, semantic state and primary chrome;
- non-uplink degraded truth -> Zone C + secondary health copy while local activity remains primary;
- owner-decision/error authority -> authority semantic/pose/primary chrome state;
- speech -> temporary articulation/pose precedence while underlying activity is preserved.

The floating overlay and Command Centre consume the same application-scoped presence and subsystem-health sources, preventing surface-local state forks.

## 11. Performance and accessibility

`VanEffectBudget` remains authoritative:

- `FULL`: full field motion and particles;
- `REDUCED`: fewer filaments, smaller field;
- `LOW`: tighter field and fewer effects;
- `REDUCED_MOTION`: designed still field, semantics preserved;
- `STATIC`: thermal floor, still readable field.

Critical semantic information is preserved before decorative effects.

## 12. Acceptance requirements

The implementation is mergeable only when all are true:

1. no full or implied concentric ring is visible in a frozen frame;
2. Zone B/C remain detached from the body-safe region;
3. semantic states have distinct geometry, not only distinct colour;
4. phase wrapping is seamless;
5. Google-unverified + LISTENING renders a LISTENING pose and primary copy with DEGRADED Zone C + secondary health line;
6. microphone-end ordering cannot erase THINKING;
7. TTS round-trips restore underlying THINKING/DELEGATING/WORKING activity;
8. TTS speech frames cannot replace WAITING_FOR_OWNER/ERROR/URGENT authority;
9. OFFLINE uplink truth forces OFFLINE pose/semantics/primary chrome;
10. Compose and Java2D evidence both compose independent activity and semantic specs through `VanFieldGeometryEngine`;
11. reduced-motion produces stable geometry;
12. gateway `accepted` never displays SUCCESS;
13. overlay and Command Centre react to health changes from `DegradedModeStore.state`;
14. Android and visual-evidence Gradle gates pass;
15. generated Rev 2.3 evidence includes the orthogonal presence board and is manually inspected before merge.

## 13. CI / evidence gates

`.github/workflows/van-ci.yml` runs on pull requests and `main`, with obsolete runs cancelled by concurrency control. `tools/ci/github-actions-ci.yml` is kept aligned with the live workflow and `tools/ci/install_github_workflow.py` installs only `.github/workflows/van-ci.yml`.

```text
pytest backend
pytest tests/contracts
:app:testDebugUnitTest
:app:assembleDebug
:app:lintDebug
:visual-preview:test
:visual-preview:renderVanPreviews
```

Generated preview evidence is uploaded as the `van-visual-evidence` workflow artifact. Canonical named evidence is written under `artifacts/release/preview/rev23/`; the Rev 2.3 generator no longer writes a `rev21/` directory.

The top-level `van_orthogonal_presence.png` and `rev23/orthogonal-presence.png` board certify:

```text
LISTENING + DEGRADED
THINKING  + DEGRADED
SPEAKING  + DEGRADED
WORKING   + DEGRADED
LISTENING + OFFLINE          -> OFFLINE takeover
SPEAKING  + WAITING_FOR_OWNER -> authority takeover
```

PR promotion must use the generated results, not descriptive claims.

## 14. Key files

- `visual-authority/van-visual-authority-v2.yaml` — canonical Rev 2.3 authority
- `android/app/src/main/java/com/dial/van/degraded/DegradedMode.kt`
- `android/app/src/main/java/com/dial/van/degraded/DegradedModeStore.kt`
- `android/app/src/main/java/com/dial/van/visual/VanPresenceFrame.kt`
- `android/app/src/main/java/com/dial/van/visual/VanLiveVisualState.kt`
- `android/app/src/main/java/com/dial/van/visual/VanPresence.kt`
- `android/app/src/main/java/com/dial/van/visual/VanWindFieldMotion.kt`
- `android/app/src/main/java/com/dial/van/visual/VanFieldGeometry.kt`
- `android/app/src/main/java/com/dial/van/visual/VanAura.kt`
- `android/app/src/main/java/com/dial/van/overlay/VanOverlayChrome.kt`
- `android/app/src/main/java/com/dial/van/overlay/FloatingOverlayService.kt`
- `android/visual-preview/src/main/kotlin/com/dial/van/preview/GlassPainter.kt`
- `android/visual-preview/src/main/kotlin/com/dial/van/preview/VanEvidenceMatrix.kt`
- `android/app/src/main/java/com/dial/van/VanApplication.kt`
- `android/app/src/main/java/com/dial/van/gateway/VanGatewayClient.kt`
- `android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt`

## 15. Renderer truth

The authored `van.riv` remains external/not READY. Renderer selection stays fail-closed: usable Rive artboard -> complete owner art -> procedural Canvas fallback. The living field is rendered independently behind whichever character renderer is active.
