# VAN Visual & Owner-UX Acceptance Matrix — Rev 3.0

Canonical implementation authority: `docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md`.

## Current owner status

**NOT ACCEPTED — corrective implementation in progress.**

The first physical Samsung verification exposed defects that preview-only evidence did not reveal: VAN's body appeared glassified/over-transparent, the aura still read too close to the body and lacked sufficient living electrical motion, the workboard interaction model was incomplete, the Command Centre was mainly presentational, and VAN could appear static after the board opened. This device evidence supersedes the prior automated/previews-only merge-bar language for final visual/UX acceptance.

Only the owner may change this status to accepted after another physical-device verification.

## Identity / character criteria

| Check | Pass criteria |
|---|---|
| Hair | Silver/white swept — never dark |
| Visor | Cyan/blue transparent optic; transparency must not leak into face/body |
| Skin | Medium-brown and optically solid |
| Eyes | Blue |
| Jacket | Black/white technical and optically solid |
| Proportions | Compact-friendly stylized VAN identity |
| Orb | Present where composition supports it |
| Compact readability | Recognizable at floating size |
| Minimized identity | Circular portrait clearly reads as VAN's face |
| Launcher identity | App launcher icon clearly reads as VAN's face |
| Character opacity | Hair, skin, eyes and clothing remain effectively opaque in every durable state |
| Character motion | Smooth continuous hover/breath/gaze/blink/state motion while visible |
| Board independence | Opening/expanding/maximizing workboard never freezes or replaces character activity |

## Living electrical field criteria

| Check | Pass criteria | Enforced by |
|---|---|---|
| No halo reconstruction | Frozen frame cannot be read as a complete/broken concentric ring | `VanFieldGeometryEngine` |
| Silhouette detachment | Main Zone B/C/electrical samples remain outside inflated head/torso/shoulder exclusion | `VanBodyExclusionProfile` + tests |
| Visible air gap | Floating build shows a clear gap between body and primary field | Rev 3 geometry + device check |
| Identity ownership | Zone A/B identity energy remains cyan | `VanAuraSpecs` + ink ownership |
| Semantic ownership | warning/error/success/degraded colour lives in Zone C | `semanticState` |
| State topology | waiting/warning/error/urgent/success differ geometrically, not only by colour | semantic topology |
| Continuous field | Wind/waves/curl/advection are procedural and continue while board is open | `VanWindFieldMotion` |
| Wavy field | At least one active stream carries visible low-frequency S-curve deformation | `VanFieldGeometryEngine` |
| Electrical life | Short-lived bright-core branches appear/propagate/fork/fade without tracing VAN | `VanElectricalBranch` |
| Particle life | Ion fragments advect and fade rather than remain static points | geometry engine |
| Residual field with board | Workboard never replaces the aura; field remains visibly alive around VAN/panel | overlay composition |
| Reduced motion | Autonomous geometry reduces/freezes while essential state remains readable | `VanEffectBudget.REDUCED_MOTION` |
| Power / thermal | Expensive effects reduce before core character/state truth is removed | `VanEffectBudget` |

## Presence/state criteria

| Check | Pass criteria | Enforced by |
|---|---|---|
| Orthogonal truth | activity, health, authority, speech, attention and owner-turn phase remain independent | `VanPresenceFrame` |
| Non-uplink degradation | active local pose remains truthful while health stays secondary | `VanPresence` |
| Uplink loss | gateway/Hermes loss fails closed to OFFLINE | `VanPresence` |
| Thinking latch | microphone end cannot erase THINKING before dispatch/result | reducer tests |
| Speech articulation | TTS temporarily shows SPEAKING without erasing underlying work | reducer tests |
| Critical authority | speech cannot replace WAITING_FOR_OWNER / ERROR / URGENT | reducer tests |
| Accepted ≠ success | ACCEPTED/IN_FLIGHT are not displayed as completion | gateway/controller |
| Board independence | overlay presentation cannot mutate `VanPresenceFrame` | `VanOverlayReducer` |

