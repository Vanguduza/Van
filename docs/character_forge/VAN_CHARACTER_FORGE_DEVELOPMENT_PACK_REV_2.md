# VAN Character Forge — Deterministic Development Pack, Rev 2

Pack ID: `VAN-CHARACTER-FORGE-DP-R2`
Project: VAN · Subsystem: Character Forge · Supersedes: `VAN-CHARACTER-FORGE-DP-R1` (never executed)
Canonical repository: `Vanguduza/Van` · Canonical branch: `main`
Baseline SHA at pack compilation: `f36c929d39a5056b2a0480d6d8adf77b60152ea8` (recapture at execution start; see M0)
Primary runtime target: Samsung Galaxy S24 Ultra · CI validation target: API 31 x86_64 emulator (`pixel_6`, `google_apis`)
Final production artifact: `android/app/src/main/assets/van.riv`
Canonical source artifact: `visual-authority/rive/van_runtime.riv`
Canonical artboard / state machine: `Van` / `VanRuntime`
Authority: OWNER_VISUAL_AUTHORITY → CHARACTER_FORGE_BOUNDED_PRODUCTION → VAN_RUNTIME
BUILD_READY at compilation: `false` (M0 flips it; §6)

This document is written to be executed by any agent or person without interpretation. Where it says MUST, a contract test or a gate enforces it. Where it names a path, the path is exact. Where the repository already has something, the pack says so and forbids rebuilding it. If reality and this pack disagree, §22 says what to do.

---

## 0. Read this first: what already exists (do not rebuild)

Every item below is present at the baseline SHA. An implementer who recreates any of them has drifted.

| Thing | Where | Status |
|---|---|---|
| Public Rive wire contract | `visual-authority/rive_contract.json` | Locked: 9 inputs, 8 triggers, 18 durable states (0–17), 14 finite actions (1–14), identity lock with forbid list |
| Human-readable contract | `docs/RIVE_CHARACTER_CONTRACT.md` | Same content as the JSON; the JSON is authoritative |
| Kotlin binding | `android/app/src/main/java/com/dial/van/visual/RiveContract.kt` (`VanDurableState`, `VanFiniteAction`, `VanTrigger`, `VanInput`, `RiveBindingContract` with `ARTBOARD="Van"`, `STATE_MACHINE="VanRuntime"`, `ASSET_FILE="van.riv"`) | Bound to the JSON by `tests/contracts/test_rive_contract.py` |
| Rive playback | `android/app/src/main/java/com/dial/van/visual/VanRiveAvatar.kt` (`setRiveBytes`, `setNumberState`, `setBooleanState`) | Loads `assets/van.riv`; calls `onLoadFailed` on any throwable |
| Renderer order and fail-closed decision | `android/app/src/main/java/com/dial/van/visual/VanVisualRuntime.kt` `decide()`: RIVE → OWNER_ART → CANVAS; `MIN_ARTBOARD_BYTES = 1024` | Reasons: ASSET_MISSING, ASSET_UNUSABLE, RUNTIME_UNAVAILABLE, LOAD_FAILED |
| Renderer status to the owner | `visual/VanRendererStatus.kt` via `DegradedBridge`; Settings "Character" row | Live |
| Rive runtime | `android/app/build.gradle.kts` line 251: `app.rive:rive-android:9.6.5` | Pinned |
| Owner source art | `visual-authority/assets/` (turnaround.png, expressions.png, gestures.png, presentation.png, owner_visual_lock_sheet.jpg, compact_avatar.png, urgent_decision.png, offline_degraded.png, command_centre.png, onboarding_hero.png, icons) plus `assets/derived/` state renders and `assets/pack/` owner boards | Present; unhashed |
| Identity canon | `docs/VAN_CHARACTER_VISUAL_IDENTITY.md`, `visual-authority/van-visual-authority-v2.yaml` (aura v2.3) | Canon; the aura is Android-native and stays out of the `.riv` |
| Acceptance criteria | `docs/VAN_VISUAL_ACCEPTANCE_MATRIX.md` (identity, presence, floating UX, physical Samsung checklist) | Canon; this pack references, never restates |
| Authoring handoff | `docs/VAN_RIVE_AUTHORING_HANDOFF.md` | Superseded by §11–§13 of this pack; update it to point here in M0 |
| Emulator instrumentation | `.github/workflows/van-ci.yml` job `android-instrumentation`; tests in `android/app/src/androidTest/java/com/dial/van/instrumentation/`; screenshots via AGP `additionalTestOutputDir` → artifact `van-instrumentation-screenshots` | Green at baseline; this is the validator host |
| Geometry evidence | `van-ci.yml` job `android-and-visual-evidence` step `:visual-preview:renderVanPreviews` → artifact `van-visual-evidence` | Green at baseline |
| Owner cryptographic authority | `android/app/src/main/java/com/dial/van/security/OwnerApprovalKeyManager.kt` `prepareOwnerAuthority(act, subject, issuedAtUnix, lifetimeSeconds)`; `OwnerAuthorityToken.kt` (canonical = act, subject, keyId, issued-at, expires-at joined by `\|`; `Prepared.assembleFromSignatureBase64`); biometric signing via `security/BiometricGate.requestA4CommandApproval`; gateway-side verification via `vati.authority.OwnerAuthorityVerifier` (used by `backend/van_gateway/trading/service.py` for act `owner-halt`) | Live; reused for owner acceptance (§15) |
| Release identity | `tools/ci/record_apk_signing_identity.sh` (apksigner certs of the built APK) | Live; extended in §16 |
| Truth ledgers | `evidence/van-system-audit/findings.json` + `tools/ci/maturity_gate.py`; `docs/audit/van-fable-whole-project-2026-09-21/VAN_RUNTIME_QUALIFICATION_MATRIX.md` row `QUAL-EMB-01` = EXTERNAL_ARTEFACT | The only gap: no asset |
| Speech timing | `backend/van_gateway/voice/speech_cues.py` (`SpeechCueClock`) → device `voice/SpeechCueTiming.kt`; visemes 0–4 and `mouth_open` | Live; the rig follows this, not a third tool |

Consequence: Character Forge Rev 2 is the work between "source art in the repository" and "owner-accepted `van.riv` shipped with provenance". Nothing else.

---

## 1. Executive contract

Character Forge converts the locked VAN identity and the locked wire contract into a reproducible, inspectable, owner-accepted `.riv`, and binds that exact file to a release.

It is not: a second runtime, a second visual authority, a redesign agent, an image-generation service, a replacement for the Android aura, or a way for learned behaviour to widen authority.

Causal path (each arrow is a gate with evidence):

```
owner source art (hashed)  →  layer/vector pack (lint-clean)  →  core rig .riv (packaging receipt)
  →  emulator validation (contract + core matrix)  →  owner core verdict on S24
  →  full rig .riv  →  emulator validation (full matrix, combinations, invalid inputs, soak)
  →  production asset + CI green (Rive selected; fallback proven)  →  S24 checklist
  →  owner acceptance receipt (signed, bound to SHA-256)  →  release manifest  →  QUAL-EMB-01 READY
```

