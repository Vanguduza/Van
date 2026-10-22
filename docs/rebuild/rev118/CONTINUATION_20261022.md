# Codex build continuation — 22 October 2026

The owner transferred the build from unavailable Opus to Codex. Recovered branch `ccr-9e07e1af-8mgz1p` at `2a10b7884b9bcf214395d5c15815ab6d96f56845`; no local Opus container files were assumed available. Draft PR: https://github.com/Vanguduza/Van/pull/105. PRs #94 and #104 remain separate pending admission.

## Applied and checked

- `286ca9b4`: append-only authorization intake for the owner's exact continuation instruction. No signature, independent review or gate admission is asserted.
- `6ba1fef7`: escape both template regex closing braces. The host ICU check reproduced both original errors and passes after correction; two explicit Android runtime tests cover route encoding/missing arguments and owner-command unresolved fields/line breaks.
- `eba674ac`: fixed-time Rive instrumentation rendering. The debug renderer overrides the pinned runtime's supported createRenderer/advance interfaces, simulates the existing 250 ms input delay and subsequent time in 60 Hz steps, and freezes the pose. The test waits for a drawn sample instead of equating a wall-clock sleep with animation time. Repeatability checks were added. Original artwork, absolute visibility threshold and 3x noise margin are preserved. Runtime execution is still required to validate the correction.
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

1. Finish reading the instrumentation and build results of Actions run `39709119778`, bound to source `461186ef`. Diagnose any failure before claiming the Rive correction works.
2. Verify the complete committed rebuild submission with `python tools/rebuild/manifest.py check`, run the isolated rebuild suite and consolidation verifier, and verify/push coherent checkpoints with hooks active.
3. Review/admit the selected AP-001/AP-002 candidate using its exact digest and preserved original delivery; independently challenge the requirement dossiers and proposed Product Truth mappings. The 90 forecast hashes are no longer an unresolved finding.
4. Complete native registry/pack readback, valid scope-lock approval and trusted-base admission. #94's README specifies the first framework landing is a one-time owner adoption; no override or fake approval was used here.
5. Issue F15 against the settled baseline/package through the eligible native review process. Follow the full rebaseline/evidence refresh lifecycle at subsequent integration boundaries, not only the first task branch.
6. Implement dependency-ready backend units, their actual service/provider/failure/recovery proofs and BG-001; then execute the prescribed frontend/design, signed release and S24 Artemis programme. None of these later units has been marked complete by the maintenance work.

The 18 remaining policy/provider questions and their 49 verified requirement dependencies are in `pre002/challenge/review/DECISION_REGISTER.json`. That register distinguishes START/exit/activation decisions and states what can proceed before each answer. No financial value, procurement permission, retention duration, provider account or owner signature was selected implicitly.
