# VAN floating assistant — code hardening and closure, 5 November 2026

## Owner scope and acceptance boundary

Owner instruction for this pass: physical testing is the **last stage**; close identified implementation gaps and improvements first. No absent-device check was used to stop source work. This document concerns the implemented candidate, software tests, exact compiler/build receipts and publication. It does not declare production artwork approved, an installed handset test, zero defects, or superiority to another assistant.

All work continues the original VAN PR105 branch and Candidate B character. The 38 original identity PNG files remain unchanged. New rig derivatives, acting and underlap geometry remain explicit review material; original M0–M5 and owner acceptance are not rewritten.

## Implemented code closure

| Area | Implementation and boundary |
|---|---|
| Process-death draft recovery | One encrypted, schema-checked owner/device-scoped local snapshot, seven-day retention, bounded draft size, explicit Resume/Discard and truthful save acknowledgement. A recovered draft is never automatically sent or put into voice capture. An earlier saved draft may predate an abrupt kill; the UI instructs the owner to check conversation/task status before resending. |
| Safe asynchronous persistence | A conflated ordered background writer, monotonic snapshot revisions, error reporting and recoverable manual retry. Replacement-service generation leases prevent an older queued writer overwriting a new session; reads serialize behind any already-active commit. There is no plaintext fallback or automatic provider-command retry. |
| Personalisation | Existing workboard Settings provides Expressive/Balanced/Quiet, owner reduced motion, idle visibility, configurable double tap, encrypted-draft preference and discard/retry. Critical health/approval warnings and explicit guidance are never dimmed or suppressed. System accessibility/thermal ceilings still win. |
| Restart and screen privacy | Restored large boards return to a passive character rather than opening the keyboard or microphone. Keyguard/screen-off hides the own overlay and collapses its board. Live owner/profile changes clear local text and require a fresh session rather than exposing another owner's content. |
| Voice ownership cleanup | The overlay remembers the unique voice turn it started. Close, detach, lock or owner change cancels that UUID only; late cleanup cannot cancel a newer turn started by another screen. Stop voice remains separate from cancelling already-submitted tasks. |
| Speech-to-face timing | Local Sherpa output now reads AudioTrack's played-frame position and the amplitude of PCM actually played, not queued-write offsets. Silent/stalled playback closes the mouth. No modulo15 fake phoneme cycling remains. Real Android spoken-range callbacks supersede estimated cue timing. Generic PCM amplitude is deliberately not called phoneme recognition or measured Bluetooth latency. |
| Native Rive still-mode | Meaningful visible state changes receive a bounded render-thread pose update and then pause. Hidden views do not request updates. Duplicate native snapshots and lip/gaze chatter in still mode do not wake the renderer. Finite pause requests are revision-checked, so an older pause cannot stop resumed motion. |
| Corrupt/oversized input | Rive and metadata assets have during-read size limits; malformed bundles choose the existing fallback. Nonfinite numeric inputs and unsupported original action/viseme values cannot reach the native contract. Optional contextual controls remain bound to the exact loaded asset SHA. |
| Real context adapters | All existing canonical VAN navigation templates classify into19 owned contexts, observed only while the app's destination is resumed. Actual open decisions, refusal/error responses, verified health recovery, listening/thinking/speech, handoff/interruption and owned visible targets feed the existing guarded director. A screen route never supplies execution or approval authority. |
| Target-pointing clarity | The measured target registry, live IK and leases are retained. The current target gets a filled, lease-bound highlight and an accessibility description; disposal, stale geometry or a replacing gesture withdraws it. No external-app content inspection or implicit click is added. |
| Joint and hand mechanics | Original shoulder rebase and four underlaps remain. All five fingers on both original gloves have independent controls; index fingers retain separate proximal/distal controls. Twelve finger controls and14 exact original-pixel partitions replace the earlier grouped non-index fingers, without repainting or replacing the38 identity PNGs. This is not a claim of three anatomical bones on every finger. |
| Complete small-motion catalogue | Sixteen declared categories now have concrete ownership: breathing, hover, single/double blink, micro-saccades, smooth gaze return, four head directions, brow raise/lower, soft smile, shoulder settle, drag counterlean and docking return. They are not16 new always-on animation loops. Body/face channels remain separate from speech, actions and the autonomous orb. |
| Existing usability work retained | Available-space workboards, keyboard/inset clamping, restored character anchor, full virtualized conversation history, revisioned send safety, accessible movement, actual voice controls, reader-priority scrolling, outside-window touch behaviour and the removal of rejected aura arcs/rims remain intact. |

## Evidence tiers — do not conflate them

