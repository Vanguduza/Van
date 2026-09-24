# VAN Character Forge Production V3

Status: IMPLEMENTATION AUTHORITY — PRE-PRODUCTION / OWNER-GATED

## Purpose

Character Forge Production V3 turns the approved VAN visual authority into a reproducible Rive production system without allowing AI-assisted tooling to silently redefine VAN.

The core rule is:

> AI may propose segmentation, occluded geometry and rig structure. Deterministic tooling must classify, hash, validate and reproduce those proposals. Owner authority decides what may become canonical.

The existing primary visual authority remains:

- `visual-authority/assets/pack/owner_board_visual_authority.png`
- Git blob: `fc18bbe0b91e5b85d8cf8211314a69cb90b8bc0b`

The board explicitly declares skin token `#B8853C`; that declared token outranks raster sampling variance.

## Pipeline

1. **M0 — Source lock**
   - exact canonical source SHA/blob
   - exact machine identity lock
   - rejected-source denylist enforced

2. **M0.5 — High-resolution master candidate**
   - recreate/upscale from the canonical board only
   - candidate never becomes authority automatically
   - minimum short edge 2048 px
   - no visible design invention is admissible
   - owner approval binds the exact candidate SHA

3. **M1 — Semantic decomposition**
   - optional See-through V3 GPU proposal
   - Grounded/SAM2/BiRefNet may refine masks
   - all generated hidden regions are `INFERRED_OCCLUSION`
   - visible identity-bearing pixels may never be silently generated

4. **M1.5 — Semantic vectorization**
   - per-part masking then tracing
   - exact Character Forge layer names
   - per-part topology budgets and 1200-path hard ceiling
   - self-intersection, tiny-island and out-of-scope groups rejected

5. **M2 — Rig proposal**
   - Stretchy Studio may propose DWPose skeletons, meshes and weights
   - exported Spine JSON is an input proposal, never final authority
   - import into neutral `CF Rig IR`
   - unsupported Spine features fail closed

6. **M2.5 — Rive authoring**
   - CF Rig IR is translated to a schema-driven Rive authoring plan
   - Rive CLI/RML is the deterministic authoring authority
   - runtime public surface remains `Van` / `VanRuntime`

7. **M3 — Animation**
   - 18 durable states and 14 finite actions
   - five visemes
   - facial, gaze, blink, breathing, hair/jacket secondary motion
   - no aura baked into Rive

8. **M4 — Device qualification**
   - exact Rive SHA
   - Galaxy S24 Ultra evidence
   - Perfetto trace
   - all state/action frames
   - aura/character coexistence checks

9. **M5 — Owner release**
   - signed owner acceptance binds:
     - Rive SHA
     - contract SHA
     - identity spec SHA
     - visual acceptance matrix SHA
     - identity lock SHA

## Provenance vocabulary

Every visual layer or derived asset must carry exactly one provenance class:

- `CANONICAL_VISIBLE` — direct visible geometry/pixels from an owner-approved master.
- `DERIVED_VISIBLE` — deterministic segmentation/vectorization of canonical visible material.
- `INFERRED_OCCLUSION` — AI-generated hidden geometry. Production-blocking.
- `OWNER_APPROVED_OCCLUSION` — previously inferred hidden geometry explicitly approved by the owner.
- `GENERATIVE_VISIBLE` — AI-invented visible identity-bearing geometry. Always production-blocking.

No conversion step may downgrade provenance risk. `INFERRED_OCCLUSION` becomes production-admissible only through explicit owner approval. `GENERATIVE_VISIBLE` has no automatic promotion path.

## High-resolution master policy

The approved board is authoritative but is not sufficient by itself as a rig-ready master at facial-detail scale. A recreated high-resolution master is therefore treated as a **candidate** until owner acceptance.

The candidate must preserve:
- silver/white swept hair
- cyan/blue transparent visor
- medium-brown skin token `#B8853C`
- blue eyes
- black/white technical jacket
- charcoal underlayer
- black technical gloves
- cyan DIAL accents
- 5.5–6 head chibi-realistic proportions
- no headband
- dark/navy cyan holographic orb
- body opacity except visor/orb optics

