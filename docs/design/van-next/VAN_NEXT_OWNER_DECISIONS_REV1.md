# VAN Next — Owner Decision Record, Rev 1

**Record ID:** `VAN-NEXT-OD-REV1-20261015`
**Status:** `RECORDED_FROM_OWNER_CHAT / AWAITING_OWNER_SIGNATURE`
**Recorded:** 15 October 2026, from the owner's instructions in a Claude Code session reviewing `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_20261015.md`.
**Applies to:** `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_5_20261015.md` and its companion matrix. OD-07…OD-15 were added on 15 October 2026 after the owner reviewed Rev 1.1.

Under the VAN Project Truth Protocol an owner-signed, device-authenticated instruction outranks this record. These decisions bind development packets once the owner signs this record (blueprint §2.1, §17 F0). Until then they are the owner's stated intent, and no trading mandate, live permission or production change follows from them.

| ID | Decision (owner's words, condensed) | Effect in the blueprint |
|---|---|---|
| OD-00 | The two dark/light screenshots are the visual authority (prior instruction). | Locked originals kept unaltered in `reference/` with their SHA-256 hashes. |
| OD-01 | "A setup that allows manual trade entries or exits that are governed by the system's risk profiles, where manual entries will also have strict automated stop losses and optional take profits." | Blueprint §0.2 item 11 and §7.4; DU-28; requirement VAN-NX-027. Four sub-decisions still open (§7.4.9). |
| OD-02 | "Change the mockup labels to match the system." | §2.6 label table; relabelled references `reference/*_RELABELLED_REV1_1_20261015.png`; visual delta VD-01. |
| OD-03 | The five Trading Home entry points (Markets, Watchlist, Potential trades, Chart, Intelligence) were requested by the owner. | Recorded as visual delta VD-02, not drift. |
| OD-04 | "Change the news plan to match the code and make improvements to ensure news analysis is provided in simple terms and how it translates to trades." | §8 rebuilt on `news_ingress`; News briefs with a deterministic trade-effect table. |
| OD-05 | Repository consolidation is a priority, so the new build does not silently thin or omit features and functions that are documented or meant to be ported from the old build; it must also stop pollution of the new frontend UX/UI. | §0.2 item 12, §12.5 (DU-00 first), §12.6 module isolation, §19.1 P0. |
| OD-06 | Remaining review findings are fixed as recommended. | Change log C6–C9: coverage numbers, dependency graph, this record, native goldens, status line, matrix nulls, typo. |
| OD-07 | "A manual entry should have a stop loss attached to it automatically instead of waiting for a trade to get accepted then closing immediately if the broker does not confirm." | §7.4.3: stop (and TP) sent inside the opening order, as the adapters already do; pre-send validation; re-attach before any close. |
| OD-08 | "Adding to a winning manual trade should just work the same as entering a new trade." | §7.4.6: same flow as entry; risk judged on the position family. Resolves former OQ-04. |
| OD-09 | "There should be a feature to switch a manual trade to auto." | §7.4.7 Hand to VAN (Protect and manage / Adopt by a strategy) and Take back. |
| OD-10 | "Add positions to a winning auto trade manually, governed by the trade's risk profile." | §7.4.6: owner-requested add under that trade's strategy budget, scale policy, family envelope and temperament. |
| OD-11 | "The news feature needs more than one live news feed source and comprehensive analysis and history comparison that actually influences trading decisions." | §8: minimum independent sources per category with cross-checking and health; story analysis; headline episodes and history profiles; decision paths D1–D7. |
| OD-12 | "Your revised blueprint should have the news bundle that allows live news trading in real time." | §8.10 live news trading bundle: feeds, armed plans, unscheduled-headline classes, owner armed tickets, latency ledger, staged promotion. |
| OD-13 | "Wait for both sources to agree before entering." (answers OQ-10) | §8.10.3: armed plans enter only when the official figure and the second source both arrive and agree; otherwise the plan stands down. |
| OD-14 | "Add all six to the blueprint" (the candidates from the Vibe-Trading / FinceptTerminal audit) | §7.4.12 behaviour diagnostics, §7.4.13 pattern extraction, §8.2/§8.4 prediction markets, §8.3 attention detectors and keyword watchlists, §8.2 additional RSS, §18.1 research integrity tests. Native reimplementations; no external code adopted (DEC-039). |
| OD-15 | "Review this REA analysis of MT5 and TradingView and use it to improve VAN's trading system and the Android app." | §7.8 trading workstation architecture (shared market projection, two chart budgets with a renderer-independent contract, bridge rules, saved indicators/drawings, replay, order vocabulary, chart observations, alerts, watchlists/screener); review in `research/VAN_REA_REVIEW_20261015.md`. |

## Open owner decisions

| ID | Question | Needed before |
|---|---|---|
| OQ-01 | Risk budget for `owner.manual` in the next signed mandate | DU-28 live use |
| OQ-02 | Stop-distance ATR multiples per instrument class for `ManualStopPolicy` | DU-28 implementation |
| OQ-03 | Demo period before `LIMITED_LIVE` manual trading | DU-28 live use |
| OQ-05 | Signature of this record | DU-02 golden freeze |
| OQ-06 | Which news, wire and calendar providers to license (vendor review of cost, latency, licence terms) | DU-14a |
| OQ-07 | Whether the stop re-attach sequence (§7.4.3) also replaces the router's immediate flatten-and-halt for automated trades | DU-28 |
| OQ-08 | Promotion of each news decision path D1–D6 from shadow to live, on its shadow evidence | DU-14c, per path |
| OQ-11 | Feed bundle selection and monthly budget (about $85 minimum, $230–650 full, §8.10.2) | DU-14a / DU-14e |
| OQ-12 | `event.*` strategy budget, daily news-loss cap and first event classes to paper-trade | DU-14e |
| OQ-13 | Soft-notice wording and thresholds for behaviour diagnostics (§7.4.12) | DU-28c |
| OQ-14 | Chart workstation renderer (extend native canvas, new native engine, or qualified web engine), chosen from S24 measurements | DU-10 |
| OQ-09 | Whether news may ever *directly* increase risk (recommended: no; news creates trades only through validated event strategies, D7) | DU-14c |
