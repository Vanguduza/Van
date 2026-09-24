# VAN Rive Reference Pack — artwork and measurement inputs

Status: **REFERENCE INPUT, PRE-M1** · Authority: **Candidate B** (CF-D-05-REV2_1)
· Generator: `python -m tools.character_forge.build_reference_pack`
· Drift check: `python -m tools.character_forge.build_reference_pack --check` (runs in the contract suite)

This pack is the artwork half of Character Forge's Rive injection. Its sibling
`../asset-pack/` holds the rules: identity lock, layers, rig, animation, state/action, speech,
aura boundary and validation. This pack holds what an artist or agent builds from: every
reference image, measurement, pivot, guide and blockout. Each one traces to exact pixels of the one
approved image, `visual-authority/character-forge/01-master-candidates/van_master_source_candidate_b.png`
(native 1536×1024). The crops come from the native file, never from the 4× Lanczos upscale, so they
carry no interpolated detail.

Nothing here adds identity. Crops are exact regions of Candidate B, and `REFERENCE_INDEX.json` lists
every box. Colours and proportions are measured from those pixels. Aura and overlay numbers are
parsed from the shipping Android code and `van-visual-authority-v2.yaml`.

## Contents

| Path | What it is | Used at |
|---|---|---|
| `reference/turnaround/*.png` | front, ¾ front, side, ¾ rear and rear construction views | M1 vector tracing; M2 rig pivots |
| `reference/details/orb_*.png` | the orb in all five turnaround views | M1 orb, M2 orb drift |
| `reference/details/detail_*.png` | head front and ¾, visor, gloves, jacket, orb and boot detail panels | M1 detail and shading |
| `PALETTE_MEASURED.yaml` | measured shadow/mid/lit ramps per material; ΔE2000 checks against the lock | M1 fills and shading |
| `PROPORTIONS.yaml` + `guides/proportion_guide_front.png` | measured landmarks, the locked head count (3.15 measured, lock 3.2 ± 0.3), orb size, artboard mapping | M1 construction |
| `RIG_PIVOTS.yaml` | bone and pivot positions (hips, knees, ankles and the orb included) in artboard units (1000×1000) | M2 skeleton |
| `blockout/van_layers_blockout.svg` | **layered construction scaffold**: every required and `extra_` group at B's measured positions in lock colours; passes `vectors lint` | M1 starting file |
| `guides/artboard_overlay_template.svg` | artboard `Van`, 6% gesture margin, aura zones A–C (1.00/1.12/1.35–1.70×), 48/96 dp crop circles, pivots | locked guide layer in Inkscape/Rive |
| `OVERLAY_COMPOSITION.yaml` | overlay sizes (92 dp resting, 76 dp docked, 168/88 dp hit, 280 dp compact), rendered sizes, aura reach check | framing |
| `AURA_STATE_TABLE.yaml` | per-state aura parameters and segment angles **parsed from `VanAuraSpec.kt`**, with status accents | keeping the character clear of the Android field |
| `keyposes/` + `KEY_POSES.yaml` | **on-model key poses** for all 18 states, 14 actions and 5 visemes, made from Candidate B itself as a cut-out puppet posed about the rig pivots; each lists the bone rotations and face settings that produce it | M2/M3 key poses and rig targets |
| `STATE_ACTION_REFERENCE_MAP.yaml` | each state and action → its on-model key pose and rig values; off-model production-v3 sheets listed last as `semantic_only` | M2/M3 pose planning |
| `guides/reference_contact_sheet.png` | review sheet of every crop | reviewers |
| `interim/van_candidate_b_front.png` + `INTERIM_ART.yaml` | native cut-out of B's front view, framed like the artboard; bundled as the app's interim VAN (CF-D-07) | shipping interim character |
| `PACK_MANIFEST.json` | SHA-256 of every file, plus the authority's SHA | drift check |

## On-model versus semantic references

Every state, action and viseme has an **on-model key pose** in `keyposes/`. Each one is made from
Candidate B's own pixels: the native front view is cut into head, forearms, orb and body and
posed about the neck and elbow pivots, which is what the Rive rig will do. Faces change through
feathered edits in B's own sampled colours: closed lids, brow angles and mouth shapes.
`KEY_POSES.yaml` lists the rotations for each pose, so it doubles as a rig target sheet.

They are construction references, not final art: the upper arms don't move, and fingers can't
change shape (pointing and thumbs-up are shown by forearm angle). The production-v3 sheets stay
listed as `semantic_only`: they illustrate meaning, but their figure is off-model and is never
cropped into this pack.

## How to use it (M1 → M3)

1. Open `blockout/van_layers_blockout.svg` in Inkscape.
   - Place `reference/turnaround/turnaround_front.png` underneath, scaled so the landmarks in `PROPORTIONS.yaml` meet the blockout.
   - Place `guides/artboard_overlay_template.svg` above it as a locked guide.
2. **Redraw every group** over the reference, keeping group ids and topology.
   - Base fills use the identity-lock tokens.
   - Shading shapes use the measured `shadow_p10`/`lit_p90` of the same material.
   - The body stays opaque. Only `visor_lens` and the orb optics may be translucent.
3. Keep the character inside the 6% margin. The aura zones on the template are **Android's**, so the `.riv` stays transparent there.
4. Lint, admit, and get an independent review (`vectors lint` → `vectors admit` → `review record --target layer`).
   - With Inkscape geometry, the lint also measures head count (hair crown→chin over crown→sole).
   - It fails with `PROPORTION_OUTSIDE_LOCK` outside 2.9–3.5.
5. Build the M2 skeleton on `RIG_PIVOTS.yaml`.
   - Pose meaning comes from `STATE_ACTION_REFERENCE_MAP.yaml`.
   - Motion timing comes from `../asset-pack/ANIMATION_SPEC.yaml` and `STATE_ACTION_MATRIX.yaml`.
   - Every pose is drawn on B's proportions.
6. Where the map says `gap:`, compose from the named note plus the matrix pose. Never invent a new face, prop or costume element.

The blockout is a scaffold, not art. Its shapes are simple primitives placed at measured
positions, so pivots, layer order and proportions are right from the first file. Admitting it
unchanged as `van_layers.svg` would fail the independent layer review by design.

The blockout keeps two conventions:
- `_l` is the viewer's left, matching the crops. The viewer-left arm reaches out palm-up under the orb, as in B.
- The legs and boots are carried as `extra_leg_*` and `extra_boot_*` so knees can bend.

## Open items (not resolved by this pack)

| ID | Finding | Needed |
|---|---|---|
| REF-GAP-001 | PARTLY RESOLVED: on-model key poses now exist for every state, action and viseme (`keyposes/`). They are puppet construction references; finger poses and upper-arm motion still need the rig author. | Owner review of the key-pose sheet; finger shapes authored at M2. |
| REF-GAP-002 | RESOLVED: every state and action, including the twelve previously without references, has an on-model key pose. | — |
| REF-GAP-003 | Candidate B is AI-generated. Fine detail such as zips, glove panels and boot trim is interpreted, not traced. | Owner review of detail at M1. |
| REF-GAP-004 | RESOLVED: the app shows real Candidate B art (`interim/`, CF-D-07); `VanScene` is redrawn from B's landmarks as the last resort. | — |

## Regenerating

Regenerate the pack only when Candidate B, the aura code or the identity lock changes:
`python -m tools.character_forge.build_reference_pack`, then commit. The contract
test fails if any file drifts from `PACK_MANIFEST.json`, or if the authority's SHA changes
without a rebuild.
