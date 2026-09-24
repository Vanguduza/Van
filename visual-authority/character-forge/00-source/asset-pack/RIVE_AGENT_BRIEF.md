# RIVE Agent Build Brief — VAN

## Mission

Build the VAN authored Rive character from the admitted M1 vector artifact without changing identity,
public wire contract, Android-owned aura, or owner authority.

Read these files before authoring:
1. `ASSET_PACK_MANIFEST.yaml`
2. `LAYER_SPEC.yaml`
3. `RIG_SPEC.yaml`
4. `STATE_ACTION_MATRIX.yaml`
5. `SPEECH_SPEC.yaml`
6. `VALIDATION_MATRIX.yaml`
7. the canonical owner sources referenced by the manifest

## Non-negotiable build boundary

- Artboard: `Van`
- State machine: `VanRuntime`
- Exactly 9 public inputs and 8 public triggers from `rive_contract.json`
- One character rig; no state-specific duplicate characters
- Aura/electrical field and workboard glass stay Android-native
- Transparent artboard; >=6% gesture margin
- Nothing except visor lens/orb optical treatment may make body/hair/skin/clothes translucent

## Stage 1 — vector admission

Do not start Rive authoring until:
- source admission has recorded hashes,
- owner source-set confirmation exists,
- `van_layers.svg` passes `vectors lint`,
- `vectors admit` records it.

Do not auto-trace a lock-sheet composite into one flat path. Preserve the 23 required semantic root groups.

## Stage 2 — core rig only

Implement only:
- IDLE, LISTENING, THINKING, SPEAKING
- HELLO_WAVE, ACK_NOD, POINT_TARGET
- gaze/head-eye relationship
- blink
- mouth_open + viseme 0..4
- breathing
- orb idle drift

All 9 inputs and all 8 triggers must already exist.

Build a core candidate, create the packaging receipt, stage it, run Android instrumentation, and stop
for the M2 owner verdict. Do not continue full authoring before PASS.

## Stage 3 — full rig

Without changing the M2 skeleton:
- add the remaining durable states and finite actions,
- keep every state visually distinct from IDLE,
- keep speech and gaze additive,
- obey action durations and return behavior,
- preserve core regression baselines,
- run full Android validation and independent review.

## Drift stops

Stop rather than improvise if:
- a source image conflicts with the owner lock sheet,
- a required layer cannot be derived without inventing hidden geometry,
- a new public input seems necessary,
- a state/action needs a contract change,
- identity colours would need to leave the linter families,
- the skeleton would need restructuring after M2 PASS.

Optional reconstruction/segmentation tools may create candidates only. They never become visual authority
and never write production Rive assets directly.
