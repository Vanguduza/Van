# Approved unaccepted character-review build

The owner answered **“Proceed”** to the immediately preceding scoped question asking permission to put the refined character into a software-review build without declaring it production-approved. `OWNER_INSTRUCTION.json` records that conversation instruction and exact existing candidate scope. This is not a cryptographic signature or an artwork/independent/native/device acceptance.

## Isolated build and runtime

The dedicated `characterReview` build type is debuggable and uses application ID **com.dial.van.characterreview**, label **VAN Character Review**, and a `-character-review-unaccepted` version suffix. It does not overwrite the ordinary app's package/data namespace and does not claim the normal `van://` deep link. Its rig-lab activity retains the debug DUMP permission. A persistent **Character review — not production accepted** notice appears in its workboard, settings, full workspace and rig lab.

Only this build type receives `van_review.riv`, `van_review.context.json` and `van-character-review.json` in its generated assets. The normal floating `VanAvatar`/`VanRiveAvatar` path and the debug rig lab share one bounded loader. The marker, exact binary/context/request hashes, source commit, build type, separate app ID and complete26-action capability surface must match before the native view is given the review bytes. Missing or changed review files produce the existing truthful fallback, not a silent switch to accepted production assets.

Default debug/release have the review flag **false** and do not inherit review assets. Every variant's packaging depends on a check of its actual merged asset directory. Any review file, or the exact review binary renamed as another `.riv`, is refused outside `characterReview`. Mixed release/review task invocations are refused, and all original release signing, target profile and trust-anchor requirements remain. Nothing changes M0–M5 or creates a final release pass.

## Source reconciliation

`SOURCE_INVENTORY.json` includes the adopted Candidate B master and exact reviewed rig source files. It binds all38 unchanged original image hashes and14 glove derivatives to the existing committed review archive. The original master matches the prior owner identity decision. It records9.13.10 as the actual application/review runtime and explicitly identifies9.6.5 as a stale historical Forge record. It does not set the original global source-complete or independent-visual flags. The candidate's existing native-core proof remains distinct from Android/JNI/backend execution.

The asset generator reads only this exact source packet and owner-scoped request; it writes only the generated review-variant directory. It does not stage into main/debug/release source assets or call a Forge admission function. The existing production Forge path and original acceptance records stay untouched. This approved route is a candidate-review sequence, not an unrecorded alternate release mechanism.

## Build commands

With the original SDK/compiler/dependencies and source-locked voice assets available:

```sh
cd android
./gradlew :app:assembleCharacterReview
./gradlew :app:assembleCharacterReviewAndroidTest -PVAN_INSTRUMENTATION_BUILD_TYPE=characterReview
```

The ordinary `assembleDebug` continues to create the normal nonreview application. Original signed/deployment checks still apply to release. Source and APK provenance must identify the exact commit used; a dirty-parent trial build is not reported as the final committed artifact.

## Verification boundaries

Software tests cover byte binding, scope, context catalogue, failure fallback and generated/merged asset isolation. `CharacterReviewNativeTest` is prepared to import exact review bytes through Android JNI and check actual view texture output. Compiling that instrumentation package is **not** running it. PhysicalS24MotionPerformanceTest accepts the same exact review loader while retaining its explicit physical-handset opt-in. No microphone, phone installation or physical test is run by the generator or Gradle build.

The owner explicitly placed physical testing last. Final physical S24 timing/power/voice/accessibility and owner/artwork acceptance remain separate, unissued stages. This build is suitable for software review; it is not a production approval or proof of industry superiority.
