# VAN Next — Blueprint Rev 1.8 Freeze List

**Status:** `AWAITING_OWNER_DECISION`. The blueprint is frozen when every item below is `DONE` or `OWNER_ACCEPTED`. After the freeze, it changes only by a numbered amendment. Each amendment regenerates the development plan (`plan/generate_plan.py`), and any packet in progress stops if the amendment affects its contract.

Rev 1.8 records the owner's answers D1–D5 (OD-18…OD-22). D6 is still open as OQ-18.

## A. Items already closed (re-derivable)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| A1 | No implementation on the rebuild branch ahead of the plan | DONE | Chart engine on `spike/van-next-chart-engine-20261015` only. The harness on the rebuild branch gave 106 suites, 986 tests, 0 failures (pre-engine baseline). |
| A2 | Every requirement maps to a DU in the dependency graph | DONE | `generate_plan.py --check`: 60 requirements, 0 findings |
| A3 | Every DU has at least one requirement | DONE | Generator: "DUs with no requirement row: none" |
| A4 | Dependency graph is acyclic; no DU depends on a later phase | DONE | 49 DUs, 83 edges, 0 findings |
| A5 | Every open question is assigned to a packet, as blocking its start, its live promotion or its exit | DONE | Plan §4, last column; 18 questions |
| A6 | The checks are known to work | DONE | `--selftest` catches each of 5 deliberately broken inputs |
| A7 | The plan is reproducible | DONE | Two consecutive runs produce identical output (MD5 below) |
| A8 | The Rev 2 pack is reconciled | DONE | OD-18…OD-22 recorded. Pack strengths imported (§7.9.0, §7.9.1, §7.9.12, §7.10, §7.8.6, §7.5, §15). Reviewed contracts in `contracts/`, with their naming conflicts resolved. |
| A9 | Trading modes are evidenced, not assumed | DONE | PR #92 `923ecf9`: 177 passed versus 155 on `main` for the same suites. The AGGRESSIVE no-evidence rule was broken deliberately and the expected test failed. |

## B. Owner decisions needed to freeze

| # | Decision | Recommendation |
|---|---|---|
| B1 | Approve the plan-level choices: the phase and lane of each DU, and the five vertical slices (plan §3). The new units DU-29c and DU-30 are in the Trading lane. | Approve |
| B2 | Approve the packet rules (plan §1). | Approve |
| B3 | Sign the decision record (OQ-05). | Sign at freeze, before PKT-001 |
| B4 | Accept the known limitations carried into development (blueprint §20.2). | Accept |
| B5 | Keep the chart spike as reference only, reviewed against the DU-10 contract when PKT-024 opens. | Keep |
| B6 | Answer D6 (OQ-18): quarantine `feature/rea-trading-accounts-tactile-20261015` (`3b2c9e04`) in the same way, reviewed only when PKT-007 opens. | Quarantine |

## C. Open questions — not blocking the freeze, each gated in the plan

| Question | Gates | Packet |
|---|---|---|
| OQ-05 signature | P0 exit (recommended earlier, see B3) | PKT-002 |
| OQ-15 deletion grace period; OQ-18 quarantine of the account branch | start | PKT-007 |
| OQ-20 trading-mode percentages and evidence thresholds | live use | PKT-008 / PKT-030 |
| OQ-06 news providers; OQ-11 feed budget | start | PKT-009 |
| OQ-16 base currency | start | PKT-010 |
| OQ-02 ATR multiples; OQ-07 stop re-attach for automated trades | start | PKT-012 |
| OQ-01 manual risk budget; OQ-03 demo period | live use | PKT-012 / PKT-034 |
| OQ-09 news directly increasing risk | start | PKT-013 |
| OQ-08 per-path live promotion | live | PKT-013 / PKT-036 |
| OQ-14 renderer choice | start | PKT-024 |
| OQ-19 first admitted funds provider | start | PKT-035 |
| OQ-13 soft-notice thresholds | start | PKT-042 |
| OQ-12 news budget and first event classes | start | PKT-044 |
| OQ-17 replay practice trades | start | PKT-061 |

## D. First packet after the freeze

**PKT-001 — DU-00 Consolidation, Feature Ledger, parity oracle** (blueprint §12.5, §12.7).

PR #92 (trading modes) is one of the candidate branches it classifies. The first action is to write PKT-001's acceptance contract for your approval. No consolidation work starts before that approval.

Plan MD5 at this revision: `71a22b1c…` (re-derive with `python3 plan/generate_plan.py && md5sum plan/VAN_NEXT_DEVELOPMENT_PLAN_REV1.md`).