A polished `.riv` without this chain is a milestone, not completion.

---

## 2. Requirements (each with its proof)

| ID | Requirement | Proven by |
|---|---|---|
| CF-R-01 | Produce `visual-authority/rive/van_runtime.riv` and ship it as `android/app/src/main/assets/van.riv`, byte-identical | `test_character_forge_release.py::test_shipped_asset_matches_source` (SHA-256 equality) |
| CF-R-02 | Preserve the identity lock in `rive_contract.json` (`identity_lock`, `forbid`) | Owner core verdict (M2) and acceptance receipt (M4); automated colour-family check on emulator frames (§10.5) |
| CF-R-03 | Owner Visual Authority outranks every generated or artistic alternative | No promotion path exists without an acceptance receipt: `test_character_forge_release.py::test_release_requires_acceptance_receipt` |
| CF-R-04 | Every accepted artifact is identified by SHA-256 and immutable after acceptance | `MANIFEST.yaml` hashes checked against the tree on every CI run |
| CF-R-05 | AI produces candidates only; never promotes | Promotion CLI requires a receipt; lanes (§7) have no write path to `visual-authority/rive/` |
| CF-R-06 | Named layer pack per §11 with lint-clean SVG | `test_character_forge_svg.py` |
| CF-R-07 | Rig implements gaze, blink, speech (visemes 0–4 + `mouth_open`), orb, breathing | Emulator test `RiveContractTest.coreInputsDriveTheRig` frames |
| CF-R-08 | All 18 durable states and 14 finite actions implemented | Emulator test `RiveContractTest.everyStateAndActionRenders` (36 frames) |
| CF-R-09 | Public input names, types, artboard and state machine do not drift | `RiveContractTest.contractSurfaceMatches` (asserts against `rive_contract.json` embedded in the test APK) |
| CF-R-10 | Core rig qualified on the S24 before full animation | `STATUS.json.core_rig.owner_verdict == "PASS"` required by M3 gate; enforced by `cli gate m3` |
| CF-R-11 | Aura stays Android-native; the `.riv` has a transparent artboard and no full-artboard effects | `RiveContractTest.artboardIsTransparentOnThreeBackgrounds` (corner-pixel alpha check) |
| CF-R-12 | Invalid wire values never corrupt rendering | `RiveContractTest.invalidInputsDegradeSafely` |
| CF-R-13 | Performance judged in the real composition | `RiveContractTest.idleSoakFrameStats` (`dumpsys gfxinfo`, janky-frame percentage recorded) |
| CF-R-14 | Fallback preserved: deliberately broken asset selects OWNER_ART/CANVAS | Existing `VanVisualRuntime.decide` tests + `RiveContractTest.brokenAssetFallsBack` |
| CF-R-15 | Never report READY before asset, device and owner gates pass | `STATUS.json` vocabulary (§18) + `test_character_forge_status.py` |
| CF-R-16 | Tool versions pinned; editor export loadable by rive-android 9.6.5 | `TOOLS.yaml` checked against `build.gradle.kts` pin; emulator load is the compatibility proof |
| CF-R-17 | Provenance across the editor step | Packaging receipt (§14) required before validation runs |
| CF-R-18 | Promotion records actor, hashes, evidence, reason | `ACCEPTANCE.yaml` + release manifest schema (§16) |
| CF-R-19 | Gates can fail | Mutation tests (§19) |
| CF-R-20 | Status retrievable by future agents without this conversation | `docs/character_forge/STATUS.json` + this pack |

Forty requirements in Rev 1 collapse to twenty because the other twenty were either already satisfied by the repository (§0) or were properties of tools that are no longer on the critical path (§7).

---

## 3. Authority map

| Actor | May | May not |
|---|---|---|
| Owner | change identity; admit source art; give the core verdict; accept the final asset on the S24; reject anything | be substituted by any other actor |
| Rive artist (human) | vectorize, rig, animate within the identity lock and contract; reject AI suggestions | add, rename or remap public inputs/triggers; change identity |
| Forge CLI (`tools/character_forge`) | hash, lint, write manifests/receipts/status, copy an accepted asset into `assets/`, gate milestones | mark anything accepted; edit `rive_contract.json` |
| CI (`van-ci.yml`) | validate contract, render evidence, measure frames, fail | accept |
| AI production agents (optional lanes) | propose reconstructions, masks, vector cleanups, motion references | write to `visual-authority/rive/` or `android/app/src/main/assets/`; certify their own output |
| Hermes | read `STATUS.json` and evidence; open work items | promote; sign; alter authority |
| Independent reviewer (agent or person not the author) | compare frames to the lock; reject a milestone | be the same session that produced the candidate |

Enforcement: the only writer of `ACCEPTANCE.yaml` is `cli owner record-acceptance`, which refuses without a verified owner token (§15). The only writer of `android/app/src/main/assets/van.riv` is `cli android integrate`, which refuses without `STATUS.json.full_rig.emulator_validation == "PASS"`.

---

## 4. Decisions

| ID | Decision | Rev 1 → Rev 2 change |
|---|---|---|
| CF-D-01 | The Android runtime on the CI emulator is the only contract validator | Replaces a desktop parser and a separate evidence engine |
| CF-D-02 | **Rev 2.1 amendment:** the pinned Linux x86_64 Rive CLI is the deterministic M2/M3 authoring/build authority on Netcup DIAL control. The Rive Editor is an optional human visual-review lane, not a build dependency. All candidates must still load under rive-android 9.6.5 and pass the Android-runtime validator. | Supersedes the Rev 2 Editor-only authoring requirement so the full build can be Commander-orchestrated on Linux |
| CF-D-03 | **Rev 2.1 amendment:** minimal deterministic path is owner lock/source → Inkscape/vector layer sheet → pinned Rive CLI → Android emulator validator. Image reconstruction, segmentation, Blender and web-Editor tooling may be installed on the workstation but are optional lanes and never become milestone prerequisites merely by being present. | Preserves the minimal critical-path rule while allowing a fully equipped Netcup workstation |
| CF-D-04 | Candidates are validated from the test APK (`androidTest/assets/van_candidate.riv`); the production asset changes only at M4 | New: candidates never touch the product |
| CF-D-05 | Owner acceptance is an `OwnerAuthorityToken` (act `visual-accept`, subject `sha256:<hex>`) signed under biometrics on the device and verified by the gateway with the same verifier used for `owner-halt` | Replaces a YAML line |
| CF-D-06 | Two artifact fields, `stage` and `promotion`, replace three state machines | Simplification |
| CF-D-07 | No Forge UI, no controller API in Rev 2; CLI + `STATUS.json` + the device's Settings "Character" row | Deletes 10 screens and 10 endpoints |
| CF-D-08 | Five machine-readable files, enforced by contract tests and the existing maturity gate | Replaces 27 files and a bespoke checker |
| CF-D-09 | Speech QA follows the gateway's cue track (visemes 0–4, `mouth_open`) | Rhubarb optional |
| CF-D-10 | Gates are per milestone; nothing on the critical path waits on a lane prerequisite | Replaces the all-13-gates-before-anything rule |
| CF-D-11 | A rive-android version change re-runs M2–M4 | New |

