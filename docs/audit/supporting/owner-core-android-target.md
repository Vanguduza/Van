# Android owner-core production target

Implemented locally on 2026-10-07. No production deployment, handset execution, or trust
qualification is implied by these build-time checks.

The owner-selected backend is `van-trading-core`, Hermes remains `dial-control`, and the
phone-facing route requires a separate governed VAN-only TLS ingress on `oracle-admin`.
The existing DDS HTTP/SSE proxy does not provide this capability. No public URL, CA,
capability receipt, production signing identity, or connectivity signer was invented.

`android/app/build.gradle.kts` accepts an external `VAN_DEPLOYMENT_PROFILE_FILE` containing
the compiler's `android-owner-core.properties`. Every actual app Release task graph calls
the real `VanProductionTarget` Java validator from `android/buildSrc`. It rejects:

- Missing/legacy profile version or ID, inconsistent host roles, absent ingress receipt ID.
- Private, loopback, historical Netcup `62.83.35.103`, or malformed phone gateway URLs.
- Unqualified implicit/privileged ports; the dedicated profile requires 1024–65535.
- Split URL/CA overrides, absent CA, wrong DER SHA256 fingerprint, non-CA certificates,
  expired/not-yet-valid certificates, or additional private material in the CA payload.

The receipt ID in a build profile is a declaration, not cryptographic or broker admission.
A live deployment must independently resolve its exact immutable scope before applying
the ingress recipe. Automatic signed installer provisioning remains the connection path;
the owner supplies no URL/token/pairing configuration in the app.

The historical dial-control address/CA in `android/van-gateway.properties` is explicitly
debug-only. Debug regression builds remain possible, including exact-loopback HTTP for
local tests. The committed fallback can never qualify a Release task.

Validation:

- Production-code Java probe plus related contracts: 73 passed, 2 opt-in tests skipped,
  5.51 seconds (`android-owner-core-target-tests-final.log`). Synthetic public host names,
  receipt labels, and ephemeral CA keys are test-only inputs.
- Actual AGP direct `packageRelease --dry-run` guards and related ABI contracts: 4 passed,
  33.07 seconds (`android-owner-core-agp-guards-final.log`). The missing deployment profile
  rejects before signing or packaging. A qualified synthetic target passes target validation
  and still refuses missing production signing. These checks compile the final buildSrc
  class; no release artifact was produced. Two ABI cases overlap the portable focused run.
- `git diff --check` passed for changed owned files.

For the configured build environment, debug verification runs `:app:assembleDebug
:app:testDebugUnitTest :app:lintDebug`. An owner release runs `:app:assembleRelease` with
`VAN_DEPLOYMENT_PROFILE_FILE` selecting the reviewed compiler output, production
`android/keystore.properties`, and managed `VAN_CONNECTIVITY_TRUSTED_KEYS`; the profile
alone cannot produce a release. No private key material belongs in the profile or chat.

Root coordinates the final app assemble/unit/lint check after source freeze. Its Android
input manifest must include buildSrc Java and build files in addition to app source.

Owned changes: `android/app/build.gradle.kts`, `android/van-gateway.properties`,
`android/README.md`, `android/buildSrc/build.gradle.kts`,
`android/buildSrc/src/main/java/com/dial/van/buildconfig/VanProductionTarget.java`,
`tests/contracts/test_android_production_target.py`, and aligned release/mTLS/ABI source
contracts. No Android UI routes/selectors were changed in this task.
