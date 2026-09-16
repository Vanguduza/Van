# VAN Visual Rev 2.1 — Implementation notes

Authority: `docs/VAN_VISUAL_PRODUCTION_SYSTEM_REV_2_1_MASTER_BLUEPRINT.md` and `docs/CURSOR_PROMPT_VAN_VISUAL_CORRECTIONS_REV_2_1.md`.

## Thesis shipped

VAN is a solid expressive character surrounded by a living refractive field. When interface space is needed, that field condenses into glass.

## What changed

| Area | Before | After |
|---|---|---|
| Aura | Radial ellipse + accent ring | Deformable field, filaments 2–5, broken arcs (max 110° / 220° total). Full ring forbidden. |
| Glass | Fill + uniform glow stroke | Tint, shaping gradient, grain, inner highlight, faint structural edge, selective specular, aura contamination |
| Overlay rest | Permanent compact capsule | `OverlayMode.RESTING` — frameless VAN + aura |
| Compact / expanded | Card beside VAN | Glass condenses under VAN with 20dp overlap |
| Dock | 5dp cyan bar | 88dp hit / 76dp character crescent edge slice |
| Command Centre | Generic placeholder cards | Hero → state/mission → attention → decisions → tasks → projects → connections → solid A4 |
| Reduced motion | Mapped to `STATIC` | `VanEffectBudget.REDUCED_MOTION` — designed stillness |
| Evidence | 12 states | All 18 durable states + 14 actions + LOW/STATIC boards |

## Files

- `android/app/src/main/java/com/dial/van/visual/VanAura.kt`
- `android/app/src/main/java/com/dial/van/visual/VanAuraSpec.kt`
- `android/app/src/main/java/com/dial/van/visual/VanGlassTokens.kt`
- `android/app/src/main/java/com/dial/van/visual/VanGlassSurface.kt`
- `android/app/src/main/java/com/dial/van/visual/VanEffectBudget.kt`
- `android/app/src/main/java/com/dial/van/overlay/OverlayStateStore.kt`
- `android/app/src/main/java/com/dial/van/overlay/OverlayTheme.kt`
- `android/app/src/main/java/com/dial/van/overlay/FloatingOverlayService.kt`
- `android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt`
- `android/visual-preview/src/main/kotlin/com/dial/van/preview/GlassPainter.kt`
- `android/visual-preview/src/main/kotlin/com/dial/van/preview/VanPreviewSheets.kt`
- `android/visual-preview/src/main/kotlin/com/dial/van/preview/VanPreviewMain.kt`

## Evidence

Written by `:visual-preview:renderVanPreviews` into `artifacts/release/preview/`:

- `van_floating_overlay_preview.png`
- `van_state_matrix.png`
- `van_state_matrix_reduced_motion.png`
- `van_state_matrix_low.png`
- `van_state_matrix_static.png`
- `van_action_board.png`
- `van_command_centre.png`
- `van_glass_tokens.png`

## Residual gaps (EXTERNAL)

- Authored `van.riv` artboard and owner visual sign-off
- Physical device / production keystore
- Finite-action *poses* still reuse identity-locked idle/success/warning art; action *codes* are complete
