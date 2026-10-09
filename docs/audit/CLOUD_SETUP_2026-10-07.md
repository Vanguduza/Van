# Prepared cloud environment

Prepared 2026-10-07 using `cloud-environment-onboarding:setup`. The selected checkouts are `/workspace/Van` (`main`) and `/workspace/dial-development-system` (`master`). DIAL's ignored `.projects/dial` checkout is its pinned tenant dependency. No checkout was reset or moved.

## Installed tools

| Tool | Location / validation |
|---|---|
| Python 3.12 venv | `/workspace/.onboarding/van-venv`; exact VAN backend lock installed; `pip check` passed |
| DIAL dependencies | `npm ci`; tenant sync, TypeScript typecheck, core build and representative orchestration qualification passed |
| JDK 21 | `/workspace/.onboarding/jdk/usr/lib/jvm/java-21-openjdk-amd64` |
| Gradle 8.11.1 | `/workspace/.onboarding/gradle-8.11.1/bin/gradle`; archive checksum verified |
| Android SDK | `/workspace/.onboarding/android-sdk`; platform 36, Build Tools 35/36 and platform-tools |
| Writable Android user directory | `/workspace/.onboarding/android-user`; account home remains unchanged |

The SDK command-line archive is `commandlinetools-linux-16111833_latest.zip`, 181052239 bytes, SHA-1 `e025545c62a8e64c7559119566a569fb1dec5f60`, verified against the official HTTPS repository catalog. Reusable installation instructions are saved in `/workspace/.onboarding/install.sh` and the environment configuration draft. Gradle proxy settings contain host/port only.

## Local startup and checks

Use the venv's Python. `/workspace/.onboarding/start-van.py` starts an isolated development gateway at `127.0.0.1:8787`, with SQLite outside the checkout, ephemeral local credentials, scheduler disabled by default, and Hermes pointed at unavailable loopback. It verifies authenticated health before announcing readiness. This does not establish hosted Hermes readiness. `/workspace/.onboarding/van-smoke.py` owns and stops its separate test server.

From `/workspace/Van`, run backend, contracts, Hermes/scenarios and trading suites separately with the core venv. Run native browser services with `/workspace/van-browser-runtime-venv/bin/python`; its hash-pinned media dependencies are isolated from backend pins. Current evidence is in [the final wiring receipt](VAN_WIRING_CLOSURE_VALIDATION_2026-10-07.json) and [local acceptance supplement](validation/wiring-local-acceptance-supplement-2026-10-07.json). Earlier receipts record historical source snapshots.

For the Android JVM harness:

```bash
export JAVA_HOME=/workspace/.onboarding/jdk/usr/lib/jvm/java-21-openjdk-amd64
export GRADLE_USER_HOME=/workspace/.onboarding/gradle
export ANDROID_HOME=/workspace/.onboarding/android-sdk
export ANDROID_USER_HOME=/workspace/.onboarding/android-user
/workspace/.onboarding/gradle-8.11.1/bin/gradle -p android/verification test --offline --no-daemon --max-workers=2 --console=plain
```

The initial online build was blocked by HTTP 403 fetching pinned Sherpa from JitPack. The current runtime resolves that unchanged dependency: app compilation, native packaging, APK assembly, app unit tests and lint pass. The packaged seven arm64 native libraries meet 16 KiB alignment. The actual Gradle release graph refuses missing deployment trust and missing signing; it has not built a signed owner release. Final source validation is recorded in [the wiring receipt](VAN_WIRING_CLOSURE_VALIDATION_2026-10-07.json). Emulator and physical-device acceptance remain unverified, and the owner has deferred handset tests.

Final optional local checks use Pillow 11.3.0 for the retained character reference bytes, workspace-extracted signed/hash-verified rsync for Hermes installer preservation, and `DIAL_REPO=/workspace/dial-development-system` for the read-only resource resolver. An isolated actual PostgreSQL 17.11 fixture also passed and was stopped and removed; its [reproduction note](validation/postgres-ledger-real-fixture-2026-10-07.md) does not bind a production database. The saved setup now prepares the separate media venv and actual rsync without global installation or package scripts. Scope the native-library environment to each rsync/PostgreSQL subprocess as documented in the receipts.

## Saved configuration

The environment draft was confirmed saved. It includes reusable install/start instructions, non-secret Android paths, and the additive custom network domain `jitpack.io`. Saving does not apply or publish it. Review and save the changes in environment settings, then publish the environment to activate the draft and snapshot. A fresh-task restoration has not been independently tested.

The latest saved start instructions include the full app assembly/unit/lint commands and the distinction between local build and live enrollment. The current runtime reports its existing network/SDK paths active; the saved follow-up draft still requires publication. The source corrections authorized by the owner's requests are local and uncommitted. No production deployment, physical owner pairing, broker mutation, live credential installation or Rive redesign was performed.
