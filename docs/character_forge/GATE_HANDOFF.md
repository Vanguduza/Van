# Character Forge gate hand-off — what is ready, and what only the owner or a device can supply

Status on 2026-09-25: **no gate is promoted.** `python -m tools.character_forge.cli status` reports
`current_stage: vector` with blockers `SOURCE_SET_NOT_ADMITTED`,
`OWNER_SOURCE_CONFIRMATION_PENDING`, `RIVE_ASSET_MISSING` and `S24_DEVICE_GATES_NOT_RUN`.
The M1 layer artifact is admitted: the CF-D-09-HYBRID raster set
(`06-raster-clean/candidate_b_front`, `layer_raster_set:67af0118…`), with the owner's PASS review
recorded at the owner's instruction on 2026-09-25. `gate m1` now fails only on M0.

The gates are designed so that nobody can pass them on someone else's behalf. The owner's
verdicts, the owner's biometric acceptance, physical Galaxy S24 Ultra (SM-S928*) runs and an
independent reviewer are evidence, not paperwork, so this document prepares them and does not
record them. Each record command below refuses input that does not bind to real evidence.

| Gate | What it proves | Prepared in this repository | Still needs | Record with |
|---|---|---|---|---|
| **M0 — source admission** | The owner confirms the identity source the character is built from | Candidate B locked (CF-D-05-REV2_1): `APPROVED_IDENTITY_LOCK.yaml`, reference pack, `HIGHRES_MASTER_APPROVAL.yaml` bound to the lock hash | **Owner:** confirm Candidate B as the admitted source | `cli source admit …`, then `cli owner confirm-source …`, then `cli gate m0` |
| **M1 — layers** | A clean layered `06-vectors-clean/van_layers.svg` **or**, under CF-D-09, a raster layer set in `06-raster-clean/` exists, passes lint and independent review | Lint-clean blockout with every required and M2 group; pivots; palette; proportion lint (`PROPORTION_OUTSIDE_LOCK`); on-model key poses. CF-D-09 raster set built by `build_raster_layers` into `04-raster-layers/candidate_b_front/` (32 layers, recomposite exact outside the lens, 3.17 heads) and checked by `raster_lint`. Per CF-D-09-HYBRID, face parts, sleeves and torso are cut on hand-placed geometry (`03-masks/`) and hidden regions are AI-painted by big-lama (fills cached in `02-ai-working/`, labelled per layer) | **Raster route:** an artist checks the set and copies it into `06-raster-clean/`, then admits it; an **independent reviewer** records the review. **Vector route:** a vector artist redraws every group over `reference/turnaround/` (the traced candidate was rejected, CF-D-09-REJECT-TRACED) | Raster: `cli layers lint`, `cli layers admit DIR --artist …`, `cli review record --target raster`. Vector: `cli vectors lint`, `cli vectors admit`, `cli review record --target layer`. Then `cli gate m1` |
| **M2 — core rig** | IDLE/LISTENING/THINKING/SPEAKING + HELLO_WAVE/ACK_NOD/POINT_TARGET rigged; owner likes the core | Rive contract, rig pivots, key-pose rotations (`keyposes/KEY_POSES.yaml`), visemes, flame-aura boundary. Netcup authoring workstation installed and strictly qualified at `be49e8e`; Rive CLI 1.1.1 and Inkscape 1.2.2 pinned from its lock (`evidence/character-forge/netcup_toolchain_lock_2026-09-24.json`) | **Rive author:** build the core `.riv` (the owner first runs `rive login` on Netcup). **CI:** emulator validation. **Owner:** core verdict | `cli rive receipt`, `cli rive stage-candidate`, `cli rive record-validation`, `cli owner record-core-verdict`, `cli gate m2` |
| **M3 — full rig** | All 18 states and 14 actions, skeleton frozen, independently reviewed | Every state and action has an on-model key pose and rig values; state/action map complete | **Rive author:** full rig. **Independent reviewer:** full-rig review | `cli review record --target full`, `cli gate m3` |
| **M4 — device** | Runs within budget on the target phone | `DEVICE_CHECKLIST.yaml`; janky-frame threshold (5%) wired into instrumentation | **Physical SM-S928\*:** the device checklist run, with its captured evidence | `cli gate m4` |
| **M5 — owner acceptance** | The owner accepts VAN on their own phone, confirmed biometrically | Interim VAN (real Candidate B art + flame aura) already ships, so acceptance compares like with like | **Owner:** acceptance on the device, with biometric confirmation | `cli owner record-acceptance …`, `cli gate m5`, then `cli release promote` |

## What changed in this round that the gates rely on

- **Identity:** Candidate B, 3.2 ± 0.3 heads, dark orb with bar eyes (CF-D-05-REV2_1).
- **Aura:** a Goku/Naruto flame envelope, Android-native, with no line geometry (CF-D-06, CF-D-06-REV1). `van.riv` must stay transparent and aura-free.
- **Interim VAN:** real Candidate B art until `van.riv` loads (CF-D-07). Renderer order is `RIVE → CANDIDATE_B → CANVAS`.
- **Key poses:** on-model poses for all states, actions and visemes, with the bone rotations for the rig.
- **M1 by raster layers (CF-D-09):** M1 accepts a raster layer set cut from Candidate B's own pixels. Only one layer artifact is live: admitting a raster set supersedes the admitted SVG, and the reverse. `cli rive receipt --layer-sha` binds a Rive candidate to whichever is admitted. The Rive rig deforms the PNGs with image meshes skinned to bones. The gate re-runs `raster_lint` on the admitted directory (hashes, required layers, recomposite, head count), so the lane needs numpy and Pillow where `gate m1` runs. Withdrawing CF-D-09 withdraws the raster set.

## Next action

The owner runs the M0 confirmation, then work starts on M1. The vector artist begins from
`visual-authority/character-forge/00-source/reference-pack/blockout/van_layers_blockout.svg`.