The candidate may improve edge clarity and hidden construction, but may not redesign face shape, hairstyle silhouette, visor geometry, jacket silhouette, gloves, boots, orb identity or proportions without a new owner-approved visual-authority revision.

## AI tool lanes

### See-through

Pinned source code is treated as an optional GPU proposal engine. It may create semantic layers and inpaint hidden regions. Its output must be receipted and remains non-authoritative until provenance review.

Production use of model weights is blocked until the weight licences and exact weight hashes are recorded as cleared.

### Stretchy Studio

Pinned MIT source is used only as a rig-proposal editor. Browser interaction is not a source of truth. Exported Spine JSON is hashed and imported into CF Rig IR. The importer validates every supported structure and refuses unsupported features.

### Rive

Rive CLI/RML remains the final deterministic authoring plane. The Forge must query the installed Rive schema before emitting features whose exact RML representation is version-sensitive.

## Determinism

Every proposal/import/build receipt records:
- source image SHA
- source master SHA
- source tool repository and commit
- model/checkpoint SHA where applicable
- configuration
- seed where applicable
- output SHA(s)
- provenance classification
- author/worker identity
- timestamp
- owner-approval reference where required

A tool being reproducible does not make its visual output authoritative.

## Bootstrap topology

The Netcup `dial control` VM hosts:
- Character Forge controller
- deterministic lint/provenance/IR tools
- Rive CLI authoring plane
- Stretchy Studio local source/editor
- Playwright/Stagehand browser automation support where explicitly enabled
- GPU-job client

See-through heavy inference runs on an optional GPU worker. The Netcup bootstrap must not pretend that CPU-only execution satisfies the GPU decomposition gate.

## Required repository truth

Machine-readable V3 truth lives under:

`visual-authority/character-forge/00-source/production-v3/`

The controller implementation lives under:

`tools/character_forge/`

The bootstrap lives under:

`deploy/character-forge/bootstrap-production-v3.sh`

No M1–M5 milestone may be marked complete solely because these files exist.


## Bootstrap commands

After this branch is merged, bootstrap the exact merged revision on the Netcup DIAL-control VM:

```bash
cd /path/to/Van
export VAN_COMMIT_SHA="$(git rev-parse HEAD)"
sudo -E ./deploy/character-forge/bootstrap-netcup-authoring.sh
```

The base bootstrap now invokes `bootstrap-production-v3.sh` by default. Set
`CHARACTER_FORGE_ENABLE_PRODUCTION_V3=0` only for recovery/diagnostic runs.

The resulting controller exposes:

```text
van-character-forge-v3
Stretchy Studio: http://127.0.0.1:5173
state/lock: /var/lib/dial-character-forge/production-v3.lock.json
GPU job outbox: /var/lib/dial-character-forge/gpu-outbox
GPU result inbox: /var/lib/dial-character-forge/gpu-inbox
```

A GPU worker is bootstrapped separately:

```bash
sudo CHARACTER_FORGE_WEIGHT_LOCK=/etc/van-character-forge/see-through-weights.lock.yaml \
  ./deploy/character-forge/bootstrap-gpu-worker-v3.sh
```

Production mode refuses to start until the weight lock is `CLEARED` and every configured
checkpoint exists locally and matches its exact SHA-256. Use the checked-in weight-lock template
as the starting point.

### High-resolution master workflow

1. Use the committed `van_canonical_reference_2x.png` as the exact 3072×2048 comparison reference.
2. Recreate/commission a genuinely detailed master from the canonical character.
3. Stage it with `van-character-forge-v3 master stage`.
4. Review every item in `HIGHRES_MASTER_APPROVAL_TEMPLATE.yaml`.
5. Only an exact owner-approved SHA may be promoted to `01-master-approved/van_master_highres.png`.
6. Semantic decomposition and rig proposal begin only after that promotion.

The exact 2× reference is intentionally not described as adding detail; its receipt records
`adds_new_identity_detail: false`. This prevents an interpolation upscale from being confused with
a genuinely authored high-resolution master.
