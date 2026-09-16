# VAN Visual Acceptance Matrix — Rev 2.3

Canonical authority: `visual-authority/van-visual-authority-v2.yaml` revision 2.3.

| Check | Pass criteria |
|---|---|
| Hair | Silver/white swept — not dark |
| Visor | Cyan/blue transparent geometry |
| Skin | Medium-brown |
| Eyes | Blue |
| Jacket | Black/white technical |
| Proportions | Compact friendly stylized |
| Orb | Present where required |
| Compact readability | Recognizable at overlay size |
| Motion | Bounded, continuous and lifelike — not frantic |
| Glow | Restrained — not excessive |
| Warning/Urgent | Distinct in geometry, wording and semantic colour |
| Offline/Degraded | Truthful without suppressing locally valid activity |
| Rive failure | Owner-art/Canvas fallback still canonical Van |

## Living-field criteria

| Check | Pass criteria | Enforced by |
|---|---|---|
| No halo reconstruction | Frozen frame cannot be read as a complete or broken concentric ring | `VanFieldGeometryEngine` |
| Body detachment | Zone B/C samples remain outside the body-safe exclusion geometry | `VanFieldGeometryEngine` + tests |
| Identity ownership | Zone A/B identity energy remains cyan | `VanAuraSpecs` + renderer ink ownership |
| Semantic ownership | Warning/error/success/degraded colour lives in Zone C | `VanAuraSpecs` + `semanticState` |
| State topology | Waiting/warning/error/urgent/success differ geometrically, not only by colour | authored envelope segments + shared geometry engine |
| Continuous field | Wind/waves/curl/particles are procedural and phase-seamless | `VanWindFieldMotion` |
| Renderer parity | Compose runtime and Java2D evidence consume the same Zone B/C geometry | `VanFieldGeometryEngine` |
| Reduced motion | Autonomous field geometry freezes while state remains readable | `VanEffectBudget.REDUCED_MOTION` |
| Power / thermal | Effects reduce before semantic truth is removed | `VanEffectBudget` |

## Presence/state criteria

| Check | Pass criteria | Enforced by |
|---|---|---|
| Orthogonal truth | Activity, health, authority, speech, attention and owner-turn phase do not overwrite one another | `VanPresenceFrame` |
| Google-unverified + listening | Character can visibly LISTEN while chrome/Zone C remain DEGRADED | `VanPresence` + `VanPresenceTest` |
| Uplink loss | Gateway/Hermes loss forces OFFLINE | `VanPresence` |
| Thinking latch | Microphone end cannot erase THINKING before dispatch/result | `VanPresenceReducer` |
| Critical authority | TTS frames cannot replace WAITING_FOR_OWNER / ERROR / URGENT | `VanPresenceReducer` |
| Cross-surface coherence | Floating overlay and Command Centre consume the same live presence and subsystem-health sources | `VanLiveVisualState` + `DegradedModeStore.state` |
| Accepted ≠ success | Gateway acceptance may show hand-off/working but never SUCCESS | `VanGatewayClient` |

## Glassmorphic shell criteria

| Check | Pass criteria | Enforced by |
|---|---|---|
| Character never glassy | Glass applies to the shell only; Van stays opaque | `VanGlassStyle` |
| Van breaks the glass edge | Character is not trapped in a rectangular card | overlay composition |
| Aura layering | Field sits behind Van and in front of condensed glass, never over his face | draw order |
| Glass opacity envelope | Compact glass remains restrained; Command Centre panels are more opaque | `VanGlassTokens.forState(panel = …)` |
| Approval legibility | Critical controls become solid enough to prevent mis-taps | `requiresSolidControls` |
| No colour-only state | Critical states also carry text and geometry/topology cues | captions + field topology |
| Blur fallback | Live blur off preserves borders, depth and semantic readability | `liveBlurAvailable` handling |

## Automated evidence

`.github/workflows/van-ci.yml` must pass:

```text
:app:testDebugUnitTest
:app:assembleDebug
:app:lintDebug
:visual-preview:test
:visual-preview:renderVanPreviews
```

Preview sheets are generated from the same renderer-neutral Zone B/C geometry used by Compose and uploaded as the `van-visual-evidence` workflow artifact. The evidence set includes the floating overlay, durable-state matrices, reduced/low/static budgets, command centre, glass tokens and aura topology sheets.

## Final external gates

Owner acceptance on a physical Android device remains required for final visual lock. The authored `van.riv` artboard remains EXTERNAL/undelivered and must not be reported READY until a real artboard loads, binds and is certified on device.