---

## 5. Artifact model

Every artifact has:

```
artifact_id: <kind>:<sha256>
kind:        source | layer_svg | riv_candidate | riv_accepted | packaging_receipt | frame | frame_stats | acceptance | release_manifest
path:        repository-relative
sha256:      hex
stage:       admitted | vector | core_rig | full_rig | integrated | certified | released
promotion:   CANDIDATE | REVIEWED | OWNER_ACCEPTED | RELEASED | REJECTED | SUPERSEDED
produced_by: owner | artist:<name> | cli:<command> | ci:<job>#<run> | lane:<id>
inputs:      [artifact_id]
```

Rules: a `sha256` never changes for a given `artifact_id`; a new file is a new artifact and the old one becomes SUPERSEDED; `promotion` only advances through the CLI commands in §9; nothing is inferred from file presence.

---

## 6. Milestones (the critical path)

Each milestone lists inputs, the work, exact commands, the gate, the evidence, and what must not happen. `cli gate <m>` implements the gate; CI runs the same checks.

### M0 — Admission (Forge CLI; half a day)

Inputs: the baseline tree.

Work:
1. Recapture the SHA: `git rev-parse HEAD` on `main` at execution start; write it to `STATUS.json.baseline_sha`.
2. Create the layout in §8 and the five machine-readable files.
3. `python -m tools.character_forge.cli source admit` hashes every file under `visual-authority/assets/**`, `visual-authority/rive_contract.json`, `docs/VAN_CHARACTER_VISUAL_IDENTITY.md`, `docs/VAN_VISUAL_ACCEPTANCE_MATRIX.md` into `MANIFEST.yaml`. The owner confirms (a line in `MANIFEST.yaml`: `owner_confirmed_complete: true`, with date) that this set is the complete authoritative source. Until that line exists the manifest is `PROVISIONAL`.
4. `TOOLS.yaml`: `rive_android: "9.6.5"` (must equal the gradle pin; the test reads the gradle file), `rive_editor: "<version the artist will use>"` (may be `UNPINNED` until M2 starts; M2 gate requires a value), `inkscape: "<version>"`.
5. Extend `tests/contracts/test_rive_contract.py`: if `visual-authority/rive/van_runtime.riv` exists, its SHA must appear in `MANIFEST.yaml` and `van_runtime.sha256` must match; if `android/app/src/main/assets/van.riv` exists, it must be byte-identical to the source asset.
6. Add `tests/contracts/test_character_forge_manifest.py`: every path in `MANIFEST.yaml` exists and hashes match; every hashed source file is listed (no unlisted file under the hashed roots).
7. Rewrite `docs/VAN_RIVE_AUTHORING_HANDOFF.md` to a pointer at this pack (§11–§14).

Gate M0 (all true): baseline SHA recorded; manifest hashes verified; `TOOLS.yaml.rive_android` equals the gradle pin; contract tests green; `STATUS.json.build_ready == true`.

Evidence: `MANIFEST.yaml`, `STATUS.json`, CI run URL.

Must not: touch `rive_contract.json`; touch `android/app/src/main/assets/`.

### M1 — Layer and vector pack (artist; Inkscape; lanes optional)

Inputs: `MANIFEST.yaml` sources, identity lock, §11 layer list.

Work: produce `visual-authority/character-forge/06-vectors-clean/van_layers.svg` (one file, named groups) plus per-layer exports if the artist prefers; every group id from §11 present; palette within the identity lock families; no raster payloads, no external references.

Commands:
```
python -m tools.character_forge.cli vectors lint visual-authority/character-forge/06-vectors-clean/van_layers.svg
python -m tools.character_forge.cli vectors admit visual-authority/character-forge/06-vectors-clean/van_layers.svg
```
`admit` writes the artifact (kind `layer_svg`, stage `vector`, promotion `CANDIDATE`) to `MANIFEST.yaml` and renders `10-validation/layer_sheet.png` (every group on its own tile, plus the composite) for review.

Gate M1: lint clean; every required group present; `layer_sheet.png` reviewed by the owner or an independent reviewer with a `REVIEWED` line in `MANIFEST.yaml` (`reviewed_by`, `date`, `verdict: PASS`).

Must not: vectorize the character as one flat path; introduce colours outside the lock families; hand-write the review line without a real review.

### M2 — Core rig (Rive artist) and core device verdict (owner)

Inputs: admitted `van_layers.svg`, `rive_contract.json`, §12.

Work:
1. In the Rive Editor (version recorded in `TOOLS.yaml` before starting), build artboard `Van` with state machine `VanRuntime`, all nine inputs and eight triggers with exact names and types, and only the §12 core scope.
2. Export `visual-authority/character-forge/09-rive-working/van_runtime_core_<n>.riv`.
3. Write the packaging receipt (§14): `cli rive receipt --candidate <path> --editor-version <v> --rive-file-id <id> --rive-revision <rev> --svg-sha <sha> --artist <name>`.
4. `cli rive stage-candidate <path>` copies the file to `android/app/src/androidTest/assets/van_candidate.riv` and records it (kind `riv_candidate`, stage `core_rig`).
5. Push; CI runs `RiveContractTest` (§10) in `core` mode (chosen by `STATUS.json.current_stage`).
6. Install the CI debug APK on the S24 (artifact `van-debug-apk`). The app keeps rendering OWNER_ART/CANVAS in production (the candidate is only in the test APK), so the owner views the core rig through the instrumentation frames and through the debug host screen `RiveCandidateHost` (§10.6), which renders the candidate at overlay size, minimized-portrait crop, and full size on the device.
7. Owner records the core verdict: `cli owner record-core-verdict --verdict PASS|REVISE|REJECT --notes "..."` (plain record; the cryptographic receipt is reserved for final acceptance).

Gate M2: `RiveContractTest` core mode green; packaging receipt present; `STATUS.json.core_rig.owner_verdict == "PASS"`.

Must not: add states or actions beyond §12; restructure the skeleton after PASS without returning to this gate.

### M3 — Full authoring (Rive artist)

Inputs: PASSed core rig; §13.

Work: implement the remaining 14 durable states and 11 finite actions on the unchanged skeleton; keep the core behaviours; export `van_runtime_full_<n>.riv`; receipt; stage as candidate; push.

