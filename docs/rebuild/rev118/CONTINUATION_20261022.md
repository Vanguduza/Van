# Codex build continuation — 22 October 2026

The owner transferred the build from unavailable Opus to Codex. Recovered branch `ccr-9e07e1af-8mgz1p` at `2a10b7884b9bcf214395d5c15815ab6d96f56845`; no local Opus container files were assumed available. Draft PR: https://github.com/Vanguduza/Van/pull/105. PRs #94 and #104 remain separate pending admission.

## Applied and checked

- `286ca9b4`: append-only authorization intake for the owner's exact continuation instruction. No signature, independent review or gate admission is asserted.
- `6ba1fef7`: escape both template regex closing braces. The host ICU check reproduced both original errors and passes after correction; two explicit Android runtime tests cover route encoding/missing arguments and owner-command unresolved fields/line breaks.
- `eba674ac`: fixed-time Rive instrumentation rendering. The debug renderer overrides the pinned runtime's supported createRenderer/advance interfaces, simulates the existing 250 ms input delay and subsequent time in 60 Hz steps, and freezes the pose. The test waits for a drawn sample instead of equating a wall-clock sleep with animation time. Repeatability checks were added. Original artwork, absolute visibility threshold and 3x noise margin are preserved. Hosted runtime proof now passes at source `637eaf96`; see the final result below.
- `461186ef`: ASR acquisition uses three immutable file URLs at the already pinned model repository revision. The mutable upstream archive was republished again at 22:36 UTC on 21 October; its official digest and all selected weights were independently checked. Exact file download avoids repeating that archive-container problem. The voice manifest remains `7fa17db389349bd587c1f061c7162f9a4c419a552c9d57cd03e8e937bf935e30`, 45 files / 224,852,871 bytes, with no owner profile.
- Forecast provenance corrected: all 90 requirement hashes and 48 packet hashes rederive from original bundled JSON records. The previous report searched the wrong representation. No recorded hash or source record was changed. The new verifier rejects six classes of induced provenance corruption.
- AP-002 is now constructed and verified standalone (1,618 identities) and cumulatively with AP-001 (1,632). All ten documentary checks pass for each; thirteen regressions verify preservation and induced failure handling. Neither proposal is admitted. Original requirement, action, lineage and test obligations remain intact.
- Rebuild verification dependencies now have a separate exact-pinned lock and CI job, isolated from gateway and media runtime environments.

Local evidence at maintenance source `461186efbc7f8318468a81187eeb6e46c9a9dd41` is in `receipts/BUILD_VALIDATION_20261022.json`: 1,273 JVM tests; 195 Android app unit tests; debug and instrumentation APK assembly; lint with zero Error/Fatal (80 warnings); 31 rebuild regressions and 14 focused CI/acquisition/ICU regressions. These groups have different scopes and are not Rev1.18 acceptance identities. The debug APK is a development artifact, not an owner-signed release or a handset result.

Branch-local ledger verification covered five commits in `4fd466dec391..461186efbc7f`, GREEN. The earlier receipt covers the prior full history. Trusted-base main admission is a different operation and is still blocked on #94/intake.

## Native admission remains required

The canonical plan's PRE-003 exit requires a valid owner signature and independent current project-scoped F15; all 94 backend/backend-verification units depend on it. The package status itself is a reviewed specification proposal pending native identity and independent admission. The word "admitted" in older tooling variable names means its frozen input path; it does not prove native admission occurred.

No current DIAL/Commander/Artemis tools are exposed. There is no root-signed reviewer identity or scope-lock approval available to this session. The cloud machine has no emulator image or KVM device; native instrumentation runs through GitHub Actions. The hosted backend job also requires a DDS-only read credential. Both ordinary GitHub REST and the supplied `gh` authentication return HTTP 403 for repository-secret administration; permission metadata alone does not grant that access.

`pre003/F15_LIFECYCLE_REVIEW_20261022.md` corrects the earlier identity and signing interpretations. A package UUID and native slug are not inherently a mismatch. The existing source-authorization verifier is not a scope-lock consumer. The native operator must identify a supported approval path or admit an explicit adapter binding the exact lock, package, project, baseline and approval purpose.

## Concrete continuation

1. Hosted results are complete: run `39710993846` tests merge `b2ed4481`, whose tree equals branch head `637eaf96`. Instrumentation: 14 passed, zero failed, four full/production-only skips. Android build/lint, Character Forge core gate, rebuild-documentary jobs pass; mutation success was an invalid advisory result, corrected as described in `ci/MUTATION_VERIFICATION_FINDING.md`. Overall CI still fails on the DDS credential and trusted-base prerequisites. Preserve both initial failures and corrected evidence in `receipts/INSTRUMENTATION_461186ef.json` and `INSTRUMENTATION_637eaf96.json`.
2. Verify the complete committed rebuild submission with `python tools/rebuild/manifest.py check`, run the isolated rebuild suite and consolidation verifier, and verify/push coherent checkpoints with hooks active.
3. Review/admit the selected AP-001/AP-002 candidate using its exact digest and preserved original delivery; independently challenge the requirement dossiers and proposed Product Truth mappings. The 90 forecast hashes are no longer an unresolved finding.
4. Complete native registry/pack readback, valid scope-lock approval and trusted-base admission. #94's README specifies the first framework landing is a one-time owner adoption; no override or fake approval was used here.
5. Issue F15 against the settled baseline/package through the eligible native review process. Follow the full rebaseline/evidence refresh lifecycle at subsequent integration boundaries, not only the first task branch.
6. Implement dependency-ready backend units, their actual service/provider/failure/recovery proofs and BG-001; then execute the prescribed frontend/design, signed release and S24 Artemis programme. None of these later units has been marked complete by the maintenance work.

