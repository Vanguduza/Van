# Consolidation validation and continuation

This is source-consolidation evidence, not completed Rev1.18 application acceptance. The 1,610 blueprint acceptance identities remain a distinct future programme; they are not the similarly sized inherited source contract suite.

## Source and preservation

- Source baseline: `bdd63a40174d36ccdd0ceb8f3fb258c612df8bbe`.
- Integrated trading, accounts and blueprint inputs are pinned in root `CONSOLIDATION_STATE.json`.
- All 70 original remote heads were read back unchanged; all 70 archive snapshot tags matched their original full commit IDs.
- Seven available ordinary Van checkouts were inspected, covering eight original local branch refs. No additional local-only commit required rescue. The original dirty `/workspace/Van` head, status and tracked-diff hashes were unchanged.
- Exact Rev1.18 archive and unpacked package match the admitted delivery. Whole-product documentary checks passed 26/26; compiled effective registry and rendered-plan checks passed; archive-member comparison found no differences. These are document checks.

## Executed checks

| Scope | Actual outcome |
|---|---|
| Trading source suite | 1,534 passed, 2 skipped |
| Focused execution, lockout, incremental-ledger and atomic-account regressions | 47 passed; overlaps the trading suite |
| New transaction-preservation regressions plus learning/evidence suites | 89 passed, including 9 new transaction cases; learning cases overlap the trading suite |
| Browser/stream/worker service source suites | 198 passed using the separate media-worker environment |
| Android pure JVM logic | 1,273 tests, zero failures/errors/skips, 157 JUnit XML files |
| Backend full source suite | 4,963 passed, 159 skipped, 2 subprocess import-path failures |
| Backend subprocess failures with correct inherited import path | Both passed; no application-code change or weakened assertion |
| Contracts/Hermes source suites | 1,601 passed, 8 skipped; the remaining history test captured intermediate head f6aacd10 before adoption rows were appended |
| Full history test after adoption ledger completion | 1 passed in 395.41s, against completed source/adoption head f3cf8301; later scoped changes retain hook-generated rows |
| Existing maturity, authority-map and Rev5.1 source/specification harness | Passed; does not issue runtime eligibility |
| Local adoption ledger at dcd57640 | 50 added/adopted commits verified; source baseline's preceding 470 commits separately verified |
| Owner-release workflow regression suite | 45 passed after runner-context correction |
| Generic voice acquisition, packaging and independent verification | All 45 files / 224,852,871 bytes verified; manifest SHA-256 `7fa17db389349bd587c1f061c7162f9a4c419a552c9d57cd03e8e937bf935e30` unchanged |
| Source consolidation verifier | 70 branches, exact blueprint hash, preserved input ancestry and all active Python test roots; zero findings |

Do not sum overlapping runs as independent coverage. Skips remain skips. Backend failures were `ModuleNotFoundError: van_gateway` in spawned Python processes when launched from repository root without an inherited backend path; the exact crash tests passed with `PYTHONPATH=backend`. Run backend tests from `backend/` as CI does, or supply the correct path explicitly. Contract setup also required the existing pinned DDS sibling checkout; environment-variable selection alone is not supported by that older source helper.

## Build prerequisite corrections

The official Sherpa ASR archive was replaced at 2026-10-21T06:21:56Z. Publisher metadata and downloaded bytes agree on the new 310,453,030-byte archive and SHA-256 `4e8097ebda27dad47353bd4a7edea77c985e2dd5330d5f1cdc07354bb12ab00d`. Every selected ASR model matches its original size and SHA-256. Only archive provenance was repinned; model pins, APK bundle pin and all capabilities are unchanged. See `ASR_ARCHIVE_REQUALIFICATION.json` and the successful packaging log. No corrupt download was admitted and no verification was bypassed.

GitHub rejected the inherited manual release workflow because `runner.temp` was evaluated in job-level `env`, where that context is unavailable. Paths now bind through `$GITHUB_ENV` in a runner step. `workflow_dispatch`, the release environment, signing inputs, signer/profile verification, cleanup and packet requirements are preserved. GitHub no longer creates the invalid-workflow run for this file at source head `7858163ceb51c2a808a5ed3143889275dbe5b6a4`. No release was dispatched.

The inherited cognitive Android CI workflow also omitted generic voice-asset preparation before invoking the mandatory asset-seal task. Its app build correctly refused the absent bundle. The job now installs Python and executes the existing exact-pinned acquisition plus verification before the unchanged build/test/lint gate. The locally verified 45-file bundle proves the prerequisite; a completed hosted app build remains separate evidence.

## GitHub admission and remaining qualifications

Review PR: https://github.com/Vanguduza/Van/pull/104

GitHub's canonical-tree check passes. Main admission is still blocked by the trusted Project Truth bootstrap: at main `8eb1889822fc8a83f219977c15340172e16acd91`, `trusted/tools/ci/project_truth_ledger.py` does not exist. The PR's ledger job therefore fails before it can judge this candidate. Log: https://github.com/Vanguduza/Van/actions/runs/39588721836/job/119184020620 . The existing framework proposal is PR #94; its one-time bootstrap/trusted-base and independent/code-owner admission must be resolved through that policy, not by disabling checks or allowing the candidate to approve itself. Local ledger verification is not the same as this admission.

PR #104 remains a draft source candidate; main, original branch heads and live hosts were not changed. CI reruns for subsequent source heads may still be queued/running; do not claim an all-green final GitHub run from these local results. Owner release/signing, provider and native service qualification, economic qualification and S24/Artemis acceptance have not been issued here.

## Next execution

Opus should start from this consolidated branch, read root `CLAUDE.md`, verify `CONSOLIDATION_STATE.json` and follow `OPUS_BUILD_PROMPT.md`. Begin canonical PRE admission; retain backend-before-frontend gates. Treat all archive candidates as scoped source references until independently admitted. Do not reset to the old blueprint-delivery source branch or restore historical audit source copies over this tree.
