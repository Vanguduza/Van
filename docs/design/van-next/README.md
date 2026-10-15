# VAN Next — Tactile Spatial rebuild design pack

Design and programme documents for rebuilding VAN's Android frontend in the owner-approved Tactile Spatial style without losing existing functions. Nothing here is implemented, deployed or device-qualified.

| File | What it is |
|---|---|
| `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_1_20261015.md` | **Current blueprint.** Rev 1.1: manual trading, system labels, news briefs on the existing pipeline, consolidation first. Change log at the top. |
| `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_20261015.md` | Rev 1.0, kept for lineage. Superseded. |
| `VAN_78_SURFACE_PRESERVATION_MATRIX_REV1_1_20261015.{md,csv,json}` | 78 inherited surfaces with their owner-action obligations, per-surface PR #93 dependency, and additive VAN Next surfaces. |
| `VAN_NEXT_OWNER_DECISIONS_REV1.md` | Owner decisions behind Rev 1.1, and the questions still open. Awaiting owner signature. |
| `reference/VAN_LOCKED_{DARK,LIGHT}_20261015.png` | Locked owner-approved mockups, unaltered (SHA-256 in the blueprint §1.3). |
| `reference/VAN_LOCKED_{DARK,LIGHT}_RELABELLED_REV1_1_20261015.png` | Same mockups with labels changed to the system vocabulary (blueprint §2.6). |
| `reference/relabel_mockups.py`, `relabel_{dark,light}.json` | Reproduces the relabelled images from the originals: `python3 relabel_mockups.py VAN_LOCKED_DARK_20261015.png relabel_dark.json out.png` (needs Pillow, NumPy and the Inter font). |

Baselines: `main` `8eb1889822fc8a83f219977c15340172e16acd91`, PR #93 `dfc1557ab99ad8d41cf84714e1bb671e89b045e6`.
