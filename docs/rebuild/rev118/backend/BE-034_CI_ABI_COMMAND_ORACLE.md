# Instrumentation ABI command oracle

The frozen 9599d695 backend/contracts audit finished with 6,571 passes, 166 skips and one failure. The failing ABI contract split the CI script only at physical lines. It therefore could not find Gradle inside the literal bash diagnostics wrapper, although hosted run 39768283467 demonstrates that the exact instrumentation invocation executed. The failing audit is retained in receipts/SOURCE_QUALIFICATION_9599d695.json, including its successful checkout-storage audit.

The oracle now reads literal shell command arguments and unwraps the supported bash/sh `-c` body. It requires exactly one actual instrumentation Gradle command and exactly one ABI override matching the emulator. Comments, echoes, omitted overrides, wrong values and a later conflicting override all fail. The workflow and its diagnostics remain unchanged. Direct and wrapped positive controls pass.

Twenty CI contracts pass without skips, including an actual opt-in Gradle release-package dry run. Release packaging correctly refuses the missing real van-trading-core production deployment profile. The default handset ABI, test-only x86_64 override and release guards are preserved. No signing key was read and no APK or production qualification is inferred from that refusal. See receipts/CI_ABI_ORACLE_SOURCE_20261022.json.
