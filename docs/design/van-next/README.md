# VAN Next — Tactile Spatial rebuild design pack

Design and programme documents for rebuilding VAN's Android frontend in the owner-approved Tactile Spatial style without losing existing functions. Nothing here is implemented, deployed or device-qualified.

| File | What it is |
|---|---|
| `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_9_20261015.md` | **Current blueprint — freeze candidate.** Rev 1.9: independent audit corrections (qualification closure, pending-order risk, closed state machines, news ticket grant, winning-only adds, no unmanaged escape, crosswalk), owner decisions OD-23…OD-27. Rev 1.8: Rev 2 pack merged (in-app funds, ownership planes, trading modes from PR #92, owner decisions OD-18…OD-22). Rev 1.7: chart engine moved to an unqualified spike branch; development order derived in `plan/`; freeze criteria in `VAN_NEXT_BLUEPRINT_FREEZE_LIST_REV1_9.md`. Rev 1.6: native chart engine built, tested and extended from the 39 REA records (§7.8.11); account management with funding ledger and flow-adjusted drawdown (§7.9). Rev 1.5: trading workstation architecture from the MT5/TradingView study; six audit-derived features; live news trading bundle; manual trading with the stop inside the order, adds, Hand to VAN; multi-source news with history-driven decisions; system labels; consolidation first. Change logs at the top. |
| `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_20261015.md` | Rev 1.0, kept for lineage. Superseded (Rev 1.1–1.8 are in git history). |
| `VAN_78_SURFACE_PRESERVATION_MATRIX_REV1_2_20261015.{md,csv,json}` | 78 inherited surfaces with their owner-action obligations, per-surface PR #93 dependency, and additive VAN Next surfaces. |
| `research/FREE_TRADING_NEWS_AND_CALENDAR_FEEDS_20261015.md` | Source research behind §8.2 and §8.10: free, official and paid news, calendar and history sources, with verified vs unverified marked. |
| `research/EXTERNAL_REPO_AUDIT_VIBE_TRADING_FINCEPT_20261015.md` | Reference-only audit (DEC-039) of Vibe-Trading and FinceptTerminal: what VAN already does better, six candidate features to reimplement natively, licence notes. |
| `research/VAN_REA_MT5_TRADINGVIEW_FULL_RESEARCH_20261015.md` | Owner-supplied static study of the MetaTrader 5 and TradingView Android clients (evidence inventories kept outside the repo). |
| `research/VAN_REA_REVIEW_20261015.md` | Review of that study: what was verified, comparison with VAN's code, grading, and how it was applied (§7.8). |
| `VAN_NEXT_BLUEPRINT_FREEZE_LIST_REV1_9.md` | What must be true to freeze the blueprint, what is already closed (with evidence), and the owner decisions still needed. |
| `plan/VAN_NEXT_DEVELOPMENT_PLAN_REV1.md` (+ `.json`) | The deterministic development plan: 71 packets in a derived order, entry and exit gates, owner decisions per packet. Regenerate with `python3 plan/generate_plan.py`; `--check` validates, `--selftest` proves the checks. |
| `contracts/` | Accounts & Funds contract and funding-intent schema from the Rev 2 pack; **`VAN_STATE_MACHINES_REV1_9.json`** (VAN's canonical machines) with `check_state_machines.py` (`--selftest`); the pack's original `STATE_MACHINES.json` kept for lineage. |
| `crosswalk/` | Reviewed Rev 2 → Rev 1.9 mapping of all 18 product truths and 93 features; the unreviewed 171-atom seed for DU-01. |
| `research/VAN_NEXT_REV18_INDEPENDENT_AUDIT_RESPONSE_20261015.md` | How each of the 22 audit findings was verified and what Rev 1.9 changed. |
| `research/VAN_NEXT_PACK_REV2_COMPARISON_20261015.md` | Measured comparison of the Rev 2 Quantum pack with Rev 1.7, and the owner decisions D1–D6. |
| `research/VAN_REA_EVIDENCE_STUDY_39_RECORDS_20261015.md` | Study of the 39 original REA records on `van-trading-core` (read-only, names only): what each record showed, the chart engine changes and tests derived from it, and account management additions A1–A10. |
| `VAN_NEXT_OWNER_DECISIONS_REV1.md` | Owner decisions behind Rev 1.1–1.9, and the questions still open. Awaiting owner signature. |
| `reference/VAN_LOCKED_{DARK,LIGHT}_20261015.png` | Locked owner-approved mockups, unaltered (SHA-256 in the blueprint §1.3). |
| `reference/VAN_LOCKED_{DARK,LIGHT}_RELABELLED_REV1_1_20261015.png` | Same mockups with labels changed to the system vocabulary (blueprint §2.6). |
| `reference/relabel_mockups.py`, `relabel_{dark,light}.json` | Reproduces the relabelled images from the originals: `python3 relabel_mockups.py VAN_LOCKED_DARK_20261015.png relabel_dark.json out.png` (needs Pillow, NumPy and the Inter font). |

Baselines: `main` `8eb1889822fc8a83f219977c15340172e16acd91`, PR #93 `dfc1557ab99ad8d41cf84714e1bb671e89b045e6`.
