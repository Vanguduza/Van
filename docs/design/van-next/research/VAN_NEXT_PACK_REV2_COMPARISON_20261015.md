# VAN Next — comparison of the Rev 2 "Quantum" pack with blueprint Rev 1.7

**Date:** 15 October 2026

**Inputs:**
- The owner-supplied `VAN_NEXT_QUANTUM_BLUEPRINT_PACK_REV2_20261015.zip`: 59 files, including a 138 KB master blueprint and 30 registries.
- `VAN_TACTILE_SPATIAL_REDESIGN_BLUEPRINT_REV1_7_20261015.md` with its decision record, development plan and freeze list.

**Method:** every number below comes from a command run on 15 October against these artefacts. The pack's own verifier was read before it was run (it is read-only and makes no network calls).

## 1. What each document is

| | Rev 2 pack | Rev 1.7 blueprint |
|---|---|---|
| Authority it claims | "Owner directive in this chat" plus the locked images. It never cites the OD-xx decision record. | `VAN_NEXT_OWNER_DECISIONS_REV1.md` (OD-00…OD-17, unsigned) plus the locked images |
| Owner product truths | 18 (VAN-PT-01…18), `PENDING_OWNER_REVIEW` | 17 recorded decisions plus 54 requirements (VAN-NX-001…054) |
| Machine registries | Features 93, requirements 171, surfaces 115, tests 202, development units 19, gates 16 | 78-surface matrix (CSV and JSON), requirements table, DAG; the plan is generated from them |
| Development order | Master §16.1 text (DU00–DU18) **and** a registry (VNX-DU-01…19); they disagree, see §3.3 | One DAG (§16.2); 68 packets derived mechanically, with a self-tested validator |
| Build-ready claim | Explicitly `NOT_ISSUED` | Explicitly not build-ready; freeze awaits owner decisions B1–B5 |

Both documents put consolidation and reconciliation first, then design authority, then domains, then qualification. Both quarantine work done out of order: the pack names `feature/rea-trading-accounts-tactile-20261015`, Rev 1.7 names `spike/van-next-chart-engine-20261015`. The two plans agree in direction. They differ in content and in rigour.

## 2. Where the pack is stronger, and Rev 1.7 should adopt it

| # | Pack content | Rev 1.7 today | Recommendation |
|---|---|---|---|
| P1 | **Accounts & Funds inside the app** (PT-10, §5): creation, linking, editing, credential rotation, unlink, remote closure, deposit, withdrawal, transfer, history and KYC. Every operation is gated by the provider's actual capability, with an honest hosted-flow fallback. | §7.9.5 says "VAN never moves money (§0.3)". **That is my error:** §0.3 only says the *design document* authorises no live fund movement. I added "never moves money" in Rev 1.6 and attributed it to §0.3, which turned it into a product decision you never made. Your OD-16 asked me to study funding. | Remove the claim. Adopt the pack's model, subject to the owner confirming in-app funding (D1). |
| P2 | **Six ownership planes** (§5.1): broker identity, local link, execution, money movement, balances, analytics. Plus Account ≠ Wallet ≠ Payment Method ≠ Transaction ≠ Mandate ≠ Session. | Partly implied | Adopt as §7.9.0 |
| P3 | **Canonical financial models** (§5.2): `ProviderCapability`, `PaymentIntent` with idempotency key, `FinancialMovement`, `AccountClosureIntent`. Money is held in integer minor units, never floating point. | No money-type rule (0 matches for "integer minor" / "floating point") | Adopt |
| P4 | **Funds state machine** (§5.6), DRAFT → … → SETTLED, where a timeout after submission becomes `OUTCOME_UNKNOWN` and never triggers a second payment. Linking is separate from broker registration; unlinking is separate from broker closure. | Account lifecycle only (§7.9.1) | Adopt |
| P5 | **Fresh capability check** before showing an enabled money button and again at submission (§5.5) | Capability matrix exists, without the fresh-check rule | Adopt |
| P6 | **Unified order states** (§8.1), including `CANCEL_PENDING`, `OUTCOME_UNKNOWN` and `RECONCILIATION_REQUIRED` | §7.8.6 order vocabulary, comparable | Align the names |
| P7 | **History separates cash flow from trading P&L** ("funding must not be mistaken for profit", §8.2) | F-033 flow-adjusted drawdown (§7.9.5) | Same intent; keep both |
| P8 | **Five bottom destinations** Home / Trade / Work / Memory / More (§4.1), with a per-zone first-fold table | Navigation in §4; less explicit | Compare against the locked artboards and adopt if they match |
| P9 | **Normal / Risky / Aggressive trading modes** (PT-17, §8.3): quality-aware, never above the mandate ceiling | Mentions PR #92 temperaments only | **Needs owner confirmation** (D3). The pack cites a "user trading-mode clarification" that does not appear in my record. |
| P10 | **Device scope:** process-death restore, tablet, landscape, split-screen, dynamic type (PT-16) | Partly covered | Adopt into §15 |

