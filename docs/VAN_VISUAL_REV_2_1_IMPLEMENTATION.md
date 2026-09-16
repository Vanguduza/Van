# VAN Visual Rev 2.1 — Implementation notes

Authority: `docs/VAN_VISUAL_PRODUCTION_SYSTEM_REV_2_1_MASTER_BLUEPRINT.md`, `docs/VAN_VISUAL_PRODUCTION_SYSTEM_REV_2_2_ADDENDUM_AURA_SEMANTIC_ENVELOPE.md`, and `docs/CURSOR_PATCH_PROMPT_VAN_AURA_SEMANTIC_ENVELOPE.md`. Token file: `visual-authority/van-visual-authority-v2.yaml` (revision 2.2).

## Thesis shipped

VAN is a solid expressive character surrounded by a three-zone field. Zone A is identity cyan on the body. Zone B is mid interaction. Zone C is the outer semantic envelope. When interface space is needed, the field condenses into glass.

## What changed

| Area | Before | After |
|---|---|---|
| Aura | Radial ellipse + accent ring | Offset-lobe field, filaments 2–5, broken arcs (max 110° / 220° total). Full ring forbidden. |
| Glass | Fill + uniform glow stroke | Tint, shaping gradient, grain, inner highlight, faint structural edge, selective specular, aura contamination |
| Overlay rest | Permanent compact capsule | `OverlayMode.RESTING` — frameless VAN + aura, 168dp hit / 92dp character so Zone C has air |
| Compact / expanded | Card beside VAN | 280dp glass condenses under VAN with 20dp overlap; Ask / Projects / Tasks / Decisions; no rail |
| Dock | 5dp cyan bar | 88dp hit / 76dp character crescent edge slice, face/visor on-screen |
| Command Centre | Generic placeholder cards | Hero → state/mission → attention → decisions → tasks → projects → connections → solid A4 |
| Reduced motion | Mapped to `STATIC` | `VanEffectBudget.REDUCED_MOTION` — designed stillness |
| Actions | Idle art reused for every code | 14 unique Canvas poses; owner art skipped when `actionCode != 0` |
| Evidence | Combined boards only | Named Rev 2.1 matrix, grayscale board, busy-backdrop board, SHA-256 `manifest.json` |

## Files

- `android/app/src/main/java/com/dial/van/visual/VanAura.kt`
- `android/app/src/main/java/com/dial/van/visual/VanAuraSpec.kt`
- `android/app/src/main/java/com/dial/van/visual/VanGlassTokens.kt`
- `android/app/src/main/java/com/dial/van/visual/VanGlassSurface.kt`
- `android/app/src/main/java/com/dial/van/visual/VanEffectBudget.kt`
- `android/app/src/main/java/com/dial/van/visual/VanScene.kt`
- `android/app/src/main/java/com/dial/van/overlay/OverlayStateStore.kt`
- `android/app/src/main/java/com/dial/van/overlay/OverlayTheme.kt`
- `android/app/src/main/java/com/dial/van/overlay/FloatingOverlayService.kt`
- `android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt`
- `android/visual-preview/src/main/kotlin/com/dial/van/preview/GlassPainter.kt`
- `android/visual-preview/src/main/kotlin/com/dial/van/preview/VanPreviewSheets.kt`
- `android/visual-preview/src/main/kotlin/com/dial/van/preview/VanPreviewMain.kt`
- `android/visual-preview/src/main/kotlin/com/dial/van/preview/VanEvidenceMatrix.kt`
- `android/visual-preview/src/test/kotlin/com/dial/van/preview/VanAcceptanceGateTest.kt`
- `visual-authority/van-visual-authority-v2.yaml`

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
- `van_aura_topology.png`
- `rev21/` named shots, `grayscale-state-clarity.png`, `busy-backdrop-resilience.png`, `manifest.json`

## Residual gaps (EXTERNAL)

- Authored `van.riv` artboard and owner visual sign-off
- Physical device / production keystore
- Figma source boards
