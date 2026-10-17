# VAN Next — Blueprint Rev 1.9b Freeze List

**Status:** `AWAITING_OWNER_DECISION`. The blueprint is frozen when every item below is `PREPARATION_VERIFIED` or `OWNER_ACCEPTED`. After the freeze, it changes only by a numbered amendment, which regenerates the plan. Any packet in progress stops if the amendment affects its contract.

Rev 1.9b applies the forensic evidence audit NXA-01…NXA-07 and the owner's answers G1–G5 (OD-32…OD-36), plus continuous strategy development (OD-37, §7.4.14) and the trading-path corrections (OD-38, §7.4.15), on top of Rev 1.9a (V19-A01…A09, F1–F4).

**What `PREPARATION_VERIFIED` means:** the claim was re-derived by a command anyone can rerun. The commands and their recorded outputs are in `evidence/`, bound to a commit. It is **not** a DIAL F0–F15 PASS. **F15 is issued only by an independent verifier at DU-31** and stays `NOT_ISSUED` until then.

**Freezing the blueprint is not F15.** The freeze approves the design and the plan. F15 (PKT-003) comes later and certifies the completed predevelopment pack. That includes the 171/115 mapping, which is done in PKT-002.

## A. Preparation checks (anyone can rerun; receipts in `evidence/receipts/`)

| # | Criterion | Status | Command and result |
|---|---|---|---|
| A1 | No implementation on the rebuild branch ahead of the plan | PREPARATION_VERIFIED | Chart engine only on `spike/van-next-chart-engine-20261015`; harness on this branch 106 suites, 986 tests, 0 failures. **One owner-ordered exception (OD-38):** fixes to five defects in the existing VATI trading engine (`trading/`, commits `fbf3a5f`, `d985434`, `d6c5681`), not VAN Next rebuild code. Trading suite 1326 passed, 2 skipped, 1 failed (the mTLS round-trip test, which fails identically on the base commit). They reach `main` only by a pull request the owner approves |
| A2 | Inputs valid; every build unit reaches DU-25, DU-26 and DU-MR; no code-bearing unit before the F15 gate DU-31; every requirement's needed units built upstream; **every code-bearing unit downstream of the parity checker (DU-00b)**; **no duplicate IDs**; **requirements and the 78 surfaces' 349 owner actions match the owner-pinned lock** | PREPARATION_VERIFIED | `python3 plan/generate_plan.py --check` → 0 findings (51 DUs, 92 edges, 72 requirements, 18 questions, 78 surfaces) |
| A3 | The committed plan is current | PREPARATION_VERIFIED | Same command: it regenerates the plan and compares; full input SHA-256 values are in `plan/PLAN_INPUT_PROVENANCE.json` |
| A4 | The plan checks are known to work | PREPARATION_VERIFIED | `--selftest` → 23 of 23 broken inputs caught, including deleting the money requirement VAN-NX-055 and the visual requirement VAN-NX-004, a duplicated requirement, an edited lock, a dropped legacy owner action and a code unit outside the parity checker's reach |
| A5 | State machines closed **and equal to the owner-pinned approved transition list** | PREPARATION_VERIFIED | `python3 contracts/check_state_machines.py` → 0 findings (230 on the pack's original, which has no approved list); `--selftest` 24 of 24, including the auditor's four shortcuts (deposit, withdrawal, order, news) with real proof labels, the same shortcuts with the approved list edited, and duplicate machines, states and transitions |
| A6 | Rev 2 product truths and features mapped | PREPARATION_VERIFIED | `crosswalk/`: 18 of 18 and 93 of 93; the 171/115 mapping is PKT-002 (DU-01) and is required for F15 |
| A7 | The plan is reproducible | PREPARATION_VERIFIED | Byte-identical on rerun; plan MD5 `53cd7991…` |
| A8 | Trading modes evidenced | PREPARATION_VERIFIED | PR #92 `923ecf9`: 177 versus 155 passed; the AGGRESSIVE no-evidence gate was broken deliberately and the expected test failed |
| A9 | Evidence pack | PREPARATION_VERIFIED | `evidence/EVIDENCE_MANIFEST.json` records the source commit, the SHA-256 of every input and receipt, and what is deliberately absent |

## B. Owner decisions needed to freeze

| # | Decision | Recommendation |
|---|---|---|
| B1 | Approve the plan-level choices: phase and lane per DU, and the five vertical slices (plan §3) | Approve |
| B2 | Approve the packet rules (plan §1), including the F15 entry gate for code-bearing packets and the two-stage feature-preservation rule 3a | Approve |
| B3 | **Sign the decision record before PKT-001** (OD-26). PKT-001 is now the read-only inventory. Signing also approves the two pinned lock hashes (transition list, requirement lock) | Sign |
| B4 | Accept the known limitations (§20.2) | Accept |
| B5 | Chart spike (`30bc2d0`): `REFERENCE_ONLY / QUARANTINED_UNQUALIFIED` | Keep quarantined |
| B6 | OQ-18: `feature/rea-trading-accounts-tactile-20261015` (`3b2c9e04`), same disposition | Quarantine |

## C. Open questions

Generated with current packet numbers in **plan §7 "Open questions by packet"**.

## D. Sequence after the freeze

| Packet | Unit | Changes code? | Starts when |
|---|---|---|---|
| PKT-001 | DU-00a read-only inventory | No | Decision record signed (OQ-05) and the PKT-001 contract approved by you. Exit: preservation-inventory gate (plan rule 3a) |
| PKT-002 | DU-01 Product Truth, including the 171/115 mapping and REA research admission | No | PKT-001 exited and its contract approved |
| PKT-003 | DU-31 predevelopment closure | No | An independent verifier issues F15 `FORENSIC_BUILD_READY` |
| PKT-004 | DU-00b consolidation; builds and qualifies the parity checker | Yes | Only with F15 issued |
| PKT-005 onward | Everything else; each exit needs the parity checker green | Yes | PKT-004 exited |

The first action after the freeze is to write PKT-001's acceptance contract for your approval.