Gate M3: `RiveContractTest` full mode green: contract surface, 18 state frames, 14 action frames, 10 combinations, 4 gaze extremes, 5 visemes, invalid-input sweep, three backgrounds, idle soak with janky-frame percentage ≤ the threshold in `STATUS.json.performance.max_janky_percent` (default 5.0); independent reviewer line `full_rig.reviewed: PASS` in `MANIFEST.yaml`.

Must not: change any public input; duplicate the character per state (§12.3); regress the core frames (CI diffs core frames against the M2 baseline images stored under `11-device-evidence/core_baseline/` with a tolerance; a diff above tolerance fails).

### M4 — Integration, certification and owner acceptance

Work:
1. `cli android integrate --candidate <path>`: refuses unless `STATUS.json.full_rig.emulator_validation == "PASS"`; copies the candidate to `visual-authority/rive/van_runtime.riv`, writes `van_runtime.sha256`, copies byte-identical to `android/app/src/main/assets/van.riv`, records lineage in `MANIFEST.yaml`, sets stage `integrated`.
2. Push; CI runs everything: existing jobs plus `RiveContractTest` in `production` mode (loads from app assets, asserts `VanVisualRuntime.decide` chooses RIVE, then `brokenAssetFallsBack`).
3. Install the CI debug APK on the S24. Walk `docs/VAN_VISUAL_ACCEPTANCE_MATRIX.md` "Physical Samsung re-verification checklist" plus the Rive rows in §17; record results in `DEVICE_CHECKLIST.yaml` with device model, Android build, APK SHA, Rive SHA, date.
4. Owner acceptance on the device: Settings → Character → "Accept this character asset" (new control, §15). The device mints `OwnerAuthorityToken(act="visual-accept", subject="sha256:<rive sha>")` under biometrics, posts it to `POST /v1/visual/acceptance`; the gateway verifies and stores it.
5. `cli owner record-acceptance --from-gateway` pulls the verified record into `ACCEPTANCE.yaml`. Offline alternative: `--token <string> --device-public-key <pem>` verifies locally with the same canonical.

Gate M4: CI green (including production-mode `RiveContractTest`); `DEVICE_CHECKLIST.yaml` complete with no FAIL; `ACCEPTANCE.yaml` contains a verified token whose subject equals the SHA of both `van_runtime.riv` and `assets/van.riv`.

Must not: integrate an asset that differs from the last emulator-validated candidate (the CLI compares SHAs); write `ACCEPTANCE.yaml` by hand.

### M5 — Release binding

Work:
1. `cli release promote`: refuses unless M4 gate holds; writes `visual-authority/rive/manifest.json` (§16), sets promotion `RELEASED`, sets `STATUS.json` vocabulary to the final row of §18, and updates `QUAL-EMB-01` in `docs/audit/van-fable-whole-project-2026-09-21/VAN_RUNTIME_QUALIFICATION_MATRIX.md` to READY with the SHA.
2. `tools/ci/record_apk_signing_identity.sh` additionally emits `rive_sha256` (SHA of `assets/van.riv` inside the APK) next to the signing identity; CI uploads it.
3. Add the Character Forge component rows to `evidence/van-system-audit/findings.json` (or the ledger the maturity gate reads) so the maturity gate covers them.

Gate M5: `test_character_forge_release.py` green; maturity gate green; CI green on the release commit.

---

## 7. Optional lanes (never on the critical path)

Each lane has its own prerequisites, produces candidates only, and writes only under `visual-authority/character-forge/02-…/05-…` and `08-…`. A lane's output enters the critical path only by the artist admitting it at M1.

| Lane | Tools | Prerequisites before any run | Output |
|---|---|---|---|
| L1 AI reconstruction (hidden geometry, hand poses, expression references) | ComfyUI with pinned JSON workflows, admitted model hashes, GPU worker | GPU environment certificate; worker holds no production secrets; egress denied except admitted model fetch; every run records workflow/model/seed/input/output hashes | candidates under `02-ai-working/` |
| L2 Segmentation assistance | SAM2 or BiRefNet | Same isolation; mask validator (§11.3) | masks under `03-masks/`, raster layers under `04-raster-layers/` |
| L3 Motion and rig research | Inochi2D, Blender + MCP in a disposable sandbox, co-rive | Sandbox with no home mount, no secrets, restricted network | references under `07-inochi/`, `08-blender/`; research notes |

Lane tools are recorded in `TOOLS.yaml` with `class: LANE` and are not required for BUILD_READY.

---

## 8. Repository layout to create

```
docs/character_forge/
├── VAN_CHARACTER_FORGE_DEVELOPMENT_PACK_REV_2.md   (this file)
├── MANIFEST.yaml          sources, artifacts, hashes, reviews, lineage
├── STATUS.json            stage, gates, blockers, SHAs, vocabulary (§18)
├── TOOLS.yaml             pins and licences for tools actually used
├── ACCEPTANCE.yaml        owner core verdicts and the verified acceptance token
└── DEVICE_CHECKLIST.yaml  S24 results with device identity and SHAs

visual-authority/
├── rive_contract.json                       (unchanged)
├── rive/
│   ├── van_runtime.riv                       M4
│   ├── van_runtime.sha256                    M4
│   └── manifest.json                         M5 (§16)
└── character-forge/
    ├── 00-source/            symlinks or copies are NOT made; sources stay in visual-authority/assets and are referenced by hash
    ├── 02-ai-working/        L1 only
    ├── 03-masks/             L2 only
    ├── 04-raster-layers/     L2 only
    ├── 06-vectors-clean/     van_layers.svg (M1)
    ├── 07-inochi/            L3 only
    ├── 08-blender/           L3 only
    ├── 09-rive-working/      van_runtime_core_<n>.riv, van_runtime_full_<n>.riv, receipts
    ├── 10-validation/        layer_sheet.png, svg lint reports
    └── 11-device-evidence/   core_baseline/, S24 screenshots and clips referenced by DEVICE_CHECKLIST.yaml

tools/character_forge/
├── __init__.py
├── cli.py            argparse entry: source, vectors, rive, gate, android, owner, release, status
├── manifest.py       load/save/validate MANIFEST.yaml; hashing (SHA-256, streaming)
├── svg_lint.py       §11.2 rules; returns findings
├── receipts.py       packaging receipt and acceptance record models + validation
├── status.py         STATUS.json model and vocabulary transitions
├── gates.py          gate m0..m5 predicates (pure; used by cli and tests)
└── README.md         one screen: how to run each milestone

tests/contracts/
├── test_character_forge_manifest.py
├── test_character_forge_svg.py
├── test_character_forge_status.py
├── test_character_forge_release.py
└── test_character_forge_mutations.py

android/app/src/androidTest/
├── assets/van_candidate.riv                   staged candidate (M2/M3); absent at baseline
├── assets/rive_contract.json                  copied by `cli rive stage-candidate` from visual-authority (test reads it)
└── java/com/dial/van/instrumentation/RiveContractTest.kt   §10

android/app/src/main/java/com/dial/van/visual/RiveCandidateHost.kt   debug-only host screen (§10.6), reachable from Settings → Character in debug builds
```

