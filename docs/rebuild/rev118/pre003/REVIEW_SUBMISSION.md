# PRE-003 independent-review submission: VAN Rev1.18

Prepared by the lead on 2026-10-21 for the **independent** F15 reviewer. This is a submission, not a certificate. The lead has not issued, and cannot issue, F15, PRE-001/PRE-002 acceptance, an owner signature, or a review that counts as independent (see `F15_LIFECYCLE_AND_OQ05.md` §8). Every assessment below is **author-prepared** and is for the reviewer to challenge.

## 1. Identities to pin

| Item | Value |
|---|---|
| Repository / branch | `Vanguduza/Van` `ccr-9e07e1af-8mgz1p`; pin the commit you review with `git rev-parse HEAD` |
| Source candidate (PR #104) | `b02075f327ea8180ab6d269eba358cf8c5479878` |
| Admitted Rev1.18 package | tree `ac0226a22a95f51642cfeb37b3709b40f7cacf10`, archive SHA-256 `6c7c7c1cb4fbd4748c0d63ceb2add9bd460778b66fb3b2302e16de09ac3a57a8`, delivery commit `3c3379bd` (byte-identical) |
| AP-001 candidate (Rev1.18.1, not admitted) | file-tree SHA-256 `8eb76af51c41260c0e86ab4201a75339126367126ab3ada806ee0d2d89e10e49`; definition and all 30 checks in `../pre002/AP-001/CANDIDATE_VERIFICATION.json` |
| DDS source-contract pin | `64d6b7158c723b7700e5b53175ea8048d4e92d00` (CONSOLIDATION_STATE `native_dependency`) |
| DDS code read for F15/reviewer/signing | `origin/master` `204f2f3b` |
| Every rebuild evidence file | SHA-256 in `SUBMISSION_MANIFEST.json`; verify with `python3 tools/rebuild/manifest.py check` |
| Ledger consistency at `1cab6b2f` | `../receipts/PROJECT_TRUTH_VERIFY_1cab6b2f.json`: GREEN, 533 commits, exit 0. Covers only that range; later commits need their own run |

## 2. What to review

| Area | Artefact | Reproduce |
|---|---|---|
| Source preservation (PRE-001) | `../pre001/*` (dispositions, 116 symbol dispositions, classification of 2,131 files, test evidence) | `python3 tools/rebuild/pre001.py check` and `selftest` (20/20); needs an unshallowed clone with `refs/pull/*` fetched |
| Gate-unit acceptance gap | `../pre002/AP-001/` (patch, per-identity review, design change proposal) | `python3 tools/rebuild/ap001.py check` and `selftest` (13/13) |
| AP-001 complete candidate | `CANDIDATE_VERIFICATION.json`, `DRYRUN_RESULT.json`, `DRYRUN_*_CHANGES.diff` | `cp -a docs/review-inputs/van-rev115/package <copy>; python3 tools/rebuild/ap001_dryrun.py <copy>` (10/10 package checks exit 0), then `python3 tools/rebuild/ap001_candidate.py <copy>` |
| Requirement challenge (all 324) | `../pre002/challenge/DOSSIERS.json`, `SUMMARY.md` | `python3 tools/rebuild/pre002_dossiers.py check` and `selftest` (11/11) |
| Semantic review of 43 "no negative/recovery" | `../pre002/challenge/review/NEG_REC_REVIEW.json`: 37 adequate with references, 6 gaps | `python3 tools/rebuild/pre002_neg_review.py check` (every cited identity and section validated) |
| 189 without a Product Truth link | `../pre002/challenge/review/PRODUCT_TRUTH_TRACE_REVIEW.json` | `python3 tools/rebuild/pre002_truth_review.py check` |
| Owner-question dependencies | `../pre002/challenge/review/DECISION_REGISTER.json`: 49 of 149 flagged requirements genuinely depend on a decision; 18 owner decisions, 3 resolved as technical or already decided | `python3 tools/rebuild/pre002_decisions.py check` |
| Follow-on amendment | `../pre002/AP-002/AP-002_PATCH.json`: 8 new identities, 6 owner bindings, 4 citation errata; additive; not dry-run | read; dry-run after the AP-001 decision (count chain) |
| Observation obligations | `../obligations/OBLIGATIONS.json` (OBL-001…005) | read |
| F15 lifecycle and signing | `F15_LIFECYCLE_AND_OQ05.md`, `F15_AND_IDENTITY_REQUIREMENTS.md` | read against the DDS source cited |
| CI | `../ci/CI_DIAGNOSIS.md`, `../ci/patches/` | backend: `pytest tests/contracts/test_artemis_*.py` with and without the sibling; `pytest tests/contracts/test_ci_dds_contract_pin.py` |

## 3. Unresolved findings the reviewer must decide

1. **AP-001** (5 gate units without acceptance). Preparation blocker; PRE-001 stays open until it is admitted or rejected.
2. **AP-002** (six gaps: NX-001, 024, 025, 026, 049, 067; four ambiguous master citations). Accept, amend or reject.
3. **Project identity.** The registry assigns `previous?.project_id || slug` (expected `van`); the package label is the UUID. Native readback is required (`NATIVE_READBACK_REQUEST.md`). Preparation blocker.
4. **Product Truth.** No atom states the backend-first direction F0 requires (18 clauses). VAN-NX-066/067 have no covering atom. Forecast obligation hashes (90) do not re-derive from package bytes.
5. **Owner decisions** (18): `DECISION_REGISTER.json` `remaining_owner_decisions`, including OQ-05 (signing mechanism recommendation in `F15_LIFECYCLE_AND_OQ05.md` §7).
6. **CI defects on the consolidation head:**
   - Android ICU regex: two sites; patch prepared.
   - Rive action-2 margin: both outcomes at one SHA; remedies prepared.
   - DDS deploy key: not yet provisioned.
7. **Self-referential provenance.** The 18 backend-first `source_row_sha256` values are sha256 of their own text.
8. **Trusted-base admission** (PR #94 then PR #104) is separate from F15. See `../ADMISSION_STEPS.md`.
9. **F15 timing.** Certify only after merges and the AP-001 decision, at a frozen SHA, with no commits to the registered checkout before the first wave branches (`F15_LIFECYCLE_AND_OQ05.md` §3, §6).

## 4. Explicit non-claims

- No application code changed. The only active-code change on this branch is the CI prerequisite (`.github/workflows/van-ci.yml`, its template mirror and its regression test) under owner authorization.
- No Rev1.18 acceptance identity was executed; all remain NOT_RUN.
- JVM-harness and source-test passes are source evidence, not instrumentation, APK or handset acceptance.
- No deployment, provider, device, financial or live effect; no credential created or widened.
- No certificate, signature, independent review, admission or regrading was produced.
