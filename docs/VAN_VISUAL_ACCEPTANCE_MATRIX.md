# VAN Visual & Owner-UX Acceptance Matrix — Rev 3.0

Canonical implementation authority: `docs/VAN_PRODUCTION_VISUAL_FLOATING_UX_OWNER_ADMIN_REV_3_0.md`.

Aura authority: owner decisions CF-D-06, CF-D-06-REV1 and CF-D-08 (`docs/character_forge/MANIFEST.yaml`) and
`visual-authority/character-forge/aura/AURA_RUNTIME_CONTRACT.yaml`. The aura is a flame envelope wrapping VAN's
silhouette with embers; wind strands, electrical branches, ion specks, the orb link line and the detached-field
rule are removed. The aura criteria below follow that authority; the former living-electrical-field rows are retired.

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

## Flame aura criteria (CF-D-06 / CF-D-06-REV1 / CF-D-08)

| Check | Pass criteria | Enforced by |
|---|---|---|
| Flame envelope | The aura wraps VAN's silhouette and rises off it as layered flame tongues with a core rim and rising embers | `VanFlameAura` + `VanFlameAuraTest` |
| No line geometry | No wind strands, electrical branches, ion specks or orb link line are drawn in any state | `AURA_RUNTIME_CONTRACT.yaml` `line_geometry: forbidden` + `test_aura_runtime_contract.py` |
| Silhouette source | The envelope follows what is on screen: Rive alpha once the rig loads, Candidate B alpha today, measured layout for the Canvas fallback | `VanSilhouette` |
| Front depth | Front wisps stay faint and never rise over the face | contract `FRONT_ALPHA_MAX`, `FRONT_TOP_FRACTION` |
| Identity / state colour | Identity flame is cyan; THINKING cyan-violet and SLEEPING faint blue per the contract palette | `VanAuraSpec` + contract `state_palette` |
| Trade energy | Calm in a trade, turbulent under risk, highest on a stop; a closed position fires one white pulse | `VanTradeSemantic` + `VanTradeSemanticTest` |
| Continuous motion | Flame motion continues while the board is open and never visibly repeats (slow second clock) | `VanAnimationClock` + contract `motion` |
| Residual aura with board | Workboard never replaces the aura; the flame remains visibly alive around VAN/panel | overlay composition |
| Reduced motion | Autonomous motion freezes while essential state remains readable | `VanEffectBudget.REDUCED_MOTION` |
| Power / thermal | Expensive layers reduce before core character/state truth is removed | `VanEffectBudget` + contract `performance_tiers` |

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

Rev 3 evidence should move to `artifacts/release/preview/rev30/` and include multi-frame flame-motion evidence (CF-D-08 8-second motion clips) rather than relying only on still sheets.

## Physical Samsung re-verification checklist

- [ ] Character solid/opaque over light background
- [ ] Character solid/opaque over dark background
- [ ] Character solid/opaque over busy/photo background
- [ ] Flame aura wraps VAN's silhouette and rises off it (CF-D-06)
- [ ] No strands, lightning branches, specks or orb link line visible (CF-D-06-REV1)
- [ ] Flame motion continuous for 30+ seconds without visible repetition or strobing
- [ ] Front wisps never cover the face
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