No `ui/`, no `api.py`, no `controller.py`, no adapters on the critical path.

---

## 9. CLI contract

`python -m tools.character_forge.cli <group> <command> [args]`. Every state-changing command appends a receipt line to `MANIFEST.yaml.receipts` (`command`, `actor` (`$USER` or `--actor`), `inputs` hashes, `outputs` hashes, `timestamp`) and rewrites `STATUS.json`. Commands are idempotent: re-running with identical inputs changes nothing and exits 0 with `NO_CHANGE`.

| Command | Effect | Refuses when |
|---|---|---|
| `status` | prints `STATUS.json` and the next required action | never |
| `source admit` | hashes source roots into `MANIFEST.yaml` | a listed file is missing |
| `vectors lint <svg>` | prints findings; exit 1 on any | — |
| `vectors admit <svg>` | records the layer artifact; renders `layer_sheet.png` | lint fails; required group missing |
| `rive receipt …` | writes `09-rive-working/<candidate>.receipt.json` | any field missing; `svg-sha` not an admitted layer artifact |
| `rive stage-candidate <riv>` | copies to `androidTest/assets/van_candidate.riv`; copies contract JSON beside it; sets `current_stage` (`core_rig` or `full_rig` from `--stage`) | no receipt for that SHA; size < 1024 bytes |
| `gate m0..m5` | evaluates the milestone predicate; exit 0/1 with reasons | — |
| `owner record-core-verdict --verdict … --notes …` | writes `ACCEPTANCE.yaml.core_rig` | no staged core candidate; CI evidence for its SHA absent (`--ci-run <url>` required) |
| `android integrate --candidate <riv>` | copies to source and production assets; writes sha256; lineage | `STATUS.json.full_rig.emulator_validation != "PASS"`; SHA differs from the validated candidate |
| `owner record-acceptance --from-gateway \| --token … --device-public-key …` | verifies and writes `ACCEPTANCE.yaml.final` | signature invalid; subject SHA ≠ integrated asset SHA; act ≠ `visual-accept` |
| `release promote` | writes `rive/manifest.json`; flips vocabulary; updates QUAL-EMB-01 | gate m4 false |

Exit codes: 0 success/no change, 1 gate or validation failure, 2 usage. Output is plain text plus `--json`.

---

## 10. Emulator validator: `RiveContractTest`

Location: `android/app/src/androidTest/java/com/dial/van/instrumentation/RiveContractTest.kt`. Runs in the existing `android-instrumentation` job. Mode is read from `androidTest/assets/forge_mode.txt` written by `cli rive stage-candidate` (`core`, `full`) or `production` when `assets/van.riv` exists in the app APK and no candidate is staged. If neither a candidate nor a production asset exists, every test is `Assume`-skipped with the reason `NO_RIVE_ASSET` (skipped, never passed).

### 10.1 Loading

- Candidate: `InstrumentationRegistry.getInstrumentation().context.assets.open("van_candidate.riv")`.
- Production: `targetContext.assets.open(RiveBindingContract.ASSET_FILE)`.
- Parse with the rive-android 9.6.5 API (`app.rive.runtime.kotlin.core.File(bytes)`, `artboard("Van")`, `stateMachine("VanRuntime")`; adapt call names to the 9.6.5 API if they differ, keep the assertions).

### 10.2 `contractSurfaceMatches`

Read `rive_contract.json` from the test assets. Assert: artboard `Van` exists; state machine `VanRuntime` exists; the set of input names equals the contract's nine names, each with the contract's type (`number` ↔ SMINumber, `boolean` ↔ SMIBoolean); the set of trigger names equals the eight contract triggers; no additional public inputs or triggers (an extra one fails; it is contract drift).

### 10.3 Frame capture

A test host composable `RiveCandidateHost` renders `VanRiveAvatar` from the given bytes at three sizes (overlay 96 dp, minimized portrait 48 dp circular crop, full 320 dp) over a chosen background (light `#F4F6F8`, dark `#0B0F14`, busy: a tiled high-contrast pattern). Frames are captured with `captureToImage()` and written to `<additionalTestOutputDir>/rive/<mode>/<case>.png` (AGP pulls them; CI uploads `van-instrumentation-screenshots`). Wait 600 ms after each input change before capture so transitions settle.

### 10.4 Cases

| Test | Cases | Assertion beyond "did not throw" |
|---|---|---|
| `coreInputsDriveTheRig` (core, full, production) | states 2,4,5,9; actions 1,2,7 via `action_code` and their triggers; `attention_x/y` at (−1,−1),(1,−1),(−1,1),(1,1),(0,0); `mouth_open` 0/0.5/1 with `viseme` 0–4; `speaking` true/false; `listening` true/false | frames differ pairwise where they must (gaze extremes are not pixel-identical; mouth_open 0 vs 1 differ) |
| `everyStateAndActionRenders` (full, production) | `state` 0–17 each; `action_code` 1–14 each | 32 frames present; each state frame differs from `IDLE` except where the contract allows identical presentation (none; all must differ) |
| `mandatoryCombinations` (full, production) | WORKING+speaking; THINKING+speaking; WAITING_FOR_OWNER+speaking; URGENT+speaking; LISTENING+attention sweep; WORKING+POINT_TARGET; WAITING_FOR_OWNER+PRESENT_CARD; SUCCESS+CELEBRATE; WARNING+CAUTION; DEGRADED+LISTENING | frames present; no exception |
| `invalidInputsDegradeSafely` (all modes) | state −1, 18, 999; action_code −1, 15, 999; attention ±2; mouth_open −1, 2; urgency −1, 2; viseme 99 | no exception; a frame is still produced; the frame is not fully transparent |
| `artboardIsTransparentOnThreeBackgrounds` (all modes) | IDLE on light, dark, busy | the four corner 8×8 patches of the 320 dp frame equal the background (alpha of the artboard is 0 there) |
| `identityColourFamilies` (all modes) | IDLE full-size frame | dominant hue in the hair region is low-saturation light (silver/white); a cyan family is present (visor/accents); no dominant dark hair mass. Implemented as coarse HSV histograms over the upper-third and centre regions with thresholds recorded in the test. This is a drift alarm, not an acceptance criterion. |
| `idleSoakFrameStats` (full, production) | render IDLE with breathing for 300 s inside the host; then `UiAutomation.executeShellCommand("dumpsys gfxinfo com.dial.van")` | write raw output to `<out>/rive/<mode>/gfxinfo.txt`; parse "Janky frames" percentage; assert ≤ `max_janky_percent` (from a test asset `forge_thresholds.json` written by the CLI) |
| `brokenAssetFallsBack` (production) | `VanVisualRuntime.decide(assetBytes = 512, riveRuntimeAvailable = true, ownerArtAvailable = true)` and with `loadFailed = true` | renderer is OWNER_ART with reasons ASSET_UNUSABLE and LOAD_FAILED respectively |

