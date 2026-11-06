# Exact contextual character package — source review handoff

Status: implemented and software-tested; no actual M2/M3/M4/M5 or artwork/device verdict was granted by the tests.

## Closed implementation gap

The original Forge receipt/staging/integration route copied the .riv file but did not carry the optional metadata enabling codes15–26. The debug lab also exposed only the original14 actions. The continuation now binds and carries that metadata through the same workflow rather than adding a second staging mechanism.

`rive receipt` accepts optional `--context-manifest PATH`. The metadata must be a real, bounded file inside the existing Rive working area, use schema `van.character.context/1`, name the exact candidate SHA256, and contain all12 canonical code/name/duration/original-fallback tuples. Duplicates, changed fields, invalid numeric types, wrong hashes, path escape, symlinks and oversized payloads fail closed. An absent manifest is deliberately legacy mode, never implicit adoption of a nearby file.

Receipts bind the exact path, metadata bytes, length, schema and SHA. Candidate staging revalidates those fields and the original source tree; it copies `van_candidate.riv` together with `van_candidate.context.json` into the original debug/test asset locations only after the original gates permit it. A new legacy package removes stale metadata. Atomic same-directory replacements install metadata last; interrupted copying cannot enable an unrelated binary. Copy-time SHA checking catches a candidate changed after validation.

Normal integration retains its M3 requirement, revalidates the exact staged metadata and installs `van.context.json` beside both canonical .riv copies. M4 verifies that the source and shipped binary/metadata pairs remain identical to the receipt. Release manifests retain the same context SHA. No accepted status, original dependency, owner key, history baseline, test threshold or release gate was weakened.

## Android debug review path

The native review Activity loads the sidecar matching its explicit candidate/production mode and resolves it against the exact bytes loaded. The rig lab displays all26 clips only for a verified full extension. Legacy/missing/stale metadata limits it to the original14; unknown requested codes return to neutral. The fixed-time snapshot host uses the same policy. A private preview view coalesces pending input updates and removes them on detach so stale delayed slider/demo input cannot overwrite a newer selection.

The tests exercise real package functions using isolated temporary fixtures. Fixture gate responses do not grant a real gate and inert byte strings do not constitute runtime animation evidence. Actual Rive software playback remains independently bound to the current a5b848a0… candidate binary.

## Canonical use after original prerequisites are met

Use the existing CLI `rive receipt` with its normal candidate/stage/source-project/artist/source-layer arguments plus `--context-manifest` naming the matching working-area file. Then use the unchanged `rive stage-candidate`, `android integrate` and release commands. They continue to refuse unmet original gates. This document is not an instruction to copy an unadmitted file directly into Android assets.

## Source publication scope

Android/debug catalogue changes are within the existing reusable candidate-source authorization. New Rive authoring files, packaging helper and original Forge CLI/gate deltas remain separately identified review material when their file paths are outside that authorization. Their exact files and tracked patch are retained in the source-review archive. They are not silently treated as production or described as merged simply because an Android commit is published.
