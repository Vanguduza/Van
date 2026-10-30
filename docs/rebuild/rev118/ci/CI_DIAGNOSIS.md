# PR #104 CI diagnosis and prepared fixes (van-ci run 39590832158, head `b02075f3`)

Author-prepared. Every claim below cites the command or log that established it.

## 1. backend: missing DDS sibling — FIXED IN CI (applied, needs one secret)

**Reproduced.** In a layout matching CI (`Van/` plus optional sibling `dial-development-system/`), `pytest -q tests/contracts/test_artemis_*.py`:

| Sibling | Result |
|---|---|
| absent | `2 passed, 134 errors` — identical to the CI step |
| DDS at pin `64d6b7158c72` | `136 passed` |
| DDS at master `204f2f3b` | `136 passed` |
| only the 3 contract files at the pin (blobs `4aca852d…`, `c99f02f3…`, `9134ddc8…`) | `136 passed` |

**Source contracts read.** These three files are the whole dependency:
- `tools/certification/artemis_acceptance.py:210` (`contract_paths`) reads `agent-system/orchestration/android-testing-mcp.mjs`, `agent-system/orchestration/android-testing-plane.mjs` and `deploy/netcup/hermes-control/artemis/dial_artemis_mcp_bridge.py`;
- `tests/contracts/test_artemis_acceptance_plan.py:246` reads `android-testing-mcp.mjs`.

**Why the pinned commit, and why it is compatible.**
- `CONSOLIDATION_STATE.json` `native_dependency` pins `64d6b7158c72` with scope "pinned source contract tests; not current deployment attestation". That pin is the qualification baseline.
- The three blobs are byte-identical at `64d6b715` and at `2964c6ec` (the DDS commit PRE-001 cites for relocated Artemis subscription source).
- At master, `android-testing-plane.mjs` differs (`4b2de40c`), yet the tests still pass. That shows compatibility, but the baseline stays the declared pin, and moving it is a deliberate re-pin.
- `2964c6ec` is cited only as the destination of cross-repo symbol moves, not as the test baseline.

**Constraint found.** DDS is private and Van is public (GitHub API visibility, read through the session proxy). Copying the files into Van would publish private source, and Van's `GITHUB_TOKEN` cannot read DDS.

**Applied fix** (`.github/workflows/van-ci.yml`, mirrored byte-identically in `tools/ci/github-actions-ci.yml`):
1. A precondition step fails with an actionable error if `secrets.DDS_CONTRACT_READ_DEPLOY_KEY` is absent. It never skips.
2. `actions/checkout@v4` of `Vanguduza/dial-development-system` at the pin, sparse to exactly the three files, with `persist-credentials: false`.
3. A verification step checks HEAD equals the pin and each file's `git hash-object` equals the recorded blob, then moves the checkout to `../dial-development-system`.

**Regression test** `tests/contracts/test_ci_dds_contract_pin.py` (6 tests) checks:
- the pin equals `CONSOLIDATION_STATE.json`;
- the checkout is read-only, keyed and leaves no credential behind;
- the sparse paths cover every DDS path the code reads;
- a missing key fails rather than skips;
- the sibling is placed before any pytest step;
- the recorded blobs equal real DDS blobs whenever a DDS clone is present.

**Induced failures caught:** wrong pin, wrong blob, `persist-credentials: true`, a conditional precondition, a dropped path. `test_ci_workflow_is_what_it_claims.py` stays green (template byte-identical). The verify step's actual shell script was extracted from the YAML and executed against a real sparse checkout at the pin: `STEP_OK`, sibling holds 3 files.

**Remaining owner action (credential provisioning is not authorized to the lead):**
1. Create a read-only deploy key on `Vanguduza/dial-development-system`.
2. Store its private half as the Actions secret `DDS_CONTRACT_READ_DEPLOY_KEY` on `Vanguduza/Van`.

Until then, the backend job fails at the precondition with that exact message instead of 134 errors.

**Steps CI never reached.** CI skipped every backend step after "Contract tests". All of them were run locally in the CI layout (Python 3.12, `backend/requirements.lock`); see `BACKEND_JOB_LOCAL.json`.
- **The next CI defect would have been the services step.** The stream-host tests need `aiortc`/`av`/`aiohttp` from the hash-pinned `deploy/van-browser-stream/requirements.lock` (3 collection errors in the backend environment).
- **Fixed in `17a7cb81`.** The step now builds an isolated venv exactly as `bootstrap.sh` does and runs the whole `services` tree: 198 passed executing the step's own script. The two locks disagree on `cryptography`/`pyee`, so the backend environment is untouched.
- **The other local non-passes are not CI defects.** Three Chromium tests fail because this container's browser build differs from Playwright 1.63's. One DDS-blob test reads an absolute path that is absent on runners, where it skips. One template-drift failure was my layout artefact.

## 2. android-instrumentation: two separate defects (five failures, not one)

The job log (retrieved through the GitHub Actions API) shows five failures: four `CommandCentreLaunchTest` tests plus `RiveContractTest.coreInputsDriveTheRig`.

