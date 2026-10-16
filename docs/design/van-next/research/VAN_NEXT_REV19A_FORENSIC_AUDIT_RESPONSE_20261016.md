# Response to the Rev 1.9a forensic evidence audit

**Audit archive:** `VAN_NEXT_REV19A_FORENSIC_EVIDENCE_AUDIT_PACK_20261016.zip`, review ID `VAN-NEXT-REV19A-FORENSIC-20261016`, outcome `CONDITIONAL — evidence replay PASSED, F15-grade semantic validator assurance NOT YET QUALIFIED`. It audited the Rev 1.9a evidence pack (zip SHA-256 `3dfb6518…5648`, source commit `8ac8992`).

**Method:** the auditor's `adversarial_counterexample_replayer.py` was read in full, then run isolated (`python3 -I`, from outside its directory) against this branch at `34bc80d`. Every escape reproduced. Two more probes went beyond the auditor's: a requirement row deleted from the blueprint *text* (not just from the parsed dictionary), and a duplicated row with contradicting text.

**Result:** all seven findings confirmed. The owner approved G1–G5 (OD-32…OD-36), and Rev 1.9b applies them.

## Reproduction before the fix (`34bc80d`)

```
$ python3 -I audit3/adversarial_counterexample_replayer.py --pack-root docs/design/van-next
BASELINE 51 DUs 71 requirements 0 plan findings 0 machine findings
SHORTCUT_ESCAPES VAN-SM-FUND_DEPOSIT DRAFT->SETTLED True
SHORTCUT_ESCAPES VAN-SM-FUND_WITHDRAWAL DRAFT->PAID True
SHORTCUT_ESCAPES VAN-SM-TRADE_ORDER DRAFT->FILLED True
SHORTCUT_ESCAPES VAN-SM-NEWS_ARMED_TICKET DRAFT_UNAPPROVED->USED True
REQUIREMENT_DROP_ESCAPES VAN-NX-004 True
REQUIREMENT_DROP_ESCAPES VAN-NX-055 True
DUPLICATE_MACHINE_ESCAPES True
DUPLICATE_TRANSITION_ESCAPES True
```

Text-level probes (in-memory copies of the blueprint): deleting the `VAN-NX-055` row → 70 requirements, `findings []`; duplicating it with contradicting text → 71 requirements, `findings []`.

## Findings

| Finding | Verified how | Result | Rev 1.9b |
|---|---|---|---|
| NXA-01 BLOCKER: shortcut transitions pass the state-machine checker | Replayer; then read `check()` | **Confirmed, and worse than stated**: the shortcut passes with a *real* proof label (`broker_readback`), not only arbitrary text. The checker had no notion of a permitted transition relation | W1: approved transition list with typed proofs (R8, R9), mandatory waypoints in the checker (R10), hash pinned in the decision record (R11) |
| NXA-02 BLOCKER: deleting a requirement is not caught | Replayer; text-level deletion | **Confirmed.** Only `STALE_PLAN` noticed, and only until the plan was regenerated | W2: owner-pinned requirement lock covering the 71 rows and the 78 surfaces' 349 owner actions |
| NXA-03 HIGH: duplicate IDs silently pass | Replayer; duplicated requirement row | **Confirmed.** The machine map, transition map and requirement dictionary each kept the last entry | W3: collisions are findings (R0; `REQ_DUPLICATE`, `OQ_DUPLICATE`, `DAG_DUPLICATE`, `SURFACE_DUPLICATE`) |
| NXA-04 HIGH: parity checker required from PKT-001, built in PKT-004 | Plan §1 rule 3 against §4 | **Confirmed**; my sequencing error in Rev 1.9a. **The same error was in §17 F2**, which required "parity checker green" as an F15 input although the checker is built after F15 | W4: two-stage preservation rule 3a; F2 corrected; generator rule `PARITY_BEFORE_CHECKER` |
| NXA-05 OPEN F15 INPUT: the 171/115 mapping is incomplete | Read `crosswalk/REV2_171_ATOM_SEED_UNREVIEWED.csv` | **Confirmed**: 171 of 171 `CANDIDATE_NOT_SEMANTICALLY_VALIDATED`; 153 with empty `source_truth`. Already declared as PKT-002's job | Unchanged: DU-01 obligation |
| NXA-06 LOW: two versions of the Rev 1.9 response | `git diff 8ac8992 34bc80d` | **Confirmed**: 6 lines were added after the pack was sealed | W5: base restored to the sealed bytes (SHA-256 `2711905d…6fff`, equal to the copy inside the Rev 1.9a zip); the later lines are `…_ADDENDUM_A1_20261016.md` |
| NXA-07: the visual references are not in the evidence pack | — | Agreed; they are referenced by SHA-256 and re-retrieved at DU-01 | Unchanged |