Software closure is recorded against exact hashes in the accompanying receipt directory. The tests execute real Kotlin sources, original Rive binary playback and original compiler/build tools; no fake Android domain classes, shortened authority history or waived asset gates are used.

The source-level checks and WASM renderer do not establish Android Keystore behaviour, S24 microphone timing, physical touch latency, GPU frame pacing or power consumption. These are deliberately deferred final-stage measurements, not unresolved code placeholders. Normal CI/review and build verification remain software-stage requirements and cannot be replaced by a device test later.

Draft storage is acknowledged only after a completed encrypted commit. No implementation can guarantee saving keystrokes that were never committed before an abrupt OS kill or power loss; the explicit save indicator and recovery review preserve that distinction.

## Software regressions retained

Initial real failures and their corrections are retained: incomplete selected native dependency closure, missing imports and a stale callback name; a missing generated source-locked voice bundle; the original source VM's memory.high throttling during Gradle compilation; source tests that referred to an older implementation location. No failing evidence is relabelled as a pass. The bounded complete-source compiler on the authorized build VM provides a separate exact full-source result.

The generic voice bundle was restored using the original acquisition lock and packager:45public files,224,852,871bytes, no private owner voice profile, no pin/manifest changes. Build relocation transfers only original pinned dependencies, project files and the public generated bundle between the owner's authorized VMs; no credentials, release signing key, resource-limit or service configuration changes are involved.

## Final physical stage (deferred by owner)

After the exact source candidate, APK/native-runtime and artwork package pass their existing software/review gates, perform physical S24 interaction/voice/accessibility, frame-deadline, thermal, memory and battery/soak tests. Verify original owner acceptance for the precise character and build. Do not report those results until actually executed. No device installation, microphone activation, new owner enrollment or physical benchmark was performed in this code pass.

## Packaging closure completed in the resumed pass

The original Forge receipt/stage/integrate/release route now carries exact optional contextual metadata, and native debug review exposes26actions only for its correctly hash-bound asset. Legacy metadata absence safely limits the original14 actions. The same original M2/M3/M4/M5 prerequisites remain mandatory.32isolated package tests passed, covering those gates, stale metadata, exact source/capability pairing, atomic copying, unexpected numeric types, symlinks, excessive files and legacy cleanup. Debug native inputs are coalesced rather than applying obsolete delayed values.

The current focused JVM run passed345tests with zero failed/skipped cases, verified from JUnit XML and exact current source hashes. A retained prior standalone runner failure was corrected by including the real LocalTtsRouter enum source; no stub was introduced. The source-scoped Rive test suites remain45original,151articulation/context and24natural-motion tests against binary a5b848a02887de309d2ee4db2dbc167efaeb123ca0078278155c8b7b4bb8f5dc.

The original Gradle application and instrumentation APK tasks completed successfully on the authorized build VM. The main321,041,411-byte debug APK binds committed application source d78368f2df1426a124072e7e04d703327f229ccd and passed89 actual signature/ZIP/provenance/voice-file/native-library/DEX checks. The2,341,198-byte instrumentation APK has the same debug certificate and actual required test classes; it was not executed. Exact final results and retained failures are in docs/rebuild/rev118/receipts/floating-20261105-apk-software-closure/. The refined Rive remains separate unadmitted review material; the APK uses the existing admitted fallback. The source publication scope remains distinguished from Rive source/artwork admission: the normal Android candidate code and evidence may be committed through their existing receipt; authoring/Forge changes are retained as an exact source-review packet rather than changing publication permissions.

## Exact native-core compatibility continuation

The refined binary additionally passes122checks in the pristine C++ core actually referenced by Android9.13.10. All1,500 source/header/build-rule files match the official Git blobs; all468core C++ files compile. A fresh reproducible build generated53byte-identical native CPU character captures relative to the initial successful run.29tool/provenance/output tests pass. No original upstream code, Rive candidate bytes, Android application bytes or original gate records were changed.

The transport is a diagnostic Cairo renderer, not the Android JNI/Skia/PLS backend; optional text/audio/flex-layout behavior is not qualified. The default empty artboard style is explicitly recorded. This closes the web-versus-pinned-native-core evidence gap without claiming emulator or physical acceptance. Exact results live in docs/rebuild/rev118/receipts/floating-20261105-pinned-native-core/.

Readiness inspection found legacy Forge metadata still naming9.6.5, and the original eight-file source inventory omitting the adopted Candidate B master. Source/layer confirmation and actual emulator/independent/owner records remain unissued. The old flow asks for an S24 core review before full-rig staging, which conflicts with the requested physical-last order. A candidate-only sequencing proposal is documented but NOT approved or executed; final release, signed owner acceptance and physical gates are unchanged.
