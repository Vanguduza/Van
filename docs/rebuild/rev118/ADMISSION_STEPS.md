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
