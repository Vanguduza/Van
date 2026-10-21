# PRE-002 status — whole-product semantic reconciliation and packet contracts

Unit `PRE-002` (VAN-PKT-002), plan revision 1.18, package tree `ac0226a2`, source frozen at consolidation head `b02075f3`. The exit contract requires author review **and independent challenge** of the 171 atoms, 115/234 contexts, 78 surfaces, 349 actions and the inherited and new requirements, with owner decisions identified and no START prerequisite hidden by a default.

## Author-side work completed (lead, this session)

| Obligation | Evidence | Result |
|---|---|---|
| Bidirectional registry linkage: requirement↔unit, unit↔test, action→contract/test/units/surface, context→units/actions, feature→context, atom→feature, truth→requirement | `tools/rebuild/pre001.py` trace check → `docs/rebuild/rev118/pre001/TRACE_CHECK.json` | Counts derived from artefacts: 324 / 1,610 / 131 / 349 / 234 / 93 / 171 / 22 / 72. One defect class found: 5 gate units without acceptance (AP-001) |
| Source admission feeding semantics (PRE-001) | `pre001/STATUS.json`, `DISPOSITIONS.json`, `SOURCE_CLASSIFICATION.json` | 21 refs and 34 preservation rows dispositioned with evidence; 2,131 files with kind, owning units and migration class |
| Gate units have falsifiable acceptance | `pre002/AP-001/*`, `tools/rebuild/ap001.py` | Proposal prepared with per-identity specification; additive (1,610→1,624); generic checks 13/13; dry run on a package copy passes all 10 package checks; **not admitted** |
| Owner decisions identified by scope and gate | `pre002/OWNER_DECISION_REGISTER.json` | 21 questions: 13 START, 4 LIVE, 1 F15 (OQ-05), 1 target admission (OQ-CRYPTO-01), 1 financial activation (OQ-SO-01), 1 decided-values-needing-runtime-signature (OQ-21) |
| No hidden START default | Same register, `source_default_scan` | No source value pre-decides OQ-02/07/15/16. OQ-21 code defaults equal the accepted OD-39 values; signed runtime activation still has to be verified in BE-009 |
| Experience-learning / model-hardening documentary admission (Rev1.16/1.17 deliverable) | Package verifiers run 2026-10-21: `verify_experience_learning.py` 36/36, `verify_model_hardening.py` 35/35 | Documentary checks only, by design ("do not require application execution at PRE") |
| Challenge dossiers for all 324 requirements | `tools/rebuild/pre002_dossiers.py` → `pre002/challenge/{DOSSIERS.json,SUMMARY.md}` | One dossier per requirement: provenance, plan owners, linked identities, product-truth trace, open owner questions, baseline source files, mechanical flags and challenge questions. Flags: 43 no negative/recovery, 29 underspecified, 18 template, 1 subjective, 149 owner question open, 3 gate unit without acceptance, 189 no product-truth trace; 0 missing, unbound or ownership mismatches. Selftest 11/11. **Author-prepared; state `AUTHOR_CHALLENGED_PENDING_INDEPENDENT_REVIEW`** |
| DesignChangeProposal binding (VAN-SO-043) | AP-001 uses the package's DCP field set | Applied to AP-001 |

## Not completable by the lead (reviewer or owner work)

- **Independent challenge.** The dossiers frame the challenge; answering them is the reviewer's act. Every requirement row is still graded pending independent review or admission: 141 `AUTHOR_RECONCILED_PENDING_INDEPENDENT_REVIEW`, 90 `…_PENDING_INDEPENDENT_ADMISSION`, 32 owner-directed integration pending semantic admission, 20 consolidation corrections, 18 new owner directives, 8 review proposals, 7 owner-requested integrations, 8 hardening (324 in total). The 93 features and 171 atoms are `AUTHOR_RECONCILED_NOT_INDEPENDENTLY_ACCEPTED`; Product Truth is `PENDING_OWNER_SIGNATURE_AND_INDEPENDENT_REVIEW`. The lead must not regrade these.
- **HVA R01–R12 admission** and the separation of research-source from implementation-evidence namespaces are listed as "independently admit". The namespaces exist (`package/evidence/rev115/` versus `docs/rebuild/rev118/`); admission is the reviewer's act.
- **Owner decisions** needed before the affected units START (see the register). None blocks PRE-002 documentation, but OQ-05 blocks F15.
- **AP-001 admission** through the package procedure.

## Status

`PRE-002: AUTHOR_WORK_COMPLETE_PENDING_INDEPENDENT_CHALLENGE`. No application PASS is claimed. The next actor is the independent reviewer named by the F15 process (see `../pre003/REVIEW_SUBMISSION.md`).
