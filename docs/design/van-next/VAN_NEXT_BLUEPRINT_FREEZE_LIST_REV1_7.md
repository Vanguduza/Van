# VAN Next — Blueprint Rev 1.7 Freeze List

**Status:** `AWAITING_OWNER_DECISION`. The blueprint is frozen when every item below is `DONE` or `OWNER_ACCEPTED`. After the freeze, it changes only by a numbered amendment. Each amendment regenerates the development plan (`plan/generate_plan.py`), and any packet in progress stops if the amendment affects its contract.

## A. Items already closed (re-derivable)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| A1 | No implementation on the rebuild branch ahead of the plan | DONE | Chart engine moved to `spike/van-next-chart-engine-20261015` (`30bc2d0`). Harness on the rebuild branch: 106 suites, 986 tests, 0 failures, equal to the pre-engine baseline. |
| A2 | Every requirement maps to a DU in the dependency graph | DONE | `generate_plan.py --check`: 54 requirements, 0 findings |
| A3 | Every DU has at least one requirement | DONE | VAN-NX-053 (DU-01) and VAN-NX-054 (DU-MR) added from the existing §17 F0 and §19.1 text |
| A4 | Dependency graph is acyclic; no DU depends on a later phase | DONE | `--check`: 47 DUs, 77 edges, 0 findings |
| A5 | Every open question is assigned to a packet, as blocking its start, its live promotion or its exit | DONE | Plan §4, last column |
| A6 | The checks are known to work | DONE | `--selftest` catches each of 5 deliberately broken inputs: cycle, unknown DU in a requirement, unknown DU in a question, DU without a lane, phase inversion |
| A7 | The plan is reproducible | DONE | Two consecutive runs produce identical output (MD5 `cf350ebb…`) |

## B. Owner decisions needed to freeze

| # | Decision | Recommendation |
|---|---|---|
| B1 | Approve the plan-level choices: the phase and lane of each DU, and the five vertical slices (plan §3). These are the only plan inputs not taken from the blueprint. | Approve as drafted. They follow §19.1 and §16.3; the only interpretation is placing DU-04 (app shell) in P1, so the slices have a shell to run in. |
| B2 | Approve the packet rules (plan §1): one packet at a time; the contract is approved before any code; new gates are broken on purpose before being trusted; no `FEATURE_LOSS`; no code outside a packet. | Approve. |
| B3 | Sign the decision record (OQ-05). §19.1 requires it by the end of P0. | Sign at freeze, before PKT-001, so that OD-00…OD-17 bind every packet from the start. |
| B4 | Accept the known limitations carried into development (blueprint §20.2). These include: the REA evidence is static only; TradingView was analysed from a non-store copy; PR #93's unmaterialised paths still need continuation; and no current S24 build receipt exists. | Accept. Each limitation is owned by the packet that needs it closed. |
| B5 | Decide what happens to the chart spike. | Keep it as reference only. It is reviewed against the DU-10 contract when PKT-023 opens, and never merged as is. |

## C. Open questions — not blocking the freeze, each gated in the plan

| Question | Gates | Packet |
|---|---|---|
| OQ-05 signature | P0 exit (recommended earlier, see B3) | PKT-002 |
| OQ-15 deletion grace period | start | PKT-007 |
| OQ-06 news providers, OQ-11 feed budget | start | PKT-008 |
| OQ-16 base currency | start | PKT-009 |
| OQ-02 ATR multiples, OQ-07 stop re-attach for automated trades | start | PKT-011 |
| OQ-01 manual risk budget, OQ-03 demo period | live use | PKT-011 / PKT-032 |
| OQ-09 news directly increasing risk | start | PKT-012 |
| OQ-08 per-path live promotion | live | PKT-012 / PKT-033 |
| OQ-14 renderer choice | start | PKT-023 |
| OQ-13 soft-notice thresholds | start | PKT-039 |
| OQ-12 news budget and first event classes | start | PKT-041 |
| OQ-17 replay practice trades | start | PKT-058 |

## D. First packet after the freeze

**PKT-001 — DU-00 Consolidation, Feature Ledger, parity oracle** (blueprint §12.5, §12.7).

The first action is to write its acceptance contract (§16.4 fields) for your approval. No consolidation work starts before that approval.