## 3. Where Rev 1.7 is stronger, and the pack is missing or contradicts your decisions

### 3.1 Owner decisions absent from the pack

These are counts of matches in the pack's master blueprint:

| Your decision | Pack |
|---|---|
| OD-01, OD-07: manual trading with the stop inside the opening order, optional TP, governed by risk profiles | 0 matches for manual trading, attached stop or bracket |
| OD-08, OD-10: manual adds, including adding to an auto trade under its risk profile | **Contradicted:** §8.2 allows `ADD` only "if VATI proposes and authorizes" |
| OD-09: switch a manual trade to auto ("Hand to VAN") | 0 matches |
| OD-11, OD-12: several live news sources and a live news-trading bundle (armed plans, latency ledger) | 0 matches for news trading, armed plan or squawk |
| OD-13: wait for both sources to agree before entering | 0 matches |
| OD-14: the six audit features (behaviour diagnostics, pattern extraction, prediction markets, attention detectors, extra RSS, research-integrity tests) | 0 matches for diagnostics, pattern extraction and prediction markets |
| OD-02: mockup labels follow the system vocabulary ("Potential trades", no "probability") | **Contradicted:** uses "Opportunities" 10 times |
| F-033: a withdrawal read as drawdown (reproduced defect) | Not identified as a defect |
| OD-05, §12.5: consolidation Feature Ledger and parity oracle that fails the build on feature loss | 0 matches; the pack's PT-14 states the principle without the gate |
| OD-17: the 39 REA records read; account and chart findings A1–A10 | The pack lists the records as "indexed externally" |

### 3.2 Registry content is largely templated

| Probe | Result |
|---|---|
| Requirements: distinct acceptance texts | **95 of 171.** 93 requirements are one generated "derived capability" per feature. |
| Tests: distinct assertion texts | **95 of 202** |
| Requirements referenced directly by any test | 60 of 171 (tests point at features) |
| Implementation DAG deliverables | Identical boilerplate in every packet |
| Pack verifier | Passes, but it hard-codes the counts it expects (18, 93, 171…). It does not check requirement→test coverage or that each feature is owned by a unit. |

### 3.3 The development order is not deterministic

- **Overlapping units.** Every feature belongs to between 2 and 8 development units, and four units (VNX-DU-01, 04, 18, 19) each list all 93 features. No single unit owns a feature, so "feature X is done" can't be attributed to one packet.
- **Two orders that disagree.** The master text's DU00–DU18 differ from the registry's VNX-DU-01…19 in titles and order. For example, the master puts funds (DU08) before markets (DU09), while the registry puts accounts (DU-12) after orders (DU-11). The master says the registry governs.
- **A missing branch head.** The baseline register records `feature/rea-trading-accounts-tactile-20261015` with `head_sha: null`. The branch exists on the remote at `3b2c9e04`.

Rev 1.7's generated plan has one DAG and one order key, rejects broken inputs (self-tested), and gives each DU its own packet.

## 4. Recommendation

Run one blueprint, not two. Use **Rev 1.7 as the base**, because it carries your recorded decisions, the consolidation gate and a deterministic plan. Import the pack's stronger parts P1–P10 as **Rev 1.8**, then regenerate the plan. Keep the pack's contracts and schemas (`ACCOUNTS_FUNDS_TECHNICAL_CONTRACT.md`, `FUNDING_INTENT.schema.json`, `PROVENANCE_STATE_ENVELOPE.schema.json`, and the chart/orb/graph contracts) as appendices once reviewed. Do not adopt the pack's registries as they stand: they are templated and their unit membership overlaps.

## 5. Decisions needed from the owner

| # | Question |
|---|---|
| D1 | Should VAN orchestrate deposits, withdrawals and transfers in the app, through each provider's verified API or hosted flow, with settlement proven by broker readback (pack PT-10)? This replaces my unauthorised "never moves money". |
| D2 | Is Rev 1.7 the base, with the pack's P1–P10 imported as Rev 1.8? Or should the pack be the base, with your OD-01…OD-17 re-entered into it? |
| D3 | Do you want Normal / Risky / Aggressive trading modes (pack PT-17)? I have no record of that instruction. |
| D4 | Manual adds: confirm OD-08 and OD-10 (you may add, sized by the risk profile) over the pack's "only if VATI proposes". |
| D5 | Trading Home tile label: "Potential trades" (OD-02) or "Opportunities" (pack)? |
| D6 | `feature/rea-trading-accounts-tactile-20261015` (`3b2c9e04`): quarantine it alongside the chart spike, to be reviewed only when PKT-007 (DU-29) opens? |
