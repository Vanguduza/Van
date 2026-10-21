# Trusted-base admission steps — PR #94, then PR #104 (and this branch)

Facts observed 2026-10-21:
- `main` is `8eb18898`. Its workflows are `canonical-tree-guard.yml` and `van-ci.yml`. Neither runs the Project Truth ledger; `tools/ci/project_truth_ledger.py` is absent on `main`.
- The candidate workflow (consolidation `b02075f3`) runs `python trusted/tools/ci/project_truth_ledger.py --repo head verify-pr --base "$TRUSTED_SHA" ...`, checking out the base as `trusted/`. On base `main` that file does not exist, so the job fails before judging the PR (consolidation VALIDATION.md, run 39588721836).
- PR #94 (`296d647d`, draft) adds the hooks, CODEOWNERS, `tools/ci/project_truth_ledger.py`, baselines, the ledger tests and the trusted-checker job: 17 files, no application code. Its own review states it is "a proposed initial owner adoption, not an adopted/trusted base", that the transition "needs the owner's explicit review act", and that branch protections are currently absent.
- PR #104 is the consolidation (draft, head `b02075f3`). This work branch `ccr-9e07e1af-8mgz1p` descends from it; its own commits are `git log b02075f3..ccr-9e07e1af-8mgz1p`, each with a hook-generated ledger row. Local `project_truth_ledger.py verify` was GREEN at each push (529 commits at `78145b8d`); that is consistency, not trusted-base admission.

## Steps (no merge, bypass or protection change performed by the lead)

| # | Actor | Action | Check that proves it |
|---|---|---|---|
| 1 | Owner + code owner | Review PR #94 and adopt it as the one-time framework bootstrap, per `tools/ci/README.md` ("merge the intake commit first, then verify the commits it authorizes against the new base") | `main` contains `tools/ci/project_truth_ledger.py` and the baselines, and CI on `main` runs the ledger job |
| 2 | Owner | Enable the protections PR #94 names for `main` (and `gpt/**`): require `project-truth-ledger`, code-owner review, pull requests, no bypass | GitHub branch-protection readback |
| 3 | Owner/code owner | Intake the additive authorization records separately from the code they authorize: the 39 consolidation records in `docs/consolidation/MAIN_AUTHORIZATION_INTAKE.json` (recompute if source or base changed) **plus** `auth-20261021-owner-rev118-pre001-pre002` from this branch | Intake commits on `main`; no existing record modified |
| 4 | CI | Re-run PR #104 against the adopted base: `verify-pr --base <adopted main> --head <PR head>` | Ledger job green; canonical-tree guard green; all source suites green on the exact head |
| 5 | Independent/code-owner reviewer | Review PR #104 itself (source consolidation) | Required approvals present |
| 6 | Owner | Merge PR #104 through the admitted process only | Merge commit on `main`; no force-push or history rewrite |
| 7 | — | Open a PR for `ccr-9e07e1af-8mgz1p` (PRE-001/PRE-002 evidence only) against the updated `main`; same ledger verification | Ledger job green on that head |

Not done, and not to be done to unblock the build: merging either PR, disabling or bypassing checks, minting records for past commits, rewriting history, or treating local GREEN as admission. F15 is independent of this sequence, but the F15 baseline SHA must be the commit actually reviewed. If merging changes the head, the certificate must be computed for the new baseline.

## PR #104 CI on head `b02075f3` (van-ci run 39590832158), observed 2026-10-21

| Job | Result | Diagnosis | Status |
|---|---|---|---|
| project-truth-ledger | FAIL | Expected on base `main`: `trusted/tools/ci/project_truth_ledger.py` is absent until PR #94 is adopted (step 1) | Resolved by steps 1–4 |
| backend | FAIL | **Reproduced locally.** All 134 errors are in `tests/contracts/test_artemis_*`. `tools/certification/artemis_acceptance.py:210` resolves `dds_root or root.parent / "dial-development-system"`, and the job checks out only `Van`. In a worktree with no sibling the Artemis suite errors (38/38). With the sibling DDS at the pin (`CONSOLIDATION_STATE.json` line 29, `64d6b7158c72…`) it passes 38/38 | Fix proposed below; needs owner authorization |
| android-instrumentation, character-forge-gate | FAIL | `connectedAndroidTest` failed in `RiveContractTest.coreInputsDriveTheRig`; character-forge-gate fails on that binding. PR #101 (`a39f241b`) and PR #94's Oct-9 run passed this job. The base lineage since then includes `077bc517` (visual renderer removal) and `8c192be7`. The assertion text is in the run's test-report artifact, which this session cannot download, so **regression versus emulator flake is not established** | Owner or CI: read the artifact, then rerun at most once per the flake rule. A second failure is real and goes to the owning Android unit |
| mutation, android-and-visual-evidence, cognitive-fabric, canonical-tree, python | PASS | — | — |

**Proposed backend fix (not applied).** It touches `.github/workflows/van-ci.yml`, which is outside this branch's authorization (`tools/rebuild/**`, `tests/rebuild/**`, `docs/rebuild/**`). Add this to the `backend` job before the test step:

```yaml
      - uses: actions/checkout@v4
        with:
          repository: Vanguduza/dial-development-system
          ref: 64d6b7158c723b7700e5b53175ea8048d4e92d00
          path: dds
          token: ${{ secrets.DDS_READ_TOKEN }}   # read-only; only needed if DDS is private
      - run: mv dds ../dial-development-system
```

The alternative is to pass `dds_root` from an environment variable. That is an application change to `tools/certification/`, which needs owner authorization and a ledger record. Either way the pin must stay `64d6b715` until PRE-001's MOVED_CROSS_REPO dispositions (DDS `2964c6ec`) are re-pinned deliberately.
