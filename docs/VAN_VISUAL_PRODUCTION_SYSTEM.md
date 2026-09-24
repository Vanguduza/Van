# VAN Visual Production System

Status: CANONICAL — APPROVED CHARACTER AUTHORITY CONSOLIDATED 2026-09-24

## Pipeline

1. Canonical owner board: `visual-authority/assets/pack/owner_board_visual_authority.png`
2. Machine identity lock: `visual-authority/character-forge/00-source/asset-pack/APPROVED_IDENTITY_LOCK.yaml`
3. Rive wire contract: `visual-authority/rive_contract.json`
4. Deterministic Character Forge injection pack under `visual-authority/character-forge/00-source/asset-pack/`
5. M1 semantic vector layer sheet: `visual-authority/character-forge/06-vectors-clean/van_layers.svg`
6. M2/M3 Rive candidates with receipts, CI motion evidence and independent review
7. Production integration only after M3; physical SM-S928* qualification and owner acceptance for M4/M5

## Canonical visual sources

| Role | Path |
|---|---|
| Sole primary character image authority | `visual-authority/assets/pack/owner_board_visual_authority.png` |
| Identity / palette / geometry lock | `visual-authority/character-forge/00-source/asset-pack/APPROVED_IDENTITY_LOCK.yaml` |
| Layers | `visual-authority/character-forge/00-source/asset-pack/LAYER_SPEC.yaml` |
| Rig | `visual-authority/character-forge/00-source/asset-pack/RIG_SPEC.yaml` |
| Motion | `visual-authority/character-forge/00-source/asset-pack/ANIMATION_SPEC.yaml` |
| States/actions | `visual-authority/character-forge/00-source/asset-pack/STATE_ACTION_MATRIX.yaml` |
| Speech | `visual-authority/character-forge/00-source/asset-pack/SPEECH_SPEC.yaml` |
| Android aura boundary | `visual-authority/character-forge/00-source/asset-pack/AURA_HANDOFF_SPEC.yaml` |
| Validation | `visual-authority/character-forge/00-source/asset-pack/VALIDATION_MATRIX.yaml` |
| Rejected-source denylist | `visual-authority/character-forge/00-source/asset-pack/LEGACY_ASSET_DENYLIST.yaml` |
| Production Rive after accepted promotion | `visual-authority/rive/van_runtime.riv` |

The former top-level PNG reference sheets, light-skinned/headband lock sheet and their derived Android
bitmap poses are deleted. They are not historical fallback authority and must not be regenerated.

Until the accepted `.riv` exists, the product fails closed to the canonical Canvas VAN; the retired
OWNER_ART bitmap rung is never selected.
