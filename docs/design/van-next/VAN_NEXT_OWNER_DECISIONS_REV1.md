# VAN Next — Owner Decision Record, Rev 1

**Record ID:** `VAN-NEXT-OD-REV1-20261015`
**Status:** `RECORDED_FROM_OWNER_CHAT / AWAITING_OWNER_SIGNATURE`
**Recorded:** 15 October 2026, from the owner's instructions in a Claude Code session reviewing `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_20261015.md`.
**Applies to:** `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_9A_20261016.md` and its companion matrix. OD-07…OD-31 were added on 15 October 2026 after the owner reviewed Rev 1.1.

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
| OD-16 | "Build a new chart engine that produces the best results from the research we've done… study how they handle accounts management (creation, deleting editing, funding and supporting different brokers) so that we have a comprehensive account management system for VAN as well." | §7.8.11 native chart engine built under `android/app/.../van/next/chart/` with JVM tests; §7.9 account management (lifecycle, broker adapters, funding ledger, flow-adjusted drawdown fixing F-033). The 39 original REA evidence records were not reachable at first; see OD-17. |
| OD-17 | "Use commander to access van trading core through dial admin or oracle-admin" | The 39 records were read through `dial-control` → `van-trading-core` (`dial-oracle-admin` key). The study (`research/VAN_REA_EVIDENCE_STUDY_39_RECORDS_20261015.md`) led to the engine extensions in §7.8.11 and account additions A1–A10 in §7.9.11. |
| OD-18 | D1: "yes" — VAN orchestrates deposits, withdrawals and transfers in the app, through each provider's verified API or hosted flow, settled only on broker readback. | §7.9.0, §7.9.5, §7.9.12; replaces Rev 1.6's unauthorised "VAN never moves money". |
| OD-19 | D2: "keep your blueprint as base and bring in the pack's stronger parts" | Rev 1.8 (Y1–Y7); `research/VAN_NEXT_PACK_REV2_COMPARISON_20261015.md`. |
| OD-20 | D3: "Yes I want trading modes, they should be documented or partially built inside the repo" | §7.10. Found on PR #92 (`923ecf9`) with design and tests; adopted through DU-00 consolidation and DU-30. |
| OD-21 | D4: "yes" — the owner may add to winning manual and automatic trades, sized by the trade's risk profile (OD-08, OD-10). | §7.4 unchanged; the pack's "ADD only if VATI proposes" is not adopted. |
| OD-22 | D5: "Potential trades" | §2.6 label confirmed over the pack's "Opportunities". |
| OD-23 | E1: "yes" — manual adds only to **winning** trades: in profit on a fresh quote, within the family's original risk budget. | §7.4.6; corrects Rev 1.5–1.8, which allowed adds to losing trades beyond the owner's words (AUD-21). |
| OD-24 | E2: "yes" — the one-tap news ticket also requires both sources to deliver and agree. | §8.10.5 `NewsArmedTicketGrant` (AUD-04). |
| OD-25 | E3: "yes" — no "unmanaged by VAN" escape; unlink and delete are blocked while positions, orders, in-flight funds or unknown outcomes exist. | §7.9.4 (AUD-06). |
| OD-26 | E4: "yes" — the decision record is signed before PKT-001. | OQ-05 now gates DU-00 start (AUD-15). |
| OD-27 | E5: "yes" — the 18 product truths and 93 features are mapped in Rev 1.9; the 171-atom mapping is DU-01's job. | `crosswalk/`, §16.1 (AUD-07). |
| OD-28 | F1: "yes" — apply the follow-up audit's contradiction fixes (V19-A03…A07, A09). | Rev 1.9a U3–U7, U9 |
| OD-29 | F2: "yes" — F13 is a predevelopment matrix; an independent F15 certificate is required before any code-bearing packet. | §17, DU-31 |
| OD-30 | F3: "yes" — DU-00 is split: read-only inventory → Product Truth (171/115) → F15 → code-bearing consolidation. | §12.5, §16.2 |
| OD-31 | F4: "yes" — a hash-pinned predevelopment evidence pack. | `evidence/` |

## Open owner decisions

| ID | Question | Needed before |
|---|---|---|
| OQ-01 | Risk budget for `owner.manual` in the next signed mandate | DU-28 live use |
| OQ-02 | Stop-distance ATR multiples per instrument class for `ManualStopPolicy` | DU-28 implementation |
| OQ-03 | Demo period before `LIMITED_LIVE` manual trading | DU-28 live use |
| OQ-05 | Signature of this record (OD-26: before PKT-001) | DU-00a start |
| OQ-06 | Which news, wire and calendar providers to license (vendor review of cost, latency, licence terms) | DU-14a |
| OQ-07 | Whether the stop re-attach sequence (§7.4.3) also replaces the router's immediate flatten-and-halt for automated trades | DU-28 |
| OQ-08 | Promotion of each news decision path D1–D6 from shadow to live, on its shadow evidence | DU-14c, per path |
| OQ-11 | Feed bundle selection and monthly budget (about $85 minimum, $230–650 full, §8.10.2) | DU-14a / DU-14e |
| OQ-12 | `event.*` strategy budget, daily news-loss cap and first event classes to paper-trade | DU-14e |
| OQ-13 | Soft-notice wording and thresholds for behaviour diagnostics (§7.4.12) | DU-28c |
| OQ-14 | Chart workstation renderer. Narrowed by OD-16: the native engine is built; what stays open is whether it is enough on the S24 or a qualified web engine is still needed for the full workstation | DU-10 |
| OQ-15 | Grace period before a deleted account's records are purged (recommended 30 days, cancellable) | DU-29 |
| OQ-16 | Portfolio base currency for multi-account totals and funding reports | DU-29a |
| OQ-18 | D6: quarantine `feature/rea-trading-accounts-tactile-20261015` (`3b2c9e04`) alongside the chart spike, reviewed only when the account packet opens? (Unanswered.) | DU-29 |
| OQ-19 | Which provider is the first admitted funds rail (e.g. Deriv with `payment` scope), in sandbox or demo first | DU-29c |
| OQ-20 | Owner signature of the trading-mode percentages and the AGGRESSIVE evidence thresholds before any live use | DU-30 live use |
| OQ-17 | Whether chart replay may offer simulated practice trades (TradingView has this; VAN's engine currently refuses drafts in replay). Simulated only, never an order. | DU-10c |
| OQ-09 | Whether news may ever *directly* increase risk (recommended: no; news creates trades only through validated event strategies, D7) | DU-14c |
