# VAN Android qualification — exact `dfc1557a`

Clean source: `dfc1557ab99ad8d41cf84714e1bb671e89b045e6`, in `/workspace/van-audit/canon-chromium-runtime-fix-2026-10-09`. This record qualifies source and an actual debug APK. It does not qualify owner production signing/provisioning, a production connection profile, live host services or S24 acceptance.

| Check | Measured result |
| --- | --- |
| Full contracts | 1,521 passed; 1 Project Truth real-history failure; 5 privileged firewall skips; 0 errors; 0 xfails |
| Actual AGP release guards | Real Gradle rejects missing deployment profile and a valid target without owner signer |
| Standalone Android JVM | 1,282 passed; 0 failures/errors/skips |
| Android app unit tests | 203 passed; 0 failures/errors/skips |
| Debug app assembly | Passed |
| Debug instrumentation assembly | Passed; compiled, never executed |
| Actual lint report | 0 fatal issues, 0 errors, 88 warnings |
| Actual debug APK signature | Verified with the Android Debug signer |
| Signed public APK provenance | Exact final source SHA; route/CA/public trust hashes match compiled BuildConfig |
| Launcher, ABI and version | CommandCentreActivity; arm64-v8a; version 7 / 0.6.0-canon-rc1; minimum SDK 31, target SDK 36 |
| Actual native alignment | Seven ELF libraries and their stored ZIP offsets support 16KiB; SDK zipalign exit 0 |
| Actual voice asset coverage | All 45 source-pinned generic files plus exact compiled-pinned manifest verified inside the APK |
| Physical handset tests | 0 |

All 4,015 tracked source inputs retained their measured bytes and modes throughout contracts and Android qualification. Actual selected DDS dependencies and installed Python dependency bytes stayed unchanged during full contracts. All 46 generic staged assets stayed unchanged during Android qualification. The model transfer verified identical source manifest, compiled pin, acquisition lock and packaging code, used independent destination files, and verified both source and destination against the actual source packager. The public manifest is `7fa17db389349bd587c1f061c7162f9a4c419a552c9d57cd03e8e937bf935e30`; the 45 generic files total 224,852,871 bytes. No owner profile is included.

The full-contract gate remains red solely at `test_the_real_branch_verifies_at_head`, which reports missing historical Project Truth records. No checker, ledger authority or baseline was weakened or reset. Five firewall checks require privileged root/network namespace/nft/setpriv support and were skipped explicitly. Lint produced a real report; its 88 warnings are retained.

Actual fresh debug APK: `/workspace/van-audit/canon-chromium-runtime-fix-2026-10-09/android/app/build/outputs/apk/debug/app-debug.apk`, **317,997,684 bytes**, SHA-256 `afaf6371fb3dd536e37402939b6945a6e4222ff625710e08bb18c64750543c0e`. Signed public provenance SHA-256 `6a8ec624c99376d9d620361c5fa39f46cae8890666a0ac95306adf7280af0a94`. No owner release was built or deployed.

Read-only comparison with the preserved `ffa18d57` APK verified exactly 621 unique ZIP entries in both APKs. Every voice entry and all seven native libraries are byte-identical. The 1,802,562-byte size reduction consists of 1,801,892 bytes of removed unreferenced, almost entirely zero-filled ZIP gaps, 671 fewer compressed payload bytes and one extra byte in local ZIP padding fields. APK signing block, central directory and EOCD sizes are unchanged. Only the public source-provenance JSON and two DEX payloads differ. Both changed DEX files retain the same class definitions, types and method/prototype identities; `classes4.dex` drops two references to Compose-generated `$stable` fields and is 672 bytes smaller. Both DEX files contain their respective correct source SHA. This table comparison does not assert complete bytecode semantics equivalence. No model/native asset is missing and no rebuild was needed. All prior `ffa18d57` receipts and the actual APK were rehashed and remain unchanged.

Immutable evidence:

- [Full contracts result](/workspace/van-audit/canon-final-contracts-dfc1557a-2026-10-09-result.json), SHA-256 `04e075250c9459cd64db81652b5468a5ce3ef48beb18735404e36a1287b3b4dc`; corresponding inputs, actual JUnit and log are preserved. Pytest: 147.07 seconds.
- [Android result](/workspace/van-audit/canon-corrected-android-dfc1557a-2026-10-09-result.json), SHA-256 `4ff7342b85d1d48091d38060da8a74bc33aa65a01c2162261210c969d9ae66fa`; corresponding source inputs, sequential Gradle logs, actual signer and aapt readbacks are preserved. JVM: 52.476 seconds; app: 245.877 seconds.
- [Native ELF/ZIP alignment](/workspace/van-audit/canon-corrected-android-dfc1557a-2026-10-09-native-alignment.json), SHA-256 `6ad7b113d294ca6acdb49becdba4473872c4141852e8e59926b24a136f362817`; includes per-library hashes and actual offsets. [SDK zipalign log](/workspace/van-audit/canon-corrected-android-dfc1557a-2026-10-09-zipalign.log).
- [Independent pinned model transfer](/workspace/van-audit/canon-voice-assets-copy-dfc1557a-2026-10-09.json), SHA-256 `e421f9152d1bd9ef67c18337ead1bf836f1d8b7611d23de76a2c683b94d5ece2`.
- [Actual APK contents and ZIP layout](/workspace/van-audit/canon-android-apk-content-layout-dfc1557a-2026-10-09.json), SHA-256 `b8d9d23052c9f635b297de2891a89faf4c02a0d7a8c81718ee3ab3f8b070685a`; contains every ZIP entry hash/size, all source-pinned voice/native checks and exact file-size decomposition.
- [Bounded DEX identity/layout comparison](/workspace/van-audit/canon-android-apk-dex-layout-dfc1557a-2026-10-09.json), SHA-256 `178d1d43dd8affc38d24a4a95f7c7e72676a3ce32d0a3bc8cea754f9f9cb2f12`.

All Gradle invocations used Gradle 8.11.1, Java 21, the managed Android SDK, two workers and `--no-daemon`, sequentially after the full-contract AGP guards. No tracked edits, chmod, phone install, physical acceptance or production deployment occurred during these qualifications.
