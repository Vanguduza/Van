# Trusted-base admission steps — PR #94, then PR #104 (and this branch)

**22 October continuation:** PR #105 now carries this branch. The complete candidate intake is `pre003/MAIN_AUTHORIZATION_INTAKE_CURRENT.json`: all 39 original consolidation records preserved plus four continuation records, 43 total against the recorded `8eb18898` base. Recompute against the actual base after bootstrap before intake. Android ICU fixes are applied and pass their two hosted runtime tests; source `637eaf96` corrects localized gaze measurement and deep-link harness cleanup after the first runtime run exposed those test issues. The immutable ASR acquisition fix and local APK build/lint pass are recorded in `CONTINUATION_20261022.md`. Do not use the historical "patch not applied" statements below as current status. Current F15/signature interpretation is in `pre003/F15_LIFECYCLE_REVIEW_20261022.md`. No arbitrary five-full-run requirement is introduced: execute the actual required runtime/visibility/within-test repeatability obligations and investigate remaining failures.

The remaining text records the earlier admission plan and observations.

Facts observed 2026-10-21 (PR state re-read at about 21:30 UTC: unchanged since 11:17 UTC; #104 head `b02075f3` and #94 head `296d647d` are drafts with no reviews):
- `main` is `8eb18898`. Its workflows are `canonical-tree-guard.yml` and `van-ci.yml`. Neither runs the Project Truth ledger; `tools/ci/project_truth_ledger.py` is absent on `main`.
- The candidate workflow (consolidation `b02075f3`) runs `python trusted/tools/ci/project_truth_ledger.py --repo head verify-pr --base "$TRUSTED_SHA" ...`, checking out the base as `trusted/`. On base `main` that file does not exist, so the job fails before judging the PR (consolidation VALIDATION.md, run 39588721836).
- PR #94 (`296d647d`, draft) adds the hooks, CODEOWNERS, `tools/ci/project_truth_ledger.py`, baselines, the ledger tests and the trusted-checker job: 17 files, no application code. Its own review states it is "a proposed initial owner adoption, not an adopted/trusted base", that the transition "needs the owner's explicit review act", and that branch protections are currently absent.
- PR #104 is the consolidation (draft, head `b02075f3`). This work branch `ccr-9e07e1af-8mgz1p` descends from it; its own commits are `git log b02075f3..ccr-9e07e1af-8mgz1p`, each with a hook-generated ledger row. Local `project_truth_ledger.py verify` was GREEN at each push (529 commits at `78145b8d`); that is consistency, not trusted-base admission.

## Steps (no merge, bypass or protection change performed by the lead)

| # | Actor | Action | Check that proves it |
|---|---|---|---|
| 1 | Owner + code owner | Review PR #94 and adopt it as the one-time framework bootstrap, per `tools/ci/README.md` ("merge the intake commit first, then verify the commits it authorizes against the new base") | `main` contains `tools/ci/project_truth_ledger.py` and the baselines, and CI on `main` runs the ledger job |
| 2 | Owner | Enable the protections PR #94 names for `main` (and `gpt/**`): require `project-truth-ledger`, code-owner review, pull requests, no bypass | GitHub branch-protection readback |
| 3 | Owner/code owner | Intake the additive authorization records separately from the code they authorize: the 39 consolidation records in `docs/consolidation/MAIN_AUTHORIZATION_INTAKE.json` (recompute if source or base changed) **plus** this branch's records `auth-20261021-owner-rev118-pre001-pre002`, `auth-20261021-owner-rev118-ci-prerequisites` and `auth-20261021-owner-rev118-ci-workflow-template` | Intake commits on `main`; no existing record modified |
| 4 | CI | Re-run PR #104 against the adopted base: `verify-pr --base <adopted main> --head <PR head>` | Ledger job green; canonical-tree guard green; all source suites green on the exact head |
| 5 | Independent/code-owner reviewer | Review PR #104 itself (source consolidation) | Required approvals present |
| 6 | Owner | Merge PR #104 through the admitted process only | Merge commit on `main`; no force-push or history rewrite |
| 7 | — | Open a PR for `ccr-9e07e1af-8mgz1p` (PRE evidence, rebuild tooling and the CI prerequisite fix) against the updated `main`; same ledger verification | Ledger job green on that head |
| 8 | Owner | Provision the read-only DDS deploy key (see below) before step 4, so the backend job can run | backend job passes the 'Require the DDS contract read key' step |
| 9 | Owner + reviewer | Admit or reject the prepared Android ICU regex patch (`ci/patches/0001`) and decide the Rive remedy (`ci/CI_DIAGNOSIS.md` §2b) | instrumentation job green over ≥5 runs at one SHA, or the owning unit records the open defect |

Not done, and not to be done to unblock the build: merging either PR, disabling or bypassing checks, minting records for past commits, rewriting history, or treating local GREEN as admission. F15 is independent of this sequence, but the F15 baseline SHA must be the commit actually reviewed. If merging changes the head, the certificate must be computed for the new baseline.

## PR #104 CI status and fixes

Full diagnosis: `ci/CI_DIAGNOSIS.md`. Summary:

| Job | Cause | State |
|---|---|---|
| project-truth-ledger | Base `main` lacks the trusted checker until PR #94 | Resolved by steps 1–4 |
| backend | No `../dial-development-system` sibling (reproduced: 2 passed/134 errors without, 136/136 with the 3 pinned files) | **Fixed on this branch** (`0c7fa8cf`): pinned sparse checkout with a read-only deploy key, blob-verified, fail-closed without the key; regression test `tests/contracts/test_ci_dds_contract_pin.py` |
| backend (next defect, CI never reached it) | services step lacked the stream host's hash-locked dependencies (aiortc/av/aiohttp) | **Fixed on this branch** (`17a7cb81`): isolated venv mirroring `bootstrap.sh`; 198/198 services tests locally |
| android-instrumentation | (a) ICU rejects `\{(\w+)}` → 4 CommandCentreLaunchTest failures; a second latent site in OwnerServicePresentation; (b) RiveContractTest action 2 margin, which has both passed and failed at identical SHA `80f3f0f3` | (a) patch prepared, not applied (`android/` not authorized); (b) asset/test remedies prepared for admission |
| character-forge-gate | Downstream of (b) | — |

**Owner action for the backend job (credential provisioning is outside the lead's authority):**
1. On `Vanguduza/dial-development-system` → Settings → Deploy keys, add a new key, **read-only**.
2. On `Vanguduza/Van` → Settings → Secrets and variables → Actions, add `DDS_CONTRACT_READ_DEPLOY_KEY` holding the private half.

The workflow uses it only for a sparse checkout of three files at `64d6b7158c72` with `persist-credentials: false`. No other job sees it.