## Floating UX criteria

| Check | Pass criteria |
|---|---|
| Single tap closed | opens compact workboard |
| Single tap open | closes any workboard back to full floating VAN |
| Double tap | opens Command Centre without firing a board toggle first |
| Long press | exposes Chat, Voice, Minimize, Command Centre, Dock and Close controls |
| Minimize | smoothly becomes circular live VAN-face portrait |
| Minimized tap | restores full floating VAN |
| Minimized double tap | opens Command Centre |
| Drag | only VAN/drag handle moves overlay; board scrolling never moves window |
| Dismiss | dragging VAN reveals bottom-centre X; releasing in target stops overlay |
| Board scroll | expanded/maximized content scrolls independently |
| Board expand | explicit compact → expanded → maximized controls work |
| Board input | typed input can receive IME focus and dispatch |

## Glass criteria

| Check | Pass criteria |
|---|---|
| Character never glassy | glass applies only to UI/aura optical layers |
| Baby-cyan material | board is baby-blue/cyan optical glass rather than near-invisible dark HUD |
| Readability | busy backgrounds retain enough absorber to keep controls/text legible |
| VAN breaks edge | character remains a separate solid layer overlapping/adjacent to glass |
| Approval legibility | elevated controls are sufficiently opaque and unambiguous |
| No uniform neon perimeter | specular/structural edges remain selective |

## Owner-control criteria

| Check | Pass criteria |
|---|---|
| Typed chat | real owner command dispatches through `VanCommandController` → signed gateway |
| Voice | final transcript enters the same command controller as typed chat |
| Transcript visibility | live/partial/final voice state is available to work surfaces |
| Command Centre | real navigation between Home/Chat/Decisions/Tasks/Projects/Activity/Systems/Connections/Settings |
| Decisions | gateway decisions load and approve/reject actions call the real endpoint |
| Projects | project list comes from gateway registry; no Android hard-coded production list |
| Tasks | module shows truthful local queue/dispatch lifecycle; no fabricated progress |
| Systems | live gateway/Hermes/mesh truth is readable |
| Activity | enrolled device can read gateway event replay |
| Security | Android UI never bypasses gateway into direct shell/SSH |
| A4 | privileged actions remain fail-closed and biometric-gated |

## Automated gates

The canonical CI must pass:

```text
:app:testDebugUnitTest
:app:assembleDebug
:app:lintDebug
:visual-preview:test
:visual-preview:renderVanPreviews
```

Rev 3 evidence should move to `artifacts/release/preview/rev30/` and include multi-frame motion/electrical evidence rather than relying only on still sheets.

## Physical Samsung re-verification checklist

- [ ] Character solid/opaque over light background
- [ ] Character solid/opaque over dark background
- [ ] Character solid/opaque over busy/photo background
- [ ] Aura visibly detached from VAN
- [ ] Aura visibly wavy and continuously advecting for 30+ seconds
- [ ] Electrical life visible without strobing
- [ ] Baby-cyan workboard glass readable
- [ ] Single tap opens board
- [ ] Single tap on VAN closes board
- [ ] Double tap opens Command Centre
- [ ] Board scrolls without moving VAN
- [ ] Board expands/maximizes/collapses
- [ ] Long-press controls all execute
- [ ] Minimize produces circular VAN-face icon
- [ ] Minimized tap restores VAN
- [ ] Launcher icon clearly shows VAN's face
- [ ] Drag shows bottom dismiss X and drop closes VAN
- [ ] VAN remains smoothly animated while board is open
- [ ] LISTENING → THINKING → WORKING visibly transitions
- [ ] Typed chat dispatches a harmless real owner command
- [ ] Voice displays transcript and uses the same command lifecycle
- [ ] Decisions/Tasks/Projects/Systems are interactive and truthful

## External gates

The authored `van.riv` artboard remains EXTERNAL/not READY until a real artboard loads, binds and is certified on-device. Production signing/keystore remains a separate release gate. Neither may be falsely claimed complete by visual preview CI.
