# VAN Next — Blueprint Rev 1.9 Freeze List

**Status:** `AWAITING_OWNER_DECISION`. The blueprint is frozen when every item below is `PREPARATION_VERIFIED` or `OWNER_ACCEPTED`. After the freeze, it changes only by a numbered amendment, which regenerates the development plan. Any packet in progress stops if the amendment affects its contract.

Rev 1.9 applies the independent audit (AUD-01…AUD-22) and the owner's answers E1–E5 (OD-23…OD-27).

**What `PREPARATION_VERIFIED` means** (AUD-22): the claim was re-derived by a command anyone can rerun from the repository. It is **not** a DIAL F0–F15 gate result, an independent verifier receipt, owner-signed Product Truth or device proof. F15 stays `NOT_ISSUED`.

## A. Preparation checks (anyone can rerun)

| # | Criterion | Status | Command and result |
|---|---|---|---|
| A1 | No implementation on the rebuild branch ahead of the plan | PREPARATION_VERIFIED | Chart engine only on `spike/van-next-chart-engine-20261015`; the harness on this branch gave 106 suites, 986 tests, 0 failures (pre-engine baseline) |
| A2 | Inputs valid: DAG acyclic, every requirement and open question mapped, no phase inversion | PREPARATION_VERIFIED | `python3 plan/generate_plan.py --check` → 0 findings (49 DUs, 89 edges, 69 requirements, 18 questions) |
| A3 | **Every build unit reaches integrated verification, S24 acceptance and rollout** (AUD-01) | PREPARATION_VERIFIED | Same check. Run against the Rev 1.8 inputs, it reports exactly DU-10b, DU-10c, DU-10d, DU-12, DU-12b and DU-29b; on Rev 1.9 it reports none |
| A4 | The committed plan is current, not stale (AUD-13) | PREPARATION_VERIFIED | `--check` regenerates the plan and compares it with the committed file. Full input SHA-256 values are in `plan/PLAN_INPUT_PROVENANCE.json` |
| A5 | The plan checks are known to work | PREPARATION_VERIFIED | `python3 plan/generate_plan.py --selftest` → 7 of 7 broken inputs caught (cycle, unknown DU in a requirement or question, missing lane, phase inversion, unit cut off from qualification, stale plan) |
| A6 | **State machines closed** (AUD-03, AUD-05, AUD-10, AUD-19; OD-24, OD-25) | PREPARATION_VERIFIED | `python3 contracts/check_state_machines.py` → 0 findings on `VAN_STATE_MACHINES_REV1_9.json` (69 findings on the pack's original). `--selftest` → 8 of 8 broken inputs caught |
| A7 | The Rev 2 product truths and features are mapped (OD-27) | PREPARATION_VERIFIED | `crosswalk/`: 18 of 18 product truths and 93 of 93 features, 0 dangling references; the 171-atom mapping is a DU-01 obligation |
| A8 | The plan is reproducible | PREPARATION_VERIFIED | Two consecutive runs are byte-identical; plan MD5 `1549922d…` |
| A9 | Trading modes evidenced | PREPARATION_VERIFIED | PR #92 `923ecf9`: 177 passed versus 155 on `main` for the same suites; the AGGRESSIVE no-evidence rule was broken deliberately and the expected test failed (this repository, 15 October) |

## B. Owner decisions needed to freeze

| # | Decision | Recommendation |
|---|---|---|
| B1 | Approve the plan-level choices: phase and lane per DU, and the five vertical slices (plan §3) | Approve |
| B2 | Approve the packet rules (plan §1) | Approve |
| B3 | **Sign the decision record before PKT-001** (OD-26). It is now a start gate of PKT-001 in the plan | Sign |
| B4 | Accept the known limitations (blueprint §20.2): REA is static only, with no live Android trial; no device receipts; PR #93 unmaterialised paths remain | Accept |
| B5 | Chart spike `spike/van-next-chart-engine-20261015` (`30bc2d0`): `REFERENCE_ONLY / QUARANTINED_UNQUALIFIED`. It qualifies nothing until the DU-10 contract exists | Keep quarantined |
| B6 | OQ-18: `feature/rea-trading-accounts-tactile-20261015` (`3b2c9e04`), same disposition, until the DU-29 contract exists | Quarantine |

## C. Open questions

Each is gated at a specific packet. They are generated, with current packet numbers, in **plan §7 "Open questions by packet"**, so this list no longer copies packet numbers that can go stale.

## D. First packet after the freeze

**PKT-001 — DU-00 Consolidation, Feature Ledger, parity oracle.** Its start gates are the signed decision record (OQ-05) and its own acceptance contract, approved by you. The first action is to write that contract. No consolidation work starts before your approval.
