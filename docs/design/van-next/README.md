# VAN Next — Tactile Spatial rebuild design pack

Design and programme documents for rebuilding VAN's Android frontend in the owner-approved Tactile Spatial style without losing existing functions. Nothing here is implemented, deployed or device-qualified.

| File | What it is |
|---|---|
| `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_6_20261015.md` | **Current blueprint.** Rev 1.6: native chart engine built and tested (§7.8.11); account management with funding ledger and flow-adjusted drawdown (§7.9). Rev 1.5: trading workstation architecture from the MT5/TradingView study; six audit-derived features; live news trading bundle; manual trading with the stop inside the order, adds, Hand to VAN; multi-source news with history-driven decisions; system labels; consolidation first. Change logs at the top. |
| `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_20261015.md` | Rev 1.0, kept for lineage. Superseded (Rev 1.1–1.5 are in git history). |
| `VAN_78_SURFACE_PRESERVATION_MATRIX_REV1_2_20261015.{md,csv,json}` | 78 inherited surfaces with their owner-action obligations, per-surface PR #93 dependency, and additive VAN Next surfaces. |
| `research/FREE_TRADING_NEWS_AND_CALENDAR_FEEDS_20261015.md` | Source research behind §8.2 and §8.10: free, official and paid news, calendar and history sources, with verified vs unverified marked. |
| `research/EXTERNAL_REPO_AUDIT_VIBE_TRADING_FINCEPT_20261015.md` | Reference-only audit (DEC-039) of Vibe-Trading and FinceptTerminal: what VAN already does better, six candidate features to reimplement natively, licence notes. |
| `research/VAN_REA_MT5_TRADINGVIEW_FULL_RESEARCH_20261015.md` | Owner-supplied static study of the MetaTrader 5 and TradingView Android clients (evidence inventories kept outside the repo). |
| `research/VAN_REA_REVIEW_20261015.md` | Review of that study: what was verified, comparison with VAN's code, grading, and how it was applied (§7.8). |
| `VAN_NEXT_OWNER_DECISIONS_REV1.md` | Owner decisions behind Rev 1.1–1.6, and the questions still open. Awaiting owner signature. |
| `reference/VAN_LOCKED_{DARK,LIGHT}_20261015.png` | Locked owner-approved mockups, unaltered (SHA-256 in the blueprint §1.3). |
| `reference/VAN_LOCKED_{DARK,LIGHT}_RELABELLED_REV1_1_20261015.png` | Same mockups with labels changed to the system vocabulary (blueprint §2.6). |
| `reference/relabel_mockups.py`, `relabel_{dark,light}.json` | Reproduces the relabelled images from the originals: `python3 relabel_mockups.py VAN_LOCKED_DARK_20261015.png relabel_dark.json out.png` (needs Pillow, NumPy and the Inter font). |

Baselines: `main` `8eb1889822fc8a83f219977c15340172e16acd91`, PR #93 `dfc1557ab99ad8d41cf84714e1bb671e89b045e6`.
