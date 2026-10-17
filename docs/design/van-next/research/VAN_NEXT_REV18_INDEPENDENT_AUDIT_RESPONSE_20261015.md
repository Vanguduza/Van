# Response to the independent Rev 1.8 vs Rev 2 audit

**Audit archive:** `VAN_NEXT_REV18_VS_REV2_INDEPENDENT_AUDIT_20261015.zip`, SHA-256 `3a7300e7c1b3256da659d488e157f9997e4b5523581b7adc0665b1ba1e349e64`. It contains 22 findings, AUD-01…AUD-22, all graded `DOCUMENTARY_STATIC`.

**Method:** each claim was checked against this repository before it was adopted. The auditor did not have the generator, the decision record or `contracts/`.

**Result:** every finding tested was confirmed. Rev 1.9 applies them, together with owner decisions E1–E5 (OD-23…OD-27).

| Finding | Verified how | Result | Rev 1.9 change |
|---|---|---|---|
| AUD-01 BLOCKER: six units cut off from qualification | Ancestor walk over the §16.2 DAG | **Confirmed**: DU-10b, DU-10c, DU-10d, DU-12, DU-12b, DU-29b. The plan validator had no reachability rule. | Six edges into DU-25. A new validator rule reports exactly these six on the Rev 1.8 inputs and none on Rev 1.9, and a self-test proves it. |
| AUD-02 BLOCKER: "cancelled, not filled" | Read §7.4.5 | **Confirmed**: a broker can fill a resting order before a cancellation arrives | §7.4.5 rewritten: worst-case reservation, cancellation before fill, reconciliation of an unexpected fill, race tests |
| AUD-03 BLOCKER: inherited state machines not closed | New model checker run on the pack's `STATE_MACHINES.json` | **Confirmed and worse**: 69 findings. Beyond the audit's list, `MODIFY_PENDING`, `RESTRICTED` and `UNLINK_BLOCKED` are dead ends, and order `EXPIRED` and deposit `REJECTED`/`FAILED`/`EXPIRED` are unreachable. | `contracts/VAN_STATE_MACHINES_REV1_9.json` (6 machines) with 0 findings. `check_state_machines.py --selftest` catches 8 of 8. The checker also caught three gaps in my own first draft (returns to "linked" without a broker readback). |
| AUD-04 BLOCKER: one-tap news ticket authority | Read §8.10.5 and §7.4.1 | Confirmed | `NewsArmedTicketGrant` plus a state machine; both sources must agree (OD-24) |
| AUD-05 HIGH: warning versus block | §7.9.5 against §7.9.12 | **Confirmed** contradiction | Server-side refusal; `REFUSED_MARGIN` state |
| AUD-06 HIGH: "unmanaged by VAN" | §7.9.4 | Confirmed | Removed (OD-25) |
| AUD-07 HIGH: no Rev 2 crosswalk | Repository search | Confirmed | `crosswalk/`: 18 product truths and 93 features reviewed; the 171 atoms go to DU-01 (OD-27) |
| AUD-08 HIGH: TCA and Risk Command Centre under-specified | §7.4–§7.5 | Confirmed | VAN-NX-061, VAN-NX-062 |
| AUD-09 HIGH: VAN-NX-026 has no packet | Requirement scan | **Confirmed** | VAN-NX-026 moved to DU-01 as a research-input admission record |
| AUD-10 HIGH: cancelled deletion restoring credentials | §7.9.4 | Confirmed | `RELINK_REQUIRED`; the checker forbids a direct return to "linked" |
| AUD-11 HIGH: "probability" ban | §2.6 against §8.4 and §7.4.13 | **Confirmed** conflict | Lint narrowed to uncalibrated certainty wording |
| AUD-12 HIGH: `DEMO / NOT LIVE` check | §12.6 | Confirmed | Check moved to fixture provenance; real demo badges allowed |
| AUD-13 MEDIUM: plan digest not reproducible | Recomputed | **Confirmed, and worse**: the committed Rev 1.8 plan was **stale**. The blueprint was edited after generation; recomputed `679c657d…` against recorded `4367690e…`. Packets were unaffected. | Full per-file SHA-256 values in `plan/PLAN_INPUT_PROVENANCE.json`; `--check` now fails on a stale plan, and a self-test proves it |
| AUD-14 MEDIUM: stale references | grep | Confirmed ("68 packets", "PKT-023", REA status) | Fixed. The blueprint now refers to packets by DU, and plan §7 generates open-question packet numbers. |
| AUD-15 MEDIUM: OQ-05 timing | Freeze list against plan | Confirmed | Signed before PKT-001 (OD-26); now a PKT-001 start gate |
| AUD-16 MEDIUM: nine partial features | Crosswalk review | Confirmed | VAN-NX-061…069 |
| AUD-17 MEDIUM: v1→v2 account API | §7.9.12 | Confirmed | Compatibility-bridge obligations added |
| AUD-18 MEDIUM: latency and cost provisional | §8.10 | Confirmed | Marked as vendor research estimates |
| AUD-19 MEDIUM: `WORKING` versus `PLACED` | §7.8.6 | **Confirmed**: both appear | `PLACED` in code, *Working* on screen; adapters map raw states |
| AUD-20 MEDIUM: branch candidates | Freeze list | Agreed. The PR #92 test counts the auditor could not reproduce were reproduced in this repository (177 versus 155). | B5/B6: `REFERENCE_ONLY / QUARANTINED_UNQUALIFIED` |
| AUD-21 MEDIUM: averaging down | §7.4.6 against OD-08/OD-10/OD-21 and `HARD_FORBIDDEN_BEHAVIOURS` on `main` | **Confirmed, and it was my error**: §7.4.6 extended "adding to a winning trade" to losing trades | Adds only to winning trades (OD-23); anti-martingale tests |
| AUD-22 MEDIUM: "DONE" overstated | Freeze list | Agreed | Renamed `PREPARATION_VERIFIED`, with an explicit statement of what it is not |

The audit's two seed crosswalks were reviewed row by row; 14 rows were corrected or completed. The 171-atom seed is kept unreviewed as DU-01 input (`crosswalk/README.md`).
