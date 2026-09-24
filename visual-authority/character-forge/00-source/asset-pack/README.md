# VAN Approved Character — Rive Injection Asset Pack

Status: **IDENTITY AUTHORITY LOCKED / RIVE AUTHORING INPUT**  
Pack revision: **2.0 — 2026-09-24**

This pack is the only Character Forge input surface for authoring VAN. It replaces the rejected
light-skinned/headband lock sheet, procedural placeholder sheets and crops derived from them.

## Authority order

1. `visual-authority/assets/pack/owner_board_visual_authority.png` — canonical owner-approved visual board.
2. `APPROVED_IDENTITY_LOCK.yaml` — machine-readable identity and geometry lock.
3. `visual-authority/rive_contract.json` — public artboard/state-machine wire contract.
4. `LAYER_SPEC.yaml`, `RIG_SPEC.yaml`, `ANIMATION_SPEC.yaml`, `STATE_ACTION_MATRIX.yaml`,
   `SPEECH_SPEC.yaml` — deterministic construction and motion truth.
5. `AURA_HANDOFF_SPEC.yaml` — Android-native aura boundary; aura is not authored into the .riv.
6. `VALIDATION_MATRIX.yaml` and repository gates — drift detection and promotion rules.

Other owner boards may be used only as contextual UX/composition references. They cannot override the
canonical visual board or identity lock.

## Identity summary

VAN has silver/white swept hair, medium-brown skin, blue eyes, a cyan/blue transparent visor,
black/white technical clothing over a charcoal underlayer, black technical gloves, DIAL-cyan accents,
a cyan holographic orb, no headband, and compact but human-readable approximately 5.75-head proportions.
Hair, skin, eyes and clothing are opaque. Only visor/orb optical layers may be translucent.

## Hard boundary

The Rive file contains the **solid character + orb**. The detached windy/electrical aura and glass UI
remain Android-native. A halo, full ring, body glow, background or workboard inside `van.riv` is a
contract violation.

## Promotion

This pack prevents identity/specification drift; it does not falsify final production acceptance.
The authored `van.riv` is promoted only after M1 vector review, M2 core owner verdict, M3 independent
full-rig review, production-path CI, physical SM-S928* evidence and owner biometric acceptance.