## What changed

**W1: approved transition list (`contracts/VAN_TRANSITION_GUARDS_REV1_9B.json`).**
- **What it holds:** 159 transitions, each with a stable ID and the exact AND-set of required proofs. There are 35 proof types, each with a meaning and the guard fields it binds.
- **How it was produced:** from the current model, which had 0 findings and was reviewed in two earlier audits. Producing it changed no state machine.
- **New checker rules:**
  - R8: the model equals the list.
  - R9: every proof is typed.
  - R10: success states are reachable only through mandatory waypoints, and these are held in the checker itself.
  - R11: the list's hash equals the pinned hash.
  - R0: duplicates fail.
- **Why R10 matters:** even if someone edits the list and re-pins it, the deposit, withdrawal, order and news shortcuts still fail. The self-test proves this.

**W2: requirement lock (`plan/REQUIREMENT_LOCK_REV1_9B.json`).**
- **What it holds:** a SHA-256 digest of each §16.1 row's text (ID and cells) and of each legacy surface's owner-action list.
- **What fails:** a removed, changed, unlocked or duplicated requirement; a removed or duplicated surface; a dropped owner action; an edited lock without a matching pin.
- **How to update it:** `--write-requirement-lock` rewrites the lock, and refuses to drop a locked requirement unless the lock records the owner decision that supersedes it.
- **The auditor's direct `validate()` call:** it is caught too, because `validate()` now loads the lock by default.

**W4: two-stage feature preservation (plan rule 3a).**
- **PKT-001 to PKT-003:** a preservation-inventory gate applies:
  - no source change;
  - frozen heads unchanged;
  - `--check` passes, so the lock is intact;
  - the Feature Ledger changes only through recorded rows.
- **PKT-004:** exits only with the parity checker qualified.
- **PKT-005 onward:** every packet's exit needs no `FEATURE_LOSS`.

## Proof after the fix

```
$ python3 plan/generate_plan.py --check            → 0 findings
$ python3 plan/generate_plan.py --selftest         → 23 of 23 caught (was 9)
$ python3 contracts/check_state_machines.py        → 0 findings
$ python3 contracts/check_state_machines.py --selftest → 24 of 24 caught (was 8)
$ python3 contracts/check_state_machines.py contracts/STATE_MACHINES.json → 230 findings (69 structural + 161 R8), exit 1
```

**The auditor's replayer, rerun against Rev 1.9b:**
- It hard-codes the Rev 1.9a blueprint name, so it ran on a copy where the Rev 1.9b blueprint was also saved under that name.
- Every escape that was `True` before is now `False`:

```
SHORTCUT_ESCAPES VAN-SM-FUND_DEPOSIT DRAFT->SETTLED False
SHORTCUT_ESCAPES VAN-SM-FUND_WITHDRAWAL DRAFT->PAID False
SHORTCUT_ESCAPES VAN-SM-TRADE_ORDER DRAFT->FILLED False
SHORTCUT_ESCAPES VAN-SM-NEWS_ARMED_TICKET DRAFT_UNAPPROVED->USED False
REQUIREMENT_DROP_ESCAPES VAN-NX-004 False
REQUIREMENT_DROP_ESCAPES VAN-NX-055 False
DUPLICATE_MACHINE_ESCAPES False
DUPLICATE_TRANSITION_ESCAPES False
```

**The pins were tested before they were trusted:**
- With both pins set to `PENDING`, `--check` reported `LOCK_NOT_PINNED` and the state-machine checker reported `R11 no TRANSITION_GUARDS hash pinned`.
- Both passed only after the real hashes were recorded.

## Limits, stated plainly

- **What the pins prove today.** They prove a file has not changed since it was *prepared*. They become owner approval only when the owner signs the decision record (OQ-05, B3). Until then, an author can edit a locked file and its pin together. The owner's signature and the independent DU-31 review are what make that visible.
- **The approved list's scope.** It records the current model; it does not judge whether each guard set is *sufficient*.
  - One item for the independent F15 reviewer: `SIGNED → ARMED` on the news ticket needs no proof.
  - The auditor listed an "armed window" among that ticket's preconditions; today the window is enforced only at `ARMED → USED` and through expiry.
  - This is recorded, not changed, because changing it would alter product semantics without an owner decision.
- **Still owner-only:** signing the decision record and decisions B1–B6.
- **Still independent-only:** the F15 certificate at DU-31.
