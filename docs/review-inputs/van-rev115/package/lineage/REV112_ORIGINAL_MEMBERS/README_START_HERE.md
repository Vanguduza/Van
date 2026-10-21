# VAN Next — Rev1.12 reviewed adoption integration

**State:** owner-directed specification integration; independent semantic/F15 admission pending; no application implementation, live deployment or financial authority is claimed.

The active master is `VAN_NEXT_UNIFIED_REBUILD_BLUEPRINT_REV1_12_20261017.md`; the only execution plan is `plan/DEVELOPMENT_PLAN.json`. Old plans are lineage.

| Scope | Generated count |
|---|---:|
| requirements | 237 |
| nodes | 131 |
| backend | 82 |
| backend_verification | 12 |
| surfaces | 234 |
| actions | 349 |
| atoms | 171 |
| features | 93 |
| truth | 18 |
| forecast_aliases | 48 |
| tests | 1287 |

**BG-001:** VAN-PKT-098; **first new UX:** VAN-PKT-099. Unit IDs are stable; sequence-based packet IDs changed and must always be revision-qualified. `traceability/REV111_PACKET_CROSSWALK.json` maps all 121 old units.

## Read in this order

1. Master §30 and the retained full product/forecast chapters.
2. `contracts/HIGH_VALUE_INTEGRATION_CONTRACTS.md`, the source/adoption/review crosswalks and exact producer/consumer contracts.
3. Generated full plan and test registry, followed by `OPUS_CONTINUATION_HANDOFF.md`.

New read-only services are BE-037–044; independent verifiers BQ-008/009. Existing 90 forecast requirements, 20 corrective contracts, 77 Opus and 18 backend-first requirements remain intact. Twelve new principal schemas supplement the 18 unchanged forecast schemas. All application tests are NOT_RUN.

## Verification boundary

Run the reproducible document scripts described in `verification/README.md`. Document/schema tests are not tests of VAN, Qlib, a chain provider, calibration accuracy or profitability. Actual source/economic/provider/device validation remains in the plan. Historical receipts moved to `lineage/rev1_11/evidence`. Current receipt files explicitly identify their scope and environment. No F15 or BG certificate is issued.


## Rev1.12 delivery verification boundary

The current local document checks validated the enlarged canonical structure (52/52 adversarial mutations), exact preservation of all inherited parent files/objects (13 check groups; 17/17 mutations), twelve new schemas/examples (67/67 schema/semantic mutations), the eighteen retained forecast schemas (38/38 mutations), and unchanged news-readiness rules (12/12 mutations). The exact exported 131-node graph was also rebuilt and verified on actual `van-trading-core`; its SHA-256 matches the delivered export and 18/18 graph counterexamples were caught. These tests cover the documents and synthetic fixtures, not the application or a live provider.

All **1,287 application acceptance contracts remain NOT_RUN**. Existing source defects are specified for repair but not repaired by this delivery. No F15, BG-001, model promotion, provider qualification or financial authority is issued. The owner direction admits proceeding with the reviewed specification scope; formal independent preparation and any required signatures remain separate. Exact evidence: `evidence/REV112_VERIFICATION_SUMMARY.json` and `evidence/REV112_GRAPH_VM_RECEIPT.json`.
