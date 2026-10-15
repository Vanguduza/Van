# VAN Next — Owner Decision Record, Rev 1

**Record ID:** `VAN-NEXT-OD-REV1-20261015`
**Status:** `RECORDED_FROM_OWNER_CHAT / AWAITING_OWNER_SIGNATURE`
**Recorded:** 15 October 2026, from the owner's instructions in a Claude Code session reviewing `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_20261015.md`.
**Applies to:** `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_1_20261015.md` and its companion matrix.

Under the VAN Project Truth Protocol an owner-signed, device-authenticated instruction outranks this record. These decisions bind development packets once the owner signs this record (blueprint §2.1, §17 F0). Until then they are the owner's stated intent, and no trading mandate, live permission or production change follows from them.

| ID | Decision (owner's words, condensed) | Effect in Rev 1.1 |
|---|---|---|
| OD-00 | The two dark/light screenshots are the visual authority (prior instruction). | Locked originals kept unaltered in `reference/` with their SHA-256 hashes. |
| OD-01 | "A setup that allows manual trade entries or exits that are governed by the system's risk profiles, where manual entries will also have strict automated stop losses and optional take profits." | Blueprint §0.2 item 11 and §7.4; DU-28; requirement VAN-NX-027. Four sub-decisions still open (§7.4.9). |
| OD-02 | "Change the mockup labels to match the system." | §2.6 label table; relabelled references `reference/*_RELABELLED_REV1_1_20261015.png`; visual delta VD-01. |
| OD-03 | The five Trading Home entry points (Markets, Watchlist, Potential trades, Chart, Intelligence) were requested by the owner. | Recorded as visual delta VD-02, not drift. |
| OD-04 | "Change the news plan to match the code and make improvements to ensure news analysis is provided in simple terms and how it translates to trades." | §8 rebuilt on `news_ingress`; News briefs with a deterministic trade-effect table. |
| OD-05 | Repository consolidation is a priority, so the new build does not silently thin or omit features and functions that are documented or meant to be ported from the old build; it must also stop pollution of the new frontend UX/UI. | §0.2 item 12, §12.5 (DU-00 first), §12.6 module isolation, §19.1 P0. |
| OD-06 | Remaining review findings are fixed as recommended. | Change log C6–C9: coverage numbers, dependency graph, this record, native goldens, status line, matrix nulls, typo. |

## Open owner decisions

| ID | Question | Needed before |
|---|---|---|
| OQ-01 | Risk budget for `owner.manual` in the next signed mandate | DU-28 live use |
| OQ-02 | Stop-distance ATR multiples per instrument class for `ManualStopPolicy` | DU-28 implementation |
| OQ-03 | Demo period before `LIMITED_LIVE` manual trading | DU-28 live use |
| OQ-04 | Whether manual adds to an open winning position are allowed | DU-28 implementation |
| OQ-05 | Signature of this record | DU-02 golden freeze |