### 10.5 Baselines and diffs

At M2 PASS, the core frames are copied by the CLI into `11-device-evidence/core_baseline/`. In full and production modes the test compares the core cases against those baselines (mean absolute RGB difference over the character bounding box ≤ 0.06, threshold in `forge_thresholds.json`). A regression fails M3.

### 10.6 `RiveCandidateHost` in the app

A debug-only composable screen reachable from Settings → Character → "Preview staged candidate" in debug builds. It renders the staged candidate (from the app's own debug assets, copied by the same CLI command into `src/debug/assets/`) at the three sizes with a state/action picker. Its purpose is the owner's core verdict on real hardware without touching the production asset. Release builds do not include it (`src/debug` only).

---

## 11. Layer and SVG contract (M1)

### 11.1 Required group ids

```
hair, visor_frame, visor_lens, face, eye_l, eye_r, brow_l, brow_r,
mouth_upper, mouth_lower, mouth_inner, neck, jacket, underlayer,
arm_l_upper, arm_l_fore, hand_l, arm_r_upper, arm_r_fore, hand_r,
orb_shell, orb_core
```
Additional groups are allowed and must be prefixed `extra_`.

### 11.2 Lint rules (`svg_lint.py`)

Reject: a required group missing; any group without an id; `<image>` elements; external references (`xlink:href`/`href` to anything but `#`); duplicate ids; `<text>`/fonts; empty paths; paths with bounding box smaller than 0.5 % of the artboard height (noise); transforms with non-finite numbers; coordinates outside the viewBox by more than 5 %; fill colours whose HSV falls outside the identity families (silver/white for `hair`; cyan/blue for `visor_lens`, `orb_core`, accents; medium-brown range for `face`, `neck`, hands; near-black/white/charcoal for `jacket`, `underlayer`). Families are defined as HSV ranges in `svg_lint.py` with the identity lock as the source of truth; changing a range is a canon change and needs the owner.

Measure and record: path count (budget 1 200), node count, bounding boxes, palette, file size.

### 11.3 Mask validator (L2 only)

Non-empty; inside bounds; eyes inside face; mouth inside lower face; visor overlaps eye region; hands attached to arm hierarchy; no severe overlap outside expected pairs. Produces an alpha overlay sheet for review.

---

## 12. Core rig scope (M2)

### 12.1 Exactly this, nothing more

Durable states: IDLE (2), LISTENING (4), THINKING (5), SPEAKING (9). Finite actions: HELLO_WAVE (1), ACK_NOD (2), POINT_TARGET (7). Inputs all present and wired even where unused yet: `state`, `speaking`, `listening`, `attention_x`, `attention_y`, `mouth_open`, `urgency`, `viseme`, `action_code`; triggers all present. Behaviours: gaze from `attention_x/y` in [−1, 1] (head and eyes, eyes lead); blink (random 3–6 s, 120–160 ms, never during a POINT); mouth from `mouth_open` amplitude and `viseme` 0–4 shape (§13.3); breathing (≈ 4 s cycle, ≤ 2 % scale); orb idle drift.

### 12.2 Identity

Silver-white swept hair, cyan-blue transparent visor over blue eyes (transparency confined to the lens), medium-brown solid skin, black/white technical jacket over charcoal underlayer, DIAL cyan accents, cyan holographic orb. Nothing translucent except the visor lens and orb glow. Recognisable at 48 dp portrait crop.

### 12.3 Internal architecture

One character, layered by additive channels: base micro-motion → durable-state layer → gaze layer → blink/face layer → speech layer → finite-action layer (blend-in/out) → orb. No per-state copies of the character. The skeleton (bones, meshes, constraints) is frozen at M2 PASS; any later structural change returns to M2.

### 12.4 Artboard

Transparent background; no full-artboard effects, glows or particles (the aura is Android's); the character bounding box leaves ≥ 6 % margin so gestures do not clip.

---

## 13. Full authoring (M3)

### 13.1 Durable states

Each of the 18 states needs: an entry transition (≤ 300 ms), a steady loop with no visible period shorter than 6 s, an exit, and a readable intent at 96 dp. Intent per state follows `docs/VAN_CHARACTER_VISUAL_IDENTITY.md` and the aura canon's orthogonal channels: DEGRADED and WARNING must not suppress local activity; SPEAKING is articulation layered on the underlying activity; URGENT and ERROR are posture changes, not colour-only changes (CF-R accessibility: a colour-blind viewer must still read the state from pose or motion).

### 13.2 Finite actions

Each of the 14 actions: trigger and `action_code` both drive it; duration 600–1 800 ms; anticipation, main pose, return; returns to the underlying durable state; compatible with `speaking` (mouth continues) and gaze (gaze resumes after). POINT_* directions must be unambiguous at 96 dp.

### 13.3 Speech

`mouth_open` (0–1) is amplitude; `viseme` selects shape: 0 neutral, 1 small neutral, 2 medium spread, 3 wide vertical, 4 rounded. Unknown positive values render as 1. The rig follows the gateway cue track (SpeechCueClock → `SpeechCueTiming`), so timing tests use recorded cue tracks from `backend/tests` fixtures, not a third tool.

### 13.4 Combination rules

The ten mandatory combinations in §10.4 must render without artefacts; `urgency` scales posture intensity within URGENT/WARNING/ERROR only.

---

## 14. Packaging receipt (`09-rive-working/<candidate>.receipt.json`)

```json
{
  "candidate_sha256": "<hex>",
  "candidate_path": "visual-authority/character-forge/09-rive-working/van_runtime_core_1.riv",
  "stage": "core_rig",
  "rive_editor_version": "<exact>",
  "rive_file_id": "<cloud file id or LOCAL>",
  "rive_revision": "<revision id or LOCAL>",
  "svg_sha256": "<hex of the admitted layer artifact>",
  "contract_sha256": "<hex of rive_contract.json at export>",
  "artist": "<name>",
  "exported_at": "<ISO-8601>",
  "notes": "<free text>"
}
```
The receipt is required by `rive stage-candidate`; the validator run in CI records the run URL against `candidate_sha256` in `MANIFEST.yaml`.

---

## 15. Owner acceptance (M4)

Device side (new, small): Settings → Character gains "Accept this character asset" in all builds. It reads the SHA-256 of `assets/van.riv` at runtime, mints `OwnerApprovalKeyManager().prepareOwnerAuthority(act = "visual-accept", subject = "sha256:<hex>")`, signs `Prepared.canonical` via `BiometricGate.requestA4CommandApproval` (title "Accept VAN character"), assembles the token and posts `{"token": ..., "rive_sha256": ..., "apk_sha256": ..., "device_model": ..., "android_build": ...}` to `POST /v1/visual/acceptance` (device-proofed route, same auth as other owner routes).

Gateway side (new, small): the route verifies the token with the same `OwnerAuthorityVerifier` used for `owner-halt`, requiring act `visual-accept` and subject equal to the posted SHA, stores the record (table `visual_acceptances`: id, rive_sha256, apk_sha256, token, key_id, device_model, android_build, verified_at), and exposes `GET /v1/visual/acceptance` (owner-device auth) returning the latest record. Tests: `backend/tests/test_visual_acceptance.py` (valid token stored; wrong act rejected; subject mismatch rejected; replay of the same token is idempotent).

Repository side: `ACCEPTANCE.yaml.final` holds the record verbatim plus `verified_by: gateway|local` and the verification timestamp. `test_character_forge_release.py` recomputes the SHA of `assets/van.riv` and asserts equality with the record's subject.

---

## 16. Release binding (M5)

`visual-authority/rive/manifest.json`:
```json
{
  "asset": "android/app/src/main/assets/van.riv",
  "source_asset": "visual-authority/rive/van_runtime.riv",
  "artboard": "Van",
  "state_machine": "VanRuntime",
  "git_sha": "<exact>",
  "rive_sha256": "<exact>",
  "contract_sha256": "<exact>",
  "visual_authority_revision": "2.3",
  "rive_android": "9.6.5",
  "rive_editor_version": "<exact>",
  "emulator_validation_run": "<CI run URL>",
  "device_checklist": "docs/character_forge/DEVICE_CHECKLIST.yaml",
  "acceptance": "docs/character_forge/ACCEPTANCE.yaml#final",
  "released_at": "<ISO-8601>"
}
```
`record_apk_signing_identity.sh` gains: unzip the built APK, SHA-256 `assets/van.riv`, print `rive_sha256=<hex>` into the identity file; CI fails if the value differs from `manifest.json.rive_sha256` when the manifest exists.

---

## 17. Device checklist additions (S24, M4)

In addition to the physical checklist in `docs/VAN_VISUAL_ACCEPTANCE_MATRIX.md`, record PASS/FAIL with a screenshot or clip reference for: renderer row shows "Rive artboard active"; identity at floating size; minimized portrait reads as VAN; gaze follows a finger drag across the workboard; blink cadence natural; speech articulation during a real spoken reply; HELLO_WAVE on first session of the day; WAITING_FOR_OWNER pose during a pending A4 approval; URGENT on a forced degraded HERMES_OFFLINE; workboard open/expand/maximize with no freeze or clipping; aura and character coexist (no double glow, no full ring); 5-minute idle without visible loop; thermal note after the 30-minute mixed soak (states, speech, board, minimize/restore, gestures, degraded transitions).

---

## 18. Status vocabulary (`STATUS.json`)

```json
{
  "pack": "VAN-CHARACTER-FORGE-DP-R2",
  "baseline_sha": "<exact>",
  "build_ready": false,
  "current_stage": "admission|vector|core_rig|full_rig|integrated|certified|released",
  "rive_authored": false,
  "rive_contract_ready": true,
  "rive_runtime_ready": true,
  "rive_asset_ready": false,
  "device_qualified": false,
  "owner_accepted": false,
  "qual_emb_01": "EXTERNAL_ARTEFACT|READY",
  "core_rig": {"candidate_sha256": null, "emulator_validation": "NOT_RUN|PASS|FAIL", "ci_run": null, "owner_verdict": "NONE|PASS|REVISE|REJECT"},
  "full_rig": {"candidate_sha256": null, "emulator_validation": "NOT_RUN|PASS|FAIL", "ci_run": null, "reviewed": "NONE|PASS|FAIL"},
  "performance": {"max_janky_percent": 5.0, "last_janky_percent": null},
  "blockers": ["<text>"],
  "next_action": "<the single next command or human step>"
}
```
Transitions are only made by the CLI. `test_character_forge_status.py` asserts: `rive_asset_ready` implies a `van_runtime.riv` whose SHA is in the manifest; `device_qualified` implies a complete `DEVICE_CHECKLIST.yaml`; `owner_accepted` implies a verified `ACCEPTANCE.yaml.final`; `qual_emb_01 == "READY"` implies all three and a release manifest. `build_ready` is true once M0's gate holds.

Until M4, `docs/VAN_CHARACTER_VISUAL_IDENTITY.md` "Rive status" keeps saying EXTERNAL and not delivered; M5 rewrites that paragraph with the SHA.

---

## 19. Mutation tests (`test_character_forge_mutations.py`)

Each mutation is applied to an in-memory copy and the named gate must fail:

| Mutation | Gate that must fail |
|---|---|
| Remove one durable state from the contract copy | `contractSurfaceMatches` logic (unit-tested Python mirror in `gates.py`) and `test_rive_contract.py` |
| Rename `attention_x` | same |
| Artboard `Van` → `VAN` in the receipt/contract copy | same |
| Remove action 14 | same |
| Alter accepted `.riv` bytes after `manifest.json` exists | `test_shipped_asset_matches_source` / release test |
| Change `baseline_sha` in STATUS without a receipt | status test |
| Drop a required group from the SVG | svg test |
| Shift `hair` fill to a dark colour | svg test (family rule) |
| Delete `ACCEPTANCE.yaml.final` | release test |
| Stage a candidate with no packaging receipt | `rive stage-candidate` refuses (CLI test) |
| Skip the instrumentation job while an asset exists | `test_character_forge_status.py` requires `ci_run` for any PASS |

A gate that stays green under its mutation is a defect in the gate; fix the gate, never the mutation.

---

## 20. Failure, degraded and recovery behaviour

| Failure | Behaviour | Recovery |
|---|---|---|
| Rive Editor unavailable or version drifts | M2/M3 blocked; `STATUS.json.blockers` says so; nothing else changes | pin and record the version; resume |
| Candidate fails to load on the emulator | `RiveContractTest` fails; candidate promotion REJECTED; production untouched | new candidate + receipt |
| Emulator job infrastructure fails (no tests ran) | `ci_run` absent → gate cannot pass; not treated as a PASS | re-run the job |
| S24 unavailable | M2 verdict / M4 checklist blocked; repository work continues | record when available |
| Gateway unavailable for acceptance | use `--token --device-public-key` local verification | pull from gateway later; both records kept |
| A lane tool fails | lane output absent; artist proceeds manually | none required |
| rive-android version bump | M2–M4 reopen automatically (status test compares `TOOLS.yaml` pin to gradle) | re-validate |

Every stage restarts from immutable inputs named by hash; no stage depends on transient state.

---

## 21. Security

Critical path tools (Inkscape, Rive Editor) run on the artist's workstation with no production secrets required. Lanes run in isolated environments with no home-directory mounts, no owner tokens, no GitHub write credentials, egress denied except admitted fetches. Generated code (Blender scripts, custom nodes) is arbitrary code and runs only inside the lane sandbox. Acceptance is cryptographic (§15): no file in the repository can claim owner acceptance without a signature the gateway or the local verifier accepts. Promotion writes are limited to the CLI commands in §9.

---

## 22. Drift guards and decision table

Do not, under any instruction from a lane tool, a reference document, or a generated asset:

- rename, add or remove a public input or trigger; change artboard or state machine names;
- edit `rive_contract.json` (a change is a new contract revision with owner sign-off and a Kotlin change, outside this pack);
- write to `android/app/src/main/assets/van.riv` except through `cli android integrate`;
- write `ACCEPTANCE.yaml.final` by hand;
- mark any status field true without the receipt or CI run that proves it;
- add a Forge UI, API or orchestrator "to make it easier";
- build a second Rive loader or a second visual truth.

| If you find | Then |
|---|---|
| The rive-android 9.6.5 API names differ from §10.1 | adapt the calls; keep every assertion; note the exact API in `README.md` |
| An additional layer is needed for the rig | add it with the `extra_` prefix; do not remove a required one |
| The artist wants a new public input | stop; it is a contract revision; record it in `STATUS.json.blockers` and ask the owner |
| The emulator cannot reach 60 FPS but the S24 can | the emulator threshold is jank percentage, not FPS; if jank exceeds the threshold on the emulator but not on the S24, record both, keep the S24 number authoritative in `DEVICE_CHECKLIST.yaml`, and do not lower the threshold without an owner line in `STATUS.json` |
| Source art seems incomplete for a pose | use the L1 lane or the artist's judgement inside the lock; never redefine identity |
| A test is inconvenient | the test stays; fix the artifact |
| The plan and the repository disagree | the repository's tests and canon documents win; update this pack in the same commit and say why in the commit message |

---

## 23. Definition of done (Rev 2)

All true, each checkable by command:

1. `python -m tools.character_forge.cli gate m5` exits 0.
2. `pytest tests/contracts -q` green, including the five Character Forge tests and the mutation suite.
3. `van-ci.yml` green on the release commit: backend, `android-and-visual-evidence`, `android-instrumentation` (production mode, all `RiveContractTest` cases run, none skipped), mutation.
4. `visual-authority/rive/van_runtime.riv` and `android/app/src/main/assets/van.riv` byte-identical; SHA in `manifest.json`, `van_runtime.sha256`, `ACCEPTANCE.yaml.final.subject` and the APK identity file all equal.
5. `DEVICE_CHECKLIST.yaml` complete for the S24 with no FAIL.
6. `STATUS.json` final row: `rive_authored`, `rive_contract_ready`, `rive_runtime_ready`, `rive_asset_ready`, `device_qualified`, `owner_accepted` all true; `qual_emb_01: READY`.
7. `docs/VAN_CHARACTER_VISUAL_IDENTITY.md` Rive status paragraph names the SHA; `VAN_RUNTIME_QUALIFICATION_MATRIX.md` QUAL-EMB-01 READY.
8. Maturity gate green with the Character Forge component rows.

---

## 24. Execution order (checklist)

```
[ ] 1  git checkout main && git pull; record HEAD in STATUS.json.baseline_sha
[ ] 2  create docs/character_forge/{MANIFEST.yaml,STATUS.json,TOOLS.yaml,ACCEPTANCE.yaml,DEVICE_CHECKLIST.yaml}
[ ] 3  implement tools/character_forge/{cli,manifest,svg_lint,receipts,status,gates}.py + README.md
[ ] 4  implement the five contract tests + mutation suite; extend test_rive_contract.py
[ ] 5  python -m tools.character_forge.cli source admit; owner confirms the source set
[ ] 6  cli gate m0 → BUILD_READY=true; commit "character-forge: M0 admission"
[ ] 7  artist: van_layers.svg; cli vectors lint; cli vectors admit; review line; cli gate m1
[ ] 8  implement RiveContractTest.kt, RiveCandidateHost.kt (debug), forge_mode/thresholds assets
[ ] 9  pin rive_editor in TOOLS.yaml; artist builds core rig; cli rive receipt; cli rive stage-candidate --stage core_rig
[ ] 10 push; read android-instrumentation run; fix candidate until green; record ci_run
[ ] 11 owner views RiveCandidateHost on the S24 from the CI debug APK; cli owner record-core-verdict; cli gate m2
[ ] 12 artist completes 18 states + 14 actions; receipt; stage --stage full_rig; push until green; reviewer line; cli gate m3
[ ] 13 implement Settings "Accept this character asset" + POST/GET /v1/visual/acceptance + tests
[ ] 14 cli android integrate --candidate <full riv>; push; CI green in production mode
[ ] 15 S24: DEVICE_CHECKLIST.yaml; owner accepts on device; cli owner record-acceptance --from-gateway; cli gate m4
[ ] 16 extend record_apk_signing_identity.sh; add ledger rows; cli release promote; cli gate m5; commit "character-forge: release <sha>"
```

Steps 3–4 and 8 and 13 are engineering; 7, 9, 12 are the artist; 5 (confirmation), 11, 15 are the owner. Nothing in 1–8 waits on a GPU, a sandbox, or a lane tool.

---

## 25. Stop conditions

Stop and record a blocker rather than working around it if: the identity lock would change; the source set is disputed after confirmation; the editor cannot export a format rive-android 9.6.5 loads; the core rig fails the S24 verdict twice on the same skeleton; whole-character opacity fails; the janky-frame threshold cannot be met on the S24; an independent review finds a severe unresolved issue; any lane tool exposes credentials.

---

## 26. What this pack removed from Rev 1 and why

| Removed | Reason |
|---|---|
| 40 requirements → 20 | half were already satisfied by the repository or belonged to tools now optional |
| 9 blockers → 3 (source confirmation, editor pin, S24 in hand) | GPU, Blender sandbox and full tool registry only gate lanes |
| 20 development units → 6 milestones + 3 lanes | the critical path is linear |
| 17 packets → the 16-step checklist | each step is a command or a named human action |
| 10 operator screens, 10-endpoint API, controller, ledger service | one operator, one asset; `STATUS.json` and the device Settings row are the truth surface |
| 27 machine-readable files + checker | 5 files enforced by existing test and gate infrastructure |
| separate contract validator, evidence engine, visual matrix renderer | one instrumentation test class on the existing emulator job |
| Inochi2D, Blender MCP, Rhubarb, ComfyUI, SAM2, VTracer on the critical path | optional lanes; Inkscape and the Rive Editor suffice for one character with existing owner art |
| three state machines | `stage` + `promotion` |

Every guarantee Rev 1 asked for survives: owner authority, hash immutability, candidate-only AI, core-rig-first, independent review, honest status, mutation-proven gates, exact-SHA release binding.