### 2a. `PatternSyntaxException` on Android — application defect, patch prepared (not applied)

**Cause, reproduced off-device.**
- Android's `java.util.regex` is backed by ICU4C. ICU rejects an unescaped `}`, which the JDK accepts.
- The system `libicui18n.so.74` (`uregex_open_74` via ctypes, `../ci/patches/0002-…py`) returns `U_REGEX_RULE_SYNTAX` (66305) at offset 8 for `\{(\w+)}`, exactly matching CI's "near index 8".
- `\{(\w+)\}` compiles.

**Scope (scan of all 64 literal Kotlin regexes plus raw strings).** Two defects:
- `android/app/src/main/java/com/dial/van/command/nav/VanRoute.kt:197`, `Regex("\\{(\\w+)}")`, used by `concreteRoute`. This is the deep-link restore path every CommandCentreLaunchTest exercises.
- `android/app/src/main/java/com/dial/van/command/owner/OwnerServicePresentation.kt:43`, `Regex("\\{[a-z_]+}")`. It is **latent**: no instrumentation test reaches it, so it would throw on device whenever an owner-service command template is rendered.

**History.** Introduced in `652ef3f3` (2026-10-08). PR #101's green head `a39f241b` does not contain it, so this is a regression in the consolidation lineage, not flakiness.

**Patch** `patches/0001-android-icu-regex.patch` escapes the closing brace in both places. Evidence:
- the JVM harness on the patched tree gives 1,273/1,273, the same as baseline;
- the proposed ICU test `patches/0002-test_android_regex_compiles_under_icu.py` fails on the current tree (both sites named) and passes on the patched tree.

**Not applied** because `android/` is outside the authorized paths and dependency-ready scope. Applying it needs a ledger authorization for those two files plus the test.

### 2b. `RiveContractTest.coreInputsDriveTheRig` — repeatable margin failure, not a generic flake

**What fails.** `core action 2 is indistinguishable from IDLE`. Action 2 is `ack` (`ACK_NOD`).

**History of the same rig family in CI** (job logs):

| Run | Head | Result |
|---|---|---|
| 36221865661 (PR) | `80f3f0f3` | gate PASS (asset bound, test ran) |
| 36221863531 (push) | `80f3f0f3` (**same SHA**) | FAIL `coreInputsDriveTheRig` |
| 37912462686 | `dfc1557a` | FAIL, action 2: 0.003928 ≤ 0.004 (floor) |
| 39590832158 | `b02075f3` | FAIL, action 2: 0.006014 ≤ 0.009802 (3 × noise) |

Identical input has produced both outcomes, so the result depends on run conditions. The cause sits at the margin:
- `ACK_NOD` keys only `head_drop: 7` in a one-shot 60-frame action that peaks at frame 22 and decays linearly to 0 (`tools/character_forge/build_candidate_b_rive_prototype.py`). Wave and point rotate a forearm 90–178°.
- The idle loop itself breathes (head −1.5, orb −2.5 over 90 frames), which is why idle-vs-idle noise was 0.0033.
- The test samples about 550 ms of wall clock after activity launch, unsynchronised with the animation. Every run logs `Failed to find ColorBuffer` (gfxstream software GPU).
- So the nod's pixel change is of the same order as idle motion, and timing jitter decides the result.
- Rive moved from 9.6.5 to 9.13.10 between `80f3f0f3` and the consolidation. The version change is not required for the failure: the `80f3f0f3` runs used 9.6.5 and already produced both outcomes. Whether 9.13.10 changes the margin is unmeasured.

**Not a test assumption to weaken.** Lowering `MIN_DISTINCT_RGB`, the 3 × noise rule or the action list would weaken the test and is excluded.

**Prepared remedies (not applied):**
1. **Asset, needs Character Forge visual-authority approval.** `patches/0003-character-forge-hold-action-peak.patch` holds every finite action's key pose from frame 22 to 40 (367–667 ms), so the peak covers the capture window.
   - Built with the pinned Rive CLI 1.1.1: exit 0, 190,745 bytes versus a baseline build of 190,514.
   - Device validation is required. The CLI has no headless renderer and this session has no emulator, so the pixel effect is not measured here.
   - The patch changes character motion, so it is a design decision.
2. **Test fidelity, needs `android/` authorization.** Render each frame at a fixed state-machine time (advance the artboard by a fixed dt off-screen) instead of screenshotting after `SystemClock.sleep`. This removes timing jitter without touching any threshold. Design only; the instrumentation code change has to be written and validated on an emulator within the owning unit.

**Validation plan for either remedy:** at least 5 consecutive CI instrumentation runs at the same SHA, recording action-2 `diff` and `threshold` each time. Success means every run passes with diff above threshold by a stated margin. One rerun alone proves nothing.

## 3. character-forge-gate

This gate is downstream of 2b: "Rive asset present means RiveContractTest must have passed". No separate defect.

## 4. project-truth-ledger

Expected on base `main` until PR #94 is adopted (`../ADMISSION_STEPS.md`).
