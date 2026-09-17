# VAN Visual Rev 2.1 — Historical implementation notes

Status: historical baseline. Aura/runtime sections are superseded by `docs/VAN_LIVING_WIND_FIELD_RUNTIME_REV_1.md` and canonical `visual-authority/van-visual-authority-v2.yaml` revision **2.3**.

Original authority lineage: `docs/VAN_VISUAL_PRODUCTION_SYSTEM_REV_2_1_MASTER_BLUEPRINT.md`, `docs/VAN_VISUAL_PRODUCTION_SYSTEM_REV_2_2_ADDENDUM_AURA_SEMANTIC_ENVELOPE.md`, and `docs/CURSOR_PATCH_PROMPT_VAN_AURA_SEMANTIC_ENVELOPE.md`.

## Thesis shipped in Rev 2.1/2.2

VAN is a solid expressive character surrounded by a three-zone field. Zone A is identity cyan on the body. Zone B is mid interaction. Zone C is the outer semantic envelope. When interface space is needed, the field condenses into glass.

Rev 2.3 retains that semantic ownership but replaces broken orbit/arc geometry with renderer-neutral directional windy-field geometry, and separates character activity from independent health/authority truth.

## Historical changes

| Area | Before | Rev 2.1/2.2 result | Rev 2.3 status |
|---|---|---|---|
| Aura | Radial ellipse + accent ring | Offset-lobe field, filaments, broken arcs | Superseded by `VanFieldGeometryEngine` directional flow |
| Glass | Fill + uniform glow stroke | Tint, shaping gradient, grain, inner highlight, selective specular | Retained |
| Overlay rest | Permanent compact capsule | Frameless VAN + aura | Retained; live state now orthogonal |
| Compact / expanded | Card beside VAN | Glass condenses under VAN | Retained |
| Dock | 5dp cyan bar | Crescent edge slice | Retained |
| Command Centre | Generic placeholder cards | Structured operational surface | Retained; now reads the same live presence frame as overlay |
| Reduced motion | Mapped to STATIC | Designed stillness | Retained and verified against shared geometry |
| Evidence | Combined boards only | Named evidence matrix | Rev 2.3 Java2D/Compose share Zone B/C geometry |

## Current canonical files

- `visual-authority/van-visual-authority-v2.yaml` — revision 2.3
- `docs/VAN_LIVING_WIND_FIELD_RUNTIME_REV_1.md`
- `android/app/src/main/java/com/dial/van/visual/VanPresenceFrame.kt`
- `android/app/src/main/java/com/dial/van/visual/VanWindFieldMotion.kt`
- `android/app/src/main/java/com/dial/van/visual/VanFieldGeometry.kt`
- `android/app/src/main/java/com/dial/van/visual/VanAura.kt`
- `android/visual-preview/src/main/kotlin/com/dial/van/preview/GlassPainter.kt`
- `android/app/src/main/java/com/dial/van/overlay/FloatingOverlayService.kt`
- `android/app/src/main/java/com/dial/van/command/CommandCentreActivity.kt`

## Evidence

`:visual-preview:renderVanPreviews` writes owner-facing evidence into `artifacts/release/preview/`. Under Rev 2.3 those previews consume the same renderer-neutral Zone B/C geometry as the Compose overlay. `.github/workflows/van-ci.yml` runs the Android, lint, test and visual-evidence gates and uploads the rendered preview artifact.

## Residual external gates

- Authored `van.riv` artboard and owner visual sign-off
- Physical Android device certification / production keystore
- Figma source boards
