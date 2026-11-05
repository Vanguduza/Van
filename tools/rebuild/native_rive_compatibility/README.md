# Pinned native Rive core compatibility

This software check closes the version gap between newer web-runtime tests and the native core referenced by VAN's declared Android dependency. It does **not** integrate a production character or issue a Forge/native/device/owner acceptance.

## Exact source and scope

`SOURCE_LOCK.json` binds the application's actual `app.rive:rive-android:9.13.10` dependency to official Android commit `43fd047149b2656e44664a5da18505d5a0f803cd` and its exact C++ submodule `ff495d263f5ec29d8986dc16d49f5ed8ea22ca33`. The runner checks every original source/header/build-rule file against that Git tree, then compiles all468 original core C++ files without modifying them.

The original core imports the actual `.riv`, evaluates state machines, animation, bones, constraints and skinning, and calls the Renderer interface. The diagnostic Cairo implementation decodes the actual embedded PNG images and draws paths, clips and textured mesh triangles. It does not reconstruct poses from the RML or substitute a fake state machine. An unrelated official vehicles.riv control must render first.

This is native Linux CPU compatibility, **not** the Android JNI/Skia/PLS renderer. Text, audio and flex-layout integration are outside its build scope. The exact candidate has only the default empty artboard layout style, not a flex-layout child hierarchy. Passing this check does not qualify those excluded features, Android lifecycle/threads, GPU output, S24 timing/power or visual owner approval. Singular transforms are handled as empty geometry rather than corrupting Cairo's context; nonzero unsupported feathering is refused, not silently approximated.

## Reproduce

Requires Linux, Python3.10+ with Pillow, CMake3.22+, Ninja, a working Clang C++ compiler, and Cairo headers/shared library. No package installer, network downloader, resource-limit setter, Android asset writer or provider configuration is embedded in the runner. Dependencies may be installed normally by the environment owner or extracted in a private working directory; the actual run used checksum-verified official Ubuntu compiler/header packages without system installation.

Obtain the exact source archive and original Git-tree responses named in SOURCE_LOCK.json. The raw response bytes used to establish the source binding are retained in the evidence archive for deterministic reproduction. Obtain the exact positive-control `.riv`; it is a test-only asset and is never adopted into VAN's artwork. Provide all paths explicitly:

```sh
python3 tools/rebuild/native_rive_compatibility/run.py \
  --source /absolute/path/to/pristine/rive-runtime-ff495d263f5ec29d8986dc16d49f5ed8ea22ca33 \
  --core-tree /absolute/path/to/core-git-tree.json \
  --android-tree /absolute/path/to/android-tag-tree.json \
  --candidate /absolute/path/to/exact-candidate.riv \
  --control /absolute/path/to/vehicles.riv \
  --compiler /absolute/path/to/clang++ \
  --cairo-include /absolute/path/to/cairo/headers \
  --cairo-library /absolute/path/to/libcairo.so.2 \
  --output .git/new-native-compatibility-result
```

Output must be a **new** directory under the repository's existing `.git/` or `evidence/` area. Existing receipts cannot be overwritten, and Android production/debug asset paths are not accepted as output. The complete one-worker build is bounded to15minutes; each actual runtime case is bounded to2minutes. Timeouts and errors stay NOT_PASSED.

The source tree, tool source, candidate and dependency identities are recorded. The positive control and candidate execute the same native probe. The verifier checks the actual trace and emitted PNGs; its122 behavior checks cover the18states,26actions, allfinger controls, cancellation/preemption,16target directions and retargeting, independent orb travel, speech shapes and sleep/blink behavior. The test count is not a performance metric.

`verify_result.py` can independently recheck retained traces and captures without recompiling. `test_native_rive_compatibility_tool.py` tests provenance, failure and output isolation with temporary fixtures; those fixtures are not represented as native runtime proof.

## Admission stays separate

The runner never imports or calls Forge source confirmation, independent review, native/CI validation or release promotion functions. It cannot record M0–M5 PASS, an owner verdict or a device result. Existing source/layer/toolchain admission and exact Android-native/CI evidence remain mandatory for canonical application integration. The admitted fallback APK is unchanged by this diagnostic.

Upstream code remains attributable to Rive under its repository license; this directory contains the local Renderer adapter and verification code, not a redistributed runtime library or font.