The 18 remaining policy/provider questions and their 49 verified requirement dependencies are in `pre002/challenge/review/DECISION_REGISTER.json`. That register distinguishes START/exit/activation decisions and states what can proceed before each answer. No financial value, procurement permission, retention duration, provider account or owner signature was selected implicitly.

Final runtime diagnosis: AndroidX 1.6.1 filtered teardown callbacks after production correctly updated its Intent. The test verifies both real deliveries and restores its own launch identity for cleanup. Gaze changed only the visor eyes; measuring that region at the existing visibility floor removes whole-image dilution. Deterministic idle/action samples repeat exactly; no animation asset or action threshold was weakened. The 45-record current intake is in `pre003/MAIN_AUTHORIZATION_INTAKE_CURRENT.json`. The tested cloud refresh installer/start instructions were saved as an environment draft; publication is separate.

Mutation continuation at `5d6372fd`: all 36 original input findings are resolved, all 374 case identities remain (380 edits), and all 32 retargeted cases are assertion-detected after valid controls. Initial survivors, missing dependencies and an invalid Kotlin replacement remain recorded as failed attempts. The shared runner rejects pytest collection and Gradle compilation/setup failures. See `ci/MUTATION_RECONCILIATION.md`, its exact mapping and per-component receipts. Thirty-five focused controls and 52 rebuild regressions pass. Full corpus run `39721114929` is in progress; its browser shard passed 26/26, with no complete corpus score claimed. Native admission, owner decisions and release/handset requirements remain unchanged.


Latest maintenance delta after fca473cc: narrow the duplicate-mission handler to
its exact unique constraint, so post-insert learning/event failures still surface;
100 related backend tests pass. Debug cleartext is restricted to exact loopback,
the main policy explicitly disables it, and the debug rig requires a privileged
caller. Both new Android framework/real HTTP policy tests passed in run39723196572.
The full mutation corpus finished 371/374 with three survivors; all are repaired
and locally detected, without dropping cases (current 374 identities/382 edits).
The resident deep-link test now awaits the exact destination after asynchronous
Intent delivery; all identity/Intent assertions remain. A fresh source CI run is
required. See the current ledger and exact retained receipts, including failures.


Final source verification is complete at c2a27848, run39725953372: all 374 legacy
mutations detected, zero survivors, 382 edits, every original identity exactly
once. Android instrumentation: 16 passed / 0 failed / 4 explicit core-mode skips;
build/lint, Character Forge core and 52 rebuild regressions pass. The only failing
workflow jobs are missing external DDS read credentials and the absent trusted
checker on main. Read CHECKPOINT_c2a27848_20261022.md and the current ledger. The
canonical Rev1.18 programme remains blocked before PRE-003, not completed by this
maintenance. Scope-lock/independent admission, production profile/signing, real
service/provider/firewall evidence and S24 acceptance remain outstanding.

## Autonomous candidate build resumed after f619ddf1

The owner explicitly corrected the stop at native admission. New append-only receipt auth-20261022-owner-autonomous-candidate-build records source construction authority without issuing any certificate, signature or release permission. CLAUDE.md now distinguishes candidate implementation from formal acceptance. CANDIDATE_SOURCE_PROGRESS.json retains all 131 original unit identities/dependencies; no unit is declared complete.

BE-003 storage: reproduced import mkdir side effects in fresh interpreters from root and backend. Implemented lazy compatible ASGI entry point, deferred Store/DocumentService directory creation, absolute development storage outside the checkout, and refusal of missing/relative production paths. Real TestClient startup migrates the configured store and retains ingress authentication. 122 targeted tests pass; broad suite audit is next. No original package bytes changed.

## BE-025 candidate continuation implemented

The actual owner A4 producer, atomic durable grant/status, readback verifier and strict production worker consumer now close the missing same-task source path. Canonical capability declaration and configuration-aware local readiness are included. Existing generic owner commands provide the approval flow; no advisory approval or legacy fixture row creates production authority. 128 focused tests pass, including app restart, same task, double consumption, expiry, revocation, scope changes, stale advisory sync, transaction rollback and paused parent. Fixture/native boundaries and existing screen registry IDs are recorded in backend/BE-025_BROWSER_CONTINUATION.md. No unit acceptance, original-package amendment, deployment or handset result is claimed.

## Trading execution economics candidate corrections

Corrected still-active R05/R07 arithmetic: versioned direct signed fill-cost TCA with submission movement, actual filled quantity/notional and no spread double counting; joint participation/lot/count planning; proper style refusal and entry/exit urgency boundary. Also reproduced and fixed missing costs being treated as zero and conditional medians hiding tail execution costs. Complete objective stream mean is descriptive, not statistical qualification. Full trading source suite: 1576 pass/2 skip. BE-010/012/036 remain partial in-progress units, especially actual qualified child scheduling and durable positive-loop integration. Frozen package and historical ledger facts unchanged.
