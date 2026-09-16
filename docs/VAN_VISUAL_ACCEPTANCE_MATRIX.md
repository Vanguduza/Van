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
| Orthogonal renderer parity | Compose and Java2D can render activity Zone A/B with independent semantic Zone C | `semanticSpec` in both render paths |
| Reduced motion | Autonomous field geometry freezes while state remains readable | `VanEffectBudget.REDUCED_MOTION` |
| Power / thermal | Effects reduce before semantic truth is removed | `VanEffectBudget` |

## Presence/state criteria

| Check | Pass criteria | Enforced by |
|---|---|---|
| Orthogonal truth | Activity, health, authority, speech, attention and owner-turn phase do not overwrite one another | `VanPresenceFrame` |
| Google-unverified + listening | Character and primary compact/expanded copy remain LISTENING while Zone C + secondary health line remain DEGRADED | `VanPresence` + `VanOverlayChrome` + tests |
| Uplink loss | Gateway/Hermes loss forces OFFLINE pose, semantic field and primary chrome | `VanPresence` + `VanOverlayChrome` |
| Thinking latch | Microphone end cannot erase THINKING before dispatch/result | `VanPresenceReducer` |
| Speech articulation | TTS temporarily shows SPEAKING without overwriting underlying THINKING/DELEGATING/WORKING activity | `VanPresenceReducer` + tests |
| Critical authority | TTS frames cannot replace WAITING_FOR_OWNER / ERROR / URGENT | `VanPresenceReducer` |
| Cross-surface coherence | Floating overlay and Command Centre consume the same live presence and subsystem-health sources | `VanLiveVisualState` + `DegradedModeStore.state` |
| Accepted ≠ success | Gateway acceptance may show hand-off/working but never SUCCESS | `VanGatewayClient` |

## Glassmorphic shell criteria

| Check | Pass criteria | Enforced by |
|---|---|---|
| Character never glassy | Glass applies to the shell only; Van stays opaque | `VanGlassStyle` |
| Van breaks the glass edge | Character is not trapped in a rectangular card | overlay composition |
| Activity-first chrome | Compact/expanded headline, caption, accent and glass state follow active pose unless OFFLINE/critical authority takes over | `VanOverlayChrome` |
| Health remains visible | Non-uplink degradation appears as secondary health copy and Zone C, not by relabelling active Van as broken | `VanPresence.healthCue` + `semanticState` |
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

Preview sheets are generated from the same renderer-neutral Zone B/C geometry used by Compose and uploaded as the `van-visual-evidence` workflow artifact. The canonical named evidence directory is `artifacts/release/preview/rev23/`; `rev21/` is no longer produced by the Rev 2.3 generator.

The evidence set includes the floating overlay, durable-state matrices, reduced/low/static budgets, command centre, glass tokens, aura topology, and `van_orthogonal_presence.png`. The orthogonal board must show:

- LISTENING + DEGRADED;
- THINKING + DEGRADED;
- SPEAKING + DEGRADED;
- WORKING + DEGRADED;
- LISTENING + OFFLINE → OFFLINE takeover;
- SPEAKING + WAITING_FOR_OWNER → owner-authority takeover.

## Final external gates

Owner acceptance on a physical Android device remains required for final visual lock. The authored `van.riv` artboard remains EXTERNAL/undelivered and must not be reported READY until a real artboard loads, binds and is certified on device.
