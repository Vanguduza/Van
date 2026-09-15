# VAN Visual Acceptance Matrix

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
| Motion | Bounded — not frantic |
| Glow | Restrained — not excessive |
| Warning/Urgent | Distinct without false calm or panic |
| Offline/Degraded | Truthful muted presentation |
| Rive failure | Canvas fallback still canonical Van |

## Glassmorphic shell criteria

From `docs/VAN_GLASSMORPHIC_FLOATING_ASSISTANT_DESIGN.md` §16. Every row is enforced in code
by `VanGlassTokens`, `VanAuraSpecs` or `VanEffectPolicy`, not by hand-tuning a screenshot.

| Check | Pass criteria | Enforced by |
|---|---|---|
| Character never glassy | Glass applies to the shell only; Van stays opaque | `VanGlassStyle` describes the shell alone |
| Van breaks the glass edge | Character is not trapped in a rectangular card (§4) | Compact/expanded shell composition |
| Aura layering | Aura sits between Van and the glass, never over his face (§2) | `VanAuraSpecs` + draw order |
| Glass opacity envelope | 55–72% compact; Command Centre panels more opaque (§3, §14) | `VanGlassTokens.forState(panel = …)` |
| Approval legibility | Approval/warning glass becomes solid enough to prevent mis-taps (§6) | `requiresSolidControls` |
| No colour-only state | Every state carries accent *and* words *and* a silhouette cue (§16) | `VanCaptions` + ring styles |
| Reduced motion | Still, complete pose — phase-independent output (§12) | `reducedMotion` in `VanSceneFrame` |
| Battery / thermal | Fixed fallback ladder; a static cyan rim always survives (§11) | `VanEffectBudget` |
| Blur fallback | Live blur off keeps borders, radii, depth, glow and geometry (§10) | `liveBlurAvailable` pre-tint |

## Evidence

Preview sheets are rendered from the shipping draw program and design tokens by
`./gradlew :visual-preview:renderVanPreviews`, and land in `artifacts/release/preview/`:

| Sheet | Shows |
|---|---|
| `van_floating_overlay_preview.png` | Compact, expanded, approval and docked shells |
| `van_state_matrix.png` | All durable states with aura, arc and glass values |
| `van_state_matrix_reduced_motion.png` | The same matrix with motion disabled |
| `van_command_centre.png` | §14 panel composition and solid critical controls |
| `van_glass_tokens.png` | §8 tokens, §12 noisy-backdrop glass, §11 fallback ladder |

`VanPreviewRenderTest` measures the distinctness and dimming requirements on real pixels, so
"offline, degraded and urgent are distinct" is evidence rather than a claim.

## Outstanding

Owner acceptance required for final visual lock on device.

The authored `van.riv` artboard is EXTERNAL and undelivered; Rive must not be reported as
`READY` anywhere until a real artboard loads and binds on device.
