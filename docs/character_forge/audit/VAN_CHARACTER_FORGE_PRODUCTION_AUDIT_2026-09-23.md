# VAN Character Forge — Production-Readiness Forensic Audit

- **Date:** 2026-09-23
- **Base audited:** `main` @ `61d86cd` (post PR #60 Character Forge M0–M5 and PR #63)
- **Remediation branch:** `claude/van-forge-audit-11n4wh` (engineering fixes listed in Part I)
- **Authority read:** Rev 2 pack, Rev 2.1 supplement, identity canon, acceptance matrix, `rive_contract.json`, aura v2.3, TOOLS/STATUS/MANIFEST/ACCEPTANCE/DEVICE_CHECKLIST, every file under `tools/character_forge/`, `deploy/character-forge/`, the Forge contract tests, `RiveContractTest`, the debug candidate host, the Android visual runtime and the CI workflow.
- **Method:** each capability traced DECLARED → IMPLEMENTED → INSTANTIATED → REACHABLE → EXERCISED → EVIDENCED → AUTHORIZED. Defects were reproduced before being fixed.

## Evidence limits (read first)

| Limit | Consequence |
|---|---|
| **`dial-control` was not reachable.** Desktop Commander lists no device named `dial-control`. Every registered device (`oracle-admin`, `oracle-admin-v2`, `dial-hermes-control`, `DESKTOP-S0CDKSD`) was **offline**; `dial-hermes-control` was last seen 2026-09-09. | §31's live host qualification **was not performed**. No claim here says the Netcup workstation is qualified. The qualifier was hardened so the probe produces machine-readable evidence (`qualification.json`) when it is run. |
| `releases.rive.app` is blocked from this audit environment by egress policy. | The Rive CLI was exercised only through GitHub Actions (the pinned `rive 1.1.1` smoke), not interactively. |
| No Android SDK in the audit container. | Kotlin changes are compiled and exercised only by CI (`android-and-visual-evidence` compiles the debug host; `android-instrumentation` compiles and runs `RiveContractTest`). |
| No S24, no owner. | Every owner/device gate is reported as external and remains unpromoted. |

---

## PART A — Executive findings

**Verdict: the production system is not ready to begin authoring the real `van.riv`. The engineering plane is sound in shape. Three things block quality, not code.**

1. **The owner's identity sources disagree with each other and with canon (CF-OPUS-001, P0, owner decision).**
   - Measured, not eyeballed:
     - `owner_visual_lock_sheet.jpg` and all nine `assets/derived/` crops show a light, peach-skinned VAN: face mean `#e3afa0`–`#eab8b0`, value 0.89–0.92. That VAN has a dark "VAN" headband, black gloves and chibi ~3-head proportions.
     - `pack/owner_board_visual_authority.png` ("Visual Authority v1.0.0") shows medium-brown skin (`#9c614e`–`#af6c50`, value 0.61–0.69, token `#B8853C`). That VAN has no headband, a hood and 5.5–6-head "chibi-realistic" proportions.
     - Canon (`VAN_CHARACTER_VISUAL_IDENTITY.md`, `rive_contract.json.identity_lock`) says medium-brown. The interim Canvas character mixes the two: medium-brown skin with a headband.
   - A vector artist cannot "faithfully" trace both.
   - Nothing in the pipeline can resolve this without inventing identity, which is prohibited (category D).
2. **Most named reference sheets are placeholders (CF-OPUS-003, P0, owner action).**
   - `turnaround.png`, `expressions.png`, `gestures.png`, `presentation.png`, `compact_avatar.png`, `urgent_decision.png`, `offline_degraded.png`, `command_centre.png`, `onboarding_hero.png`, `hermes_avatar.png`, `app_icon.png` and the icons are 0–5 KB procedural drawings: a grey/brown circle "head", a blue rectangle "visor", a hatched rectangle "torso" and a cyan dot "orb".
   - The Rev 2 pack §0 lists them as owner source art. `source admit` would hash them as authoritative.
   - The only real artwork:
     - one 957×1024 JPEG lock sheet (VAN ≈ 150–260 px tall; face ≈ 50–70 px);
     - five ~1.2–1.5 k boards (expression heads ≈ 70 px; turnaround figures ≈ 260 px);
     - nine derived crops of ≈ 160×186 px.
   - The v1.0.0 board lists a "production asset set" with SHA excerpts: `van-turnaround.png`, `van-expressions.png`, `van-gestures.png` and a Rive guide. **None of it is in the repository.**
   - Premium vectors for a 320 dp (≈ 1120 px on S24) artboard cannot be traced from 50–70 px faces. They would be re-invented, which is exactly the AI-drift risk the pack forbids.
3. **Commander could not actually build the character (CF-OPUS-004, P0, fixed in engineering; push credential external).**
   - The bounded worker had no way to:
     - put RML or SVG into the `vanforge` workspace;
     - build a candidate, receipt it, stage it or admit vectors;
     - push a branch so CI validates it.
   - The answer to "can ChatGPT/Hermes orchestrate the real `.riv` build through Commander" was **no**. It is now **yes, up to the owner-provisioned git credential**.

**Strongest elements (keep):**
- one public contract bound by tests (`rive_contract.json` ↔ `RiveContract.kt` ↔ `RiveContractTest.contractSurfaceMatches`);
- candidates never touch the product (`androidTest`/`debug` assets only until M4);
- cryptographic owner acceptance, reusing the `owner-halt` verifier;
- fail-closed renderer order RIVE → OWNER_ART → CANVAS;
- pinned, checksum-verified Rive CLI with a real CI smoke;
- exact-SHA release manifest;
- honest `STATUS.json`: nothing claims READY.

**Critical weaknesses found in engineering (all fixed on the branch unless marked):**
- **M1 could never pass on a qualified host:** the Inkscape pin format differed from the observed version (CF-OPUS-002).
- **Validation PASS was typable over a failed CI run:** the CI "binding" hashed the checkout before tests ran. The instrumentation job was also non-blocking (CF-OPUS-005/006).
- **Receipts named no RML source,** so a CLI candidate was not traceable to what produced it (CF-OPUS-007).
- **The validator could not fail a rig with no actions,** and its state-distinctness threshold was satisfied by breathing noise (CF-OPUS-008).
- **The validator tested a debug host, not the production composable,** and production never fires triggers (CF-OPUS-009).
- **The Commander could forge the cloud-write sentinel** and write outside the forge tree through `remove-bg`/`vectorize` output paths (CF-OPUS-010).
- **The qualifier always went RED when Commander ran it** (`runuser` as non-root), used predictable `/tmp` paths as root, and went permanently RED once authoring started (CF-OPUS-011).
- **The identity lint could be bypassed** with `rgb()`, named colours or gradients (CF-OPUS-013).
- **Reviewer independence and S24 evidence were typed strings** (CF-OPUS-015/016).

**Quality risks that no code fixes:**
- The 22-group layer model is too coarse for premium facial and hand animation (CF-OPUS-017).
- There is no motion evidence (only 850 ms stills) (CF-OPUS-021).
- RML's ability to express bones, meshes, constraints, blend states and layered state machines at VAN's scope is unproven (CF-OPUS-024).
- The emulator jank metric does not measure Rive's render thread (CF-OPUS-018).
- The offline-TTS viseme producer is a sawtooth that emits out-of-contract viseme ids (CF-OPUS-019).

**Determinism evidence:**
- The pinned `rive 1.1.1`, on this branch's CI run 35933638590, authored a `StateMachineBool`, `StateMachineNumber` and `StateMachineTrigger`.
- It rebuilt an unchanged project byte-identically: `5e827a3f…d8dba0` twice.
- That is a 278-byte scaffold. Determinism must be re-proven on the real rig: the smoke now records it on every CI run, and `rive-candidate` makes every build reproducible from committed RML.

---

## PART B — Findings register

Legend — **Owner:** RE = repository engineering · HB = host bootstrap · AR = artist action · OW = owner action · EX = external dependency. **State:** FIXED (on branch, tested) · OPEN.

### CF-OPUS-001 — Identity sources conflict (skin, headband, proportions)
- **Severity:** P0
- **Domain:** visual identity
- **Path:** `visual-authority/assets/owner_visual_lock_sheet.jpg`, `assets/derived/*`, `assets/pack/owner_board_visual_authority.png`, `docs/VAN_CHARACTER_VISUAL_IDENTITY.md`, `rive_contract.json.identity_lock`
- **Requirement endangered:** CF-R-02 identity lock; §3 locked visual authority
- **Evidence:** measured skin means are above (lock sheet `#e3afa0`; v1.0.0 board `#9c614e`–`#af6c50`). The headband appears on the lock sheet and derived crops, is absent on the v1.0.0 board, and is described in the Canvas character doc. Proportions differ: chibi ~3 heads vs 5.5–6 heads.
- **Root cause:** multiple owner boards (the lock sheet shows image-generation artefacts such as the "THRENING" label) were admitted without a single designated master.
- **Consequence:** any vector sheet silently picks one identity. The OWNER_ART fallback already ships the light-skinned variant while canon says medium-brown.
- **Remediation:** the owner designates one master per trait: skin tone value, headband yes/no, proportions (head count), glove colour, hood. Record it as a visual-authority revision in `VAN_CHARACTER_VISUAL_IDENTITY.md` + `identity_lock` (a contract revision per pack §22), before M0 confirmation.
- **Validation:** an owner line in the identity doc; `svg_lint` skin family narrowed to the chosen tone (CF-OPUS-014).
- **Owner:** OW
- **State:** OPEN

### CF-OPUS-002 — M1 `vectors admit` could never pass on a qualified host
- **Severity:** P0
- **Domain:** toolchain
- **Path:** `deploy/character-forge/bootstrap-netcup-authoring.sh`, `tools/character_forge/cli.py`
- **Requirement endangered:** M1 gate; CF-R-16
- **Evidence (reproduced):**
  - The bootstrap records `inkscape --version | head -n1`, e.g. `Inkscape 1.2.2 (b0a8486541, 2022-12-01)`.
  - `import-lock` pinned that full string.
  - `vectors admit` compares `parts[1]`, i.e. `1.2.2`, so it always refused.
  - The existing test fixture used the full-string form too, so the mismatch was invisible.
- **Remediation:** `normalize_inkscape_version()` in import and admit; the bootstrap records the bare version (and the raw line separately).
- **Validation:** `test_bootstrap_inkscape_lock_pins_the_version_vectors_admit_observes`, `test_bootstrap_records_a_bare_inkscape_version`
- **Owner:** RE+HB
- **State:** FIXED

### CF-OPUS-003 — Named reference sheets are placeholders; high-res originals absent
- **Severity:** P0
- **Domain:** source art
- **Path:** `visual-authority/assets/*.png` (12 files)
- **Requirement endangered:** §7 source-art preparation; M0 admission truthfulness
- **Evidence:** visual inspection (montage), file sizes 0–5 KB, the board's asset manifest references files not in git.
- **Root cause:** icon/placeholder generators were committed under reference names.
- **Consequence:**
  - Admission would certify placeholders as authority.
  - Vectorization would have to invent turnaround, expression and gesture geometry.
- **Remediation:**
  - The owner supplies the original high-resolution renders (≥ 2048 px on the long edge; face ≥ 400 px): front, ¾, side, rear, expression set, gesture set, hands, orb, visor close-ups.
  - Rename the placeholders `placeholder_*` or move them out of `visual-authority/assets/` before `source admit`. Only the owner may decide which files are authoritative.
- **Validation:** owner confirmation of the source set at M0 lists no placeholder; source resolution recorded in the manifest.
- **Owner:** OW
- **State:** OPEN

### CF-OPUS-004 — Commander had no authoring path
- **Severity:** P0
- **Domain:** orchestration
- **Path:** `deploy/character-forge/commander-worker.sh`
- **Requirement endangered:** Rev 2.1 "Netcup must produce, inspect and validate the real candidate"; §19
- **Evidence:** the worker exposed `rive-create/verify/build` but no file ingest, receipt, stage, vector admit or push. The workspace is `vanforge`-owned, so the Commander user cannot write it.
- **Remediation:** new bounded, jailed commands:
  - `rml-put`, `rml-cat`, `vector-put`, `vectors-admit`
  - `rive-candidate` (pinned build → immutable numbered candidate)
  - `rive-source-hash`, `rive-receipt`, `rive-stage`
  - `contact-sheet`, `frames-to-webm`
  - `forge-push` (to `forge/*` only, behind a root-owned switch and an owner-provisioned credential)
- **Validation:** `test_worker_rml_put_writes_only_inside_the_named_project`, `test_worker_jails_every_prep_path`, `test_worker_cloud_write_sentinel_cannot_be_forged_by_the_forge_user`
- **Owner:** RE (+OW for the git credential)
- **State:** FIXED (credential external)

### CF-OPUS-005 — A PASS could be recorded over a failed or absent test run
- **Severity:** P1
- **Domain:** anti-falsification
- **Path:** `.github/workflows/van-ci.yml` "Bind Character Forge validation input"; `cli.py cmd_record_validation`
- **Requirement endangered:** §28 "wrong CI SHA / fake evidence directory must fail"; CF-R-19
- **Evidence:**
  - The binding file was written **before** tests ran and held only the checked-out SHA.
  - `record-validation --result PASS` accepted any directory holding that one line, plus any GitHub URL.
- **Remediation:**
  - `tools/character_forge/ci_binding.py` writes `van_validation.json` from JUnit results: mode, SHAs, run id, commit, per-test outcome and a derived result. Expected skips are defined per mode.
  - `record-validation` requires the CI-stated result, the same run id, mode and SHA. It also requires that the named commit (in local git) carries the exact bytes.
  - Only `rive/core/*.png` frames become the M2 baseline.
- **Validation:** `test_character_forge_ci_binding.py` (fake dir, typed PASS over FAIL, other run, wrong mode, wrong commit)
- **Owner:** RE
- **State:** FIXED

### CF-OPUS-006 — Instrumentation failures never blocked a commit carrying an asset
- **Severity:** P1
- **Domain:** CI
- **Path:** `van-ci.yml` (`android-instrumentation: continue-on-error: true`)
- **Requirement endangered:** DoD item 3; §28 "CI skipped while an asset exists"
- **Remediation:** a new blocking job `character-forge-gate` (`needs: android-instrumentation`, `if: always()`) fails when a candidate or production asset is present and validation ≠ PASS. With no asset it passes, so hosted-emulator flakiness still cannot block unrelated work. A missing binding passes only when the checkout has no asset.
- **Validation:** `test_ci_gate_blocks_a_present_asset_that_did_not_pass`, `test_missing_binding_passes_only_when_the_tree_has_no_asset`
- **Owner:** RE
- **State:** FIXED

### CF-OPUS-007 — Packaging receipt did not bind the RML source
- **Severity:** P1
- **Domain:** provenance
- **Path:** `cli.py cmd_rive_receipt`, `gates._receipt_problems`, `receipts.py`
- **Requirement endangered:** CF-R-17; §27 "Rive source project/revision"
- **Evidence:** CLI receipts carried `rive_file_id/rive_revision` (cloud-era fields, `LOCAL` for CLI builds) and nothing identifying the source that compiled to the `.riv`.
- **Remediation:**
  - `--source-project` is required and must live under `09-rive-working/rml/`.
  - A deterministic source-tree digest is recorded; build products are excluded.
  - `stage-candidate` refuses if the RML changed after receipting, and the gate refuses unbound receipts.
  - New read-only `rive source-hash`.
- **Validation:** `test_mutation_rml_source_edited_after_receipt_blocks_staging`, `test_gate_rejects_receipt_without_rml_source_binding`, `test_source_tree_digest_ignores_build_products_but_not_source`
- **Owner:** RE
- **State:** FIXED

### CF-OPUS-008 — Validator could not fail missing actions; distinctness threshold was noise-level
- **Severity:** P1
- **Domain:** validation
- **Path:** `RiveContractTest.kt`
- **Requirement endangered:** CF-R-08; §28 "missing action must fail"
- **Evidence:**
  - Action frames were only checked for "not blank".
  - States passed with a mean RGB difference > 0.001, which breathing or blink phase alone produces.
  - Core actions were captured, never asserted.
- **Remediation:**
  - `distinctThreshold()` = max(0.004, 3 × measured IDLE-vs-IDLE noise).
  - Every state and all 14 actions must clear it. The three core actions are asserted in core mode.
  - Actions are captured ~300 ms in (`ACTION_PEAK_MS`).
- **Validation:** CI instrumentation (skips with `NO_RIVE_ASSET` until a candidate exists). `ci_binding` fails a run in which these tests skip with an asset present.
- **Owner:** RE
- **State:** FIXED

### CF-OPUS-009 — Validator exercised a debug host, not the production renderer; production never fires triggers
- **Severity:** P1
- **Domain:** Android reachability
- **Path:** `RiveCandidateHost.kt` (`RiveCandidateFrame`) vs `VanRiveAvatar.kt`
- **Requirement endangered:** §26 "prove production reachability"
- **Evidence:**
  - `RiveContractTest` renders through `RiveCandidateFrame`, which fires triggers.
  - Production `VanRiveAvatar.applyVisualState` sets only numbers and booleans; `VanTrigger` is referenced by no production code.
  - An artist who wires actions only to triggers passes CI and ships a VAN that never gestures.
- **Remediation:**
  - The action assertions drive `action_code` alone.
  - New `productionAvatarPathKeepsRive` renders the shipped asset through the real `VanAvatar` (debug host `EXTRA_PRODUCTION_PATH`) and requires RIVE with no LOAD_FAILED.
  - The rig spec (Part E) makes `action_code` the authoritative driver.
- **Remaining gap:** the full overlay composition (`FloatingOverlayService` → `VanEmbodiment` + aura) is still verified only on the S24.
- **Owner:** RE
- **State:** FIXED (partial by design)

### CF-OPUS-010 — Cloud-write sentinel forgeable; prep commands un-jailed
- **Severity:** P1
- **Domain:** security
- **Path:** `commander-worker.sh`
- **Requirement endangered:** §19, §25; supplement "root-managed sentinel"
- **Evidence:**
  - The sentinel was `$STATE_ROOT/allow-rive-cloud-write`, and `STATE_ROOT` is `vanforge`-owned.
  - `remove-bg`/`vectorize` accepted any INPUT/OUTPUT, so `remove-bg x.png /var/lib/dial-character-forge/allow-rive-cloud-write` enabled cloud push.
  - Any file readable by `vanforge` could be read, and `docs/character_forge/STATUS.json` could be overwritten.
- **Remediation:**
  - Every path is jailed.
  - Sentinels must be root-owned files in root-owned `/etc/van-character-forge`.
  - Jailed paths are resolved by assignment. A second defect was found while testing: a refusal inside `$(...)` passed as an `exec` argument did not abort under `set -e`.
- **Validation:** `test_worker_jails_every_prep_path`, `test_worker_cloud_write_sentinel_cannot_be_forged_by_the_forge_user`
- **Owner:** RE+HB
- **State:** FIXED

### CF-OPUS-011 — Qualifier failed when run by Commander, used predictable `/tmp`, and went permanently RED during authoring
- **Severity:** P1
- **Domain:** host qualification
- **Path:** `qualify-netcup-authoring.sh`
- **Evidence:**
  - `runuser` requires root, but the worker runs the qualifier as `vanforge`.
  - Its `sudo -n -u vanforge worker doctor` probe is not permitted for `vanforge`.
  - Fixed `/tmp/van-*.txt` paths were written as root.
  - An exact-SHA + clean-tree check fails as soon as authoring edits exist.
- **Remediation:**
  - `as_forge`, `mktemp -d`, and a `STRICT` mode for bootstrap (a descendant commit is GREEN and a dirty tree is WARN during authoring).
  - Checks for potrace, xvfb and montage; Rive binary drift against the lock `binary_sha256`; the authority directory.
  - Report written to `qualification.json`.
- **Validation:** `test_qualifier_runs_as_the_forge_user_and_uses_private_temp`; a **live run on dial-control is still required** (Part J).
- **Owner:** HB
- **State:** FIXED (unexecuted on host)

### CF-OPUS-012 — `rive-login` exposed to Commander
- **Severity:** P2
- **Domain:** authority
- **Path:** `commander-worker.sh`
- **Evidence:** the supplement makes login an owner action; the worker exposed `rive login`.
- **Remediation:** removed; `rive-auth-status` (whoami) remains. The owner logs in interactively (see `deploy/character-forge/README.md`).
- **Validation:** `test_worker_rive_login_is_not_a_commander_command`
- **Owner:** RE
- **State:** FIXED

### CF-OPUS-013 — Identity palette lint bypass
- **Severity:** P1
- **Domain:** identity drift
- **Path:** `svg_lint.py`
- **Evidence (reproduced):** dark hair passed when written as `rgb(17,17,17)`, `black`, or `fill="url(#darkGradient)"`.
- **Remediation:** `rgb()`/`rgba()`/percent, named colours and gradient stops (following `href` chains) are resolved. An unparseable colour in a locked group is `UNVERIFIABLE_COLOR`. Strokes stay out of scope, per §11.2's "fill colours".
- **Validation:** `test_mutation_non_hex_palette_encodings_cannot_hide_dark_hair`, `test_unparseable_colour_in_locked_group_is_refused_not_skipped`, `test_silver_hair_in_rgb_notation_is_still_admitted`
- **Owner:** RE
- **State:** FIXED

### CF-OPUS-014 — Lint colour families don't match the owner art, and don't enforce "medium-brown"
- **Severity:** P1
- **Domain:** identity
- **Path:** `svg_lint.py` `COLOR_GROUPS`, `_allowed`
- **Evidence:**
  - `hand_l/hand_r` must be skin, but every owner board shows black gloves, so a faithful vector fails M1.
  - The "skin" family (S 0.18–0.95, V 0.20–0.90) accepts the light lock-sheet tone and the medium-brown board tone alike.
  - The headband (if canon) has no group or family.
- **Remediation (owner canon change, §11.2):**
  - After CF-OPUS-001, set `hand_*` to `neutral` if the gloves are canon, or split into `glove_*` + `extra_skin_*`.
  - Narrow skin to the chosen tone ± a tolerance (e.g. ΔE2000 ≤ 8 from the owner token).
  - Add `headband` if canon.
- **Validation:** lint mutation tests per family.
- **Owner:** OW → RE
- **State:** OPEN

### CF-OPUS-015 — "Independent" reviewer was any typed name
- **Severity:** P1
- **Domain:** governance
- **Path:** `cli.py cmd_review`
- **Remediation:** refuses the layer author (`produced_by`), the full-rig receipt `artist`, and the Commander surface.
- **Validation:** `test_mutation_author_cannot_review_own_layer_svg`
- **Owner:** RE
- **State:** FIXED

### CF-OPUS-016 — The S24 checklist accepted any device and label-only evidence
- **Severity:** P1
- **Domain:** anti-falsification
- **Path:** `gates.m4`
- **Evidence:**
  - No model check existed; the prior audit's "SM-S928B required" was not in code.
  - `evidence: clip://renderer` passed.
  - The device Rive-SHA check sat in the `elif` of the thermal-note check.
- **Remediation:** the model must match `SM-S928*`; each evidence reference must be a committed file under `11-device-evidence/`; the device SHA check is independent.
- **Validation:** `test_mutation_emulator_or_other_handset_cannot_satisfy_s24_checklist`, `test_mutation_label_instead_of_evidence_file_fails_s24_checklist`
- **Owner:** RE
- **State:** FIXED

### CF-OPUS-017 — The 22-group layer model is too coarse for premium face and hands
- **Severity:** P1
- **Domain:** rig quality
- **Path:** pack §11.1, `svg_lint.REQUIRED_GROUPS`
- **Evidence:** no eyelids, sclera/iris/pupil/catchlight split, upper/lower lids, brow inner/outer, jaw, teeth/tongue, hair front/back/locks, per-finger or finger-group layers, gloves, headband, visor glow/rim, orb face/eyes, jacket front/back or collar, or shadow/highlight layers. Blink, gaze and premium mouth shapes are impossible with one `eye_l` group.
- **Remediation:** keep the required 22 (no churn) and add the **required-for-M2 `extra_` layers** listed in Part E §E1. Pack §11.1 already permits the `extra_` prefix. Enforcing them is a pack amendment (owner sign-off); until then the M1 reviewer checks them.
- **Validation:** M1 review checklist; optional lint "recommended groups" report.
- **Owner:** AR (+OW for enforcement)
- **State:** OPEN

### CF-OPUS-018 — Emulator jank metric does not measure Rive rendering
- **Severity:** P2
- **Domain:** performance
- **Path:** `RiveContractTest.idleSoakFrameStats`
- **Evidence:**
  - `dumpsys gfxinfo` counts HWUI (UI-thread) frames. `RiveAnimationView` renders on its own thread/surface.
  - The emulator uses `swiftshader_indirect` (a CPU rasteriser).
  - The count was cumulative since process start.
- **Remediation:**
  - Fixed: `gfxinfo … reset` before the soak.
  - Open: treat the emulator number as a regression signal only. The authoritative number is an S24 Perfetto trace (`android.surfaceflinger.frametimeline` + `sched`) during the 30-minute mixed soak, recorded in `DEVICE_CHECKLIST.yaml` (Part J).
- **Owner:** RE / OW (S24)
- **State:** PARTIAL

### CF-OPUS-019 — Offline-TTS lip-sync producer is mechanical and out of contract range
- **Severity:** P2
- **Domain:** speech
- **Path:** `android/.../voice/VoiceInterfaces.kt` (`onRangeStart`: `viseme = frame % 15`, `mouthOpen = (frame % 10) / 10f`)
- **Evidence:**
  - On the ANDROID_OFFLINE engine, visemes 5–14 are emitted (pack §13.3 renders unknown values as 1).
  - `mouth_open` is a sawtooth that snaps shut every 10 frames.
  - `VanPresenceFrame` clamps viseme only at ≥ 0.
- **Remediation (no new speech system):**
  - Map the word range to the existing 0–4 set: vowel class from the utterance text slice `start..end` → 2/3/4; consonant → 1; gaps → 0.
  - Clamp `viseme` to 0..4 in `VanPresenceFrame`.
  - Drive `mouth_open` from a smoothed envelope, with an attack/decay the rig can follow.
- **Validation:** unit test: `mouth_open` never jumps > 0.35 between frames; viseme ∈ 0..4.
- **Owner:** RE (runtime voice; outside Forge authority — owner prioritises)
- **State:** OPEN

### CF-OPUS-020 — Action hold times vs pack durations
- **Severity:** P2
- **Domain:** runtime/rig contract
- **Path:** `VanMotionMap.actionDurationMs`
- **Evidence:** OPEN_PANEL/CLOSE_PANEL hold `action_code` for 240 ms (`STANDARD_MS`); pack §13.2 requires 600–1800 ms actions. A rig that exits when `action_code` returns to 0 truncates them.
- **Remediation:** rig rule (Part E §E6): actions **latch** on the rising edge and play to completion regardless of `action_code` returning to 0. Optionally raise the panel hold to ≥ 600 ms (runtime change; owner prioritises).
- **Owner:** AR (+RE)
- **State:** OPEN

### CF-OPUS-021 — No motion evidence
- **Severity:** P1
- **Domain:** visual QA
- **Path:** `RiveContractTest`, CI artifacts
- **Evidence:** every capture is a single still at ~850 ms. Loop period (≥ 6 s), anticipation/settle, blink cadence, speech coarticulation and transitions are never evidenced before the S24.
- **Remediation:**
  - Added: `contact-sheet` and `frames-to-webm` worker commands.
  - Open: add a `motionSequences` instrumentation case that captures 10 fps × 8 s for IDLE, LISTENING, THINKING, SPEAKING (recorded cue track), each action, and 6 transitions. CI encodes them to WebM plus contact sheets.
  - Reviewers and the owner judge motion from these before the S24.
- **Owner:** RE
- **State:** OPEN

### CF-OPUS-022 — Unverified Rive CLI flags on the Commander surface
- **Severity:** P2
- **Domain:** toolchain truth
- **Path:** worker `rive-test`, `rive-screenshot`, `rive-push`, `rive-publish`
- **Evidence:** the smoke exercises only `create`, `--verify`, `--once`, `inspect` and `schema`. `--test`, `--screenshot`, `push --name` and `--publish` are assumed from docs.
- **Remediation:** extend the smoke to run `--test` and `--screenshot` against the scaffold and record their output paths, or remove them from the surface. Cloud commands stay unexercised until the owner enables cloud write.
- **Owner:** RE
- **State:** OPEN

### CF-OPUS-023 — Build determinism was undemonstrated
- **Severity:** P2
- **Domain:** determinism
- **Path:** `rive-cli-smoke.sh`
- **Evidence:** CI run 35933638590 on `rive 1.1.1` shows two builds of an unchanged scaffold give `5e827a3f…`, with `reproducible_build: true`.
- **Remediation:** the smoke now records this every run. `rive-candidate` builds only from committed RML, so a reviewer can rebuild and compare.
- **Owner:** RE
- **State:** FIXED (for the scaffold; re-prove on the real rig)

### CF-OPUS-024 — RML expressiveness for a premium rig is unproven
- **Severity:** P1
- **Domain:** authoring architecture
- **Path:** Rev 2.1 decision
- **Evidence:** proven so far: a project, one state machine, and bool/number/trigger inputs. Unproven: bones, weighted meshes, IK/transform/distance constraints, 1D/additive blend states, multiple state-machine layers, nested artboards, clipping, listeners, easing curves.
- **Remediation:**
  - Before M2 art work, a **rig-capability probe** (Part D stage 5): an RML project that exercises each of those features, built, inspected, staged and run through `RiveContractTest` core mode.
  - Any feature RML cannot express triggers the hybrid Editor lane (Part E §E10) as a recorded owner decision.
- **Owner:** RE+AR
- **State:** OPEN

### CF-OPUS-025 — Critical-path host carries every optional lane; Python deps unhashed
- **Severity:** P3
- **Domain:** supply chain
- **Path:** bootstrap
- **Evidence:** rembg pulls onnxruntime and others unpinned; Chrome is `stable`; Blender and ImageMagick come from distro packages.
- **Remediation:**
  - Fixed: model SHA-256 recorded in the lock.
  - Open: `pip install --require-hashes -r requirements-authoring.lock`; a Chrome version lock recorded (lane only).
- **Owner:** HB
- **State:** PARTIAL

### CF-OPUS-026 — `main` CI red at `61d86cd` for a non-Forge reason
- **Severity:** P3
- **Domain:** CI hygiene
- **Path:** `tests/contracts/test_owner_runtime_mcp_contract.py::test_owner_runtime_mcp_tools_list_is_parseable_without_network`
- **Evidence:** a 5 s `subprocess` timeout for the node MCP shim on the runner. The previous `main` run and this environment pass with the same code (node 22, 13/13).
- **Remediation:** raise the timeout or close stdin explicitly; owned by the Hermes MCP area, not changed here.
- **Owner:** RE
- **State:** OPEN

### CF-OPUS-027 — Identity colour alarm is weak
- **Severity:** P2
- **Domain:** validation
- **Path:** `RiveContractTest.identityColourFamilies`
- **Evidence:** it passes if ≥ 0.4 % of upper-half samples are light-neutral (a white jacket suffices) and ≥ 0.25 % are cyan. There is no dark-hair or skin-tone check.
- **Remediation:** after CF-OPUS-001, compare region palettes (hair, skin, visor, jacket) of the IDLE 320 dp frame to owner reference crops with ΔE2000 bounds (Part G automated layer).
- **Owner:** RE
- **State:** OPEN

### CF-OPUS-028 — No automated comparison against owner references
- **Severity:** P2
- **Domain:** visual QA
- **Evidence:** only mean-RGB regression against M2 baselines exists; nothing compares to the owner art.
- **Remediation:** Part G tool set: SSIM on the silhouette mask, palette ΔE2000, face-region landmark IoU, contact sheets, diff heatmaps. Runs in CI on downloaded frames and in `10-validation/`. It assists; it never accepts.
- **Owner:** RE
- **State:** OPEN

### CF-OPUS-029 — Stale canon (Editor-era receipt schema, M2 procedure, export checklist)
- **Severity:** P2
- **Domain:** docs
- **Path:** pack §6/§14/§16/§20/§21/§24, `VAN_RIVE_EXPORT_CHECKLIST.md`, supplement, READMEs
- **Remediation:** updated to CLI reality and the new evidence rules.
- **Owner:** RE
- **State:** FIXED

### CF-OPUS-030 — Toolchain lock import was loose
- **Severity:** P2
- **Domain:** provenance
- **Path:** `cli.cmd_tools_import_lock`
- **Evidence:** it accepted a lock without `repository_sha`, and any Rive version or archive checksum.
- **Remediation:** it requires an exact 40-hex SHA equal to HEAD, plus the repository-pinned Rive version and archive SHA (read from the bootstrap).
- **Validation:** `test_toolchain_import_requires_exact_repository_sha`, `test_toolchain_import_refuses_unpinned_rive_release`
- **Owner:** RE
- **State:** FIXED

### CF-OPUS-031 — STATUS blockers were a hard-coded list
- **Severity:** P3
- **Domain:** status truth
- **Evidence:** `source admit` re-added `RIVE_CLI_UNPINNED` after the lock import.
- **Remediation:** `_current_blockers()` derives them from the manifest, TOOLS and status.
- **Validation:** `test_blockers_are_derived_from_truth_not_a_stale_list`
- **Owner:** RE
- **State:** FIXED

### CF-OPUS-032 — Device checklist has no CLI writer and evidence is not hashed
- **Severity:** P3
- **Domain:** provenance
- **Remediation:** add `cli device record --check NAME --result PASS|FAIL --evidence FILE` that copies into `11-device-evidence/`, hashes it, and binds the APK/Rive SHA read from the device's Settings → Character row (an owner action).
- **Owner:** RE
- **State:** OPEN

### CF-OPUS-033 — Transparency test only sampled corners
- **Severity:** P1
- **Domain:** aura separation
- **Path:** `RiveContractTest.artboardIsTransparentOnThreeBackgrounds`
- **Evidence:** a radial halo that does not reach the 8×8 corner patches passed.
- **Remediation:** translucent coverage (a pixel differing from both backgrounds and between them) is bounded by `max_translucent_fraction` (0.08); the fraction is written to evidence.
- **Owner:** RE
- **State:** FIXED

---

## PART C — Toolchain matrix

| Tool | Current role | Decision | Class | Quality benefit | Automation method | Commander | Deterministic | Notes |
|---|---|---|---|---|---|---|---|---|
| Rive CLI 1.1.1 (pinned archive + binary SHA) | RML → `.riv` build, verify, inspect | **Keep** | CRITICAL PATH | reproducible candidates from source | `rive-create/rml-put/rive-verify/rive-candidate/rive-inspect` | yes | yes for the scaffold (CI evidence); re-prove on the rig | expressiveness probe required (CF-OPUS-024) |
| rive-android 9.6.5 | runtime + contract validator | **Keep** | CRITICAL PATH | the only truth about loadability | CI `RiveContractTest` | via CI | yes | a version change reopens M2–M4 (CF-D-11) |
| Inkscape (distro, bare version pinned) | layer sheet authoring, geometry bounds, layer-sheet render | **Keep** | CRITICAL PATH | manual vector cleanup is where identity fidelity is won | `vectors-admit`, `svg-lint` (`--query-all`) | yes | yes (headless) | record `inkscape_reported` too |
| Android SDK/emulator API-31 + AVD | local iteration | **Keep** | CRITICAL PATH (CI) / local iteration | contract/regression frames | `emulator-up`, `instrumentation` | yes | mostly (swiftshader) | local results are never evidence of record |
| Java 17 | Gradle | **Keep** | CRITICAL PATH | — | — | indirect | yes | |
| FFmpeg | frame sequences → WebM | **Keep** | SPECIALIST QUALITY | motion review | `frames-to-webm` (bitexact flags) | yes | yes | |
| ImageMagick (`montage`) | contact sheets | **Keep** | SPECIALIST QUALITY | at-a-glance review of 18 states + 14 actions at 3 sizes | `contact-sheet` | yes | yes (date chunks stripped) | |
| rembg + BiRefNet General | background removal from owner renders | **Keep, lane only** | OPTIONAL | clean alpha from high-res renders (once supplied) | `remove-bg` into `02–05` | yes | model SHA in lock; ONNX CPU is deterministic per build | never on flat or AI-invented art; output is a candidate |
| VTracer | raster → SVG draft | **Keep, lane only; demote** | OPTIONAL | a tracing underlay for manual redraw | `vectorize` into `05-vectors-candidate` | yes | yes | **dangerous as final geometry** (noisy paths, colour banding, would blow the 1200-path budget); never admitted without manual redraw |
| Potrace | monochrome tracing | **Keep (tiny)** | OPTIONAL | clean single-colour masks (hair locks, visor rim) as redraw underlays | not on the worker (Inkscape's Trace Bitmap wraps it) | — | yes | redundant with VTracer for colour; fine for line masks |
| Pillow | image lane utility | **Keep** | OPTIONAL | lane scripts | venv | — | yes | |
| Blender | 3D pose reference | **Keep, lane only** | OPTIONAL | pose/turnaround reference for hands and ¾ views **only if** the owner supplies nothing better | not on the worker (arbitrary-code risk; sandbox per pack §21) | no | n/a | not a critical-path tool; never renders final art |
| Chrome + Xvfb | optional web Editor review | **Keep, lane only** | OPTIONAL | human visual refinement lane (Part E §E10) | manual | no | no (human) | cloud-account dependent |
| **ADD: scikit-image + OpenCV (headless)** | SSIM, silhouette IoU, ΔE2000 palette, diff heatmaps | **Add** | SPECIALIST QUALITY | objective drift alarms vs owner references (Part G) | `python -m tools.character_forge.compare` (to build) | yes | yes | BSD/Apache; CPU; bootstrap venv, pinned + hashed |
| **ADD: MediaPipe Face Landmarker** (optional) | eye/mouth landmark positions on renders vs reference | **Add, optional lane** | OPTIONAL | catches face-proportion drift | lane script | yes | yes (CPU) | Apache-2.0; stylized chibi faces may detect poorly, so advisory only |
| **ADD: Perfetto** (`record_android_trace`) | S24 frame-timeline profiling | **Add** | CRITICAL for S24 qualification | the only trustworthy performance number (CF-OPUS-018) | owner runs on the S24 via adb; trace committed | no (physical device) | yes | Apache-2.0 |
| ComfyUI (TOOLS.yaml lane) | AI reconstruction | **Do not install** | — | — | — | — | — | prohibited from filling identity gaps until CF-OPUS-003 is resolved with real art |
| Rive MCP / agent tooling | — | **Do not add now** | — | — | — | — | — | not needed: RML is text and the worker already exposes it; revisit only if first-party and pinned |

---

## PART D — Final production pipeline

Stages are strict; each has an automatic gate and, where it matters, a human gate. **Bold** = owner-only.

| # | Stage | Inputs | Actor | Tool / command | Output | Automatic validator | Visual validator | Evidence | Promotion gate | Rollback |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | **Identity resolution** | CF-OPUS-001/003 | **Owner** | edit identity doc + `identity_lock` (contract revision) | one canonical trait set; high-res originals | `test_rive_contract.py` | owner | commit | owner commit | revert commit |
| 1 | Workstation qualification | exact SHA | Commander | bootstrap (root, once) → `W qualify` → `W import-toolchain-lock` | `qualification.json`, TOOLS pins | qualifier GREEN; lock import checks | — | report SHA in STATUS next_action | all checks GREEN | re-bootstrap |
| 2 | Source admission | `visual-authority/assets` | Commander → **Owner** | `W source-admit` → **`cli owner confirm-source --confirm-complete`** | MANIFEST sources | `gate m0` | owner reviews the list (no placeholders) | receipts | M0 PASS | re-admit resets confirmation |
| 3 | Vector candidate (optional lanes) | admitted sources | Vector agent | `W remove-bg`, `W vectorize` → `05-vectors-candidate/` | underlay drafts | — | — | lane outputs are never admitted | none | delete |
| 4 | Clean layer sheet | reference + drafts | **Human vector artist** (Inkscape; agent assists) | redraw → `W vector-put van_layers.svg` → `W svg-lint` → `W vectors-admit … artist:<id>` | `van_layers.svg`, `layer_sheet.png` | lint (groups, palette, bounds, 1200-path budget) | independent reviewer + owner spot-check vs reference | `cli review record --target layer` (non-author) | M1 PASS | new SVG supersedes |
| 5 | Rig-capability probe | pinned CLI | Rive engineer agent | `W rive-create rml/probe` → features in RML → `W rive-candidate rml/probe core 0` → stage on a `forge/probe` branch | probe `.riv` | CI RiveContractTest core mode (contract failures expected; load must succeed) | — | CI run + list of supported features | owner decides CLI-only vs hybrid (§E10) | n/a |
| 6 | Core rig | M1 SVG, §12 | Rive engineer (human animator reviews motion) | `W rml-put` iterations → `W rive-verify` → `W rive-candidate rml/van core N` → `W rive-receipt` → `W rive-stage … core_rig` → `W forge-push forge/core-N` | candidate + receipt | CI: RiveContractTest core + `character-forge-gate` | motion critic on contact sheet + WebM | `cli rive record-validation` with `van_validation.json` + screenshots | core validation PASS | increment N |
| 7 | Independent core critique | core frames/video | Independent critic (not the author session) | review against Part F/G | written critique in `10-validation/` | — | yes | critique file | rework or proceed | back to 6 |
| 8 | **Owner core verdict on S24** | CI debug APK | **Owner** | Settings → Character → Preview staged candidate → **`cli owner record-core-verdict`** | ACCEPTANCE.core_rig | `gate m2` | owner | verdict bound to CI run | M2 PASS; skeleton frozen | REVISE → 6 |
| 9 | Full rig | frozen skeleton | Rive engineer + animator | as 6 with `full`, all 18 + 14 | full candidate | CI full mode (noise-floor distinctness, all actions via action_code, translucency, soak) | motion critic | as 6 | full validation PASS | increment N |
| 10 | Independent full review | frames, WebM | Independent reviewer | `cli review record --target full` | reviews.full_rig | `gate m3` | yes | review line | M3 PASS | back to 9 |
| 11 | Integration | M3 candidate | Engineer | `cli android integrate --candidate …` → push | `van_runtime.riv` == `assets/van.riv` | CI production mode incl. `productionAvatarPathKeepsRive`; `character-forge-gate` | — | `record-validation --stage production` | production PASS | revert commit |
| 12 | **S24 physical qualification** | CI debug APK | **Owner** | walk DEVICE_CHECKLIST + Perfetto trace | DEVICE_CHECKLIST + `11-device-evidence/*` | `gate m4` (SM-S928*, files exist, SHA match) | owner | files + trace | all PASS | fix → 9/11 |
| 13 | **Owner acceptance** | S24 | **Owner** | Settings → Character → Accept (biometric) → `cli owner record-acceptance --from-gateway` | ACCEPTANCE.final | `gate m4` | owner | signed token | M4 PASS | new asset = new acceptance |
| 14 | Release | M4 | Engineer (not Commander) | `cli release promote` → commit → CI green | `rive/manifest.json`, QUAL-EMB-01 READY | `gate m5`, maturity gate | — | release commit CI | M5 PASS | revert release commit |

---

## PART E — Rig specification

The public contract is unchanged. No blocking defect in it was found. Everything below is internal to the artboard.

### E1 Layer hierarchy (required 22 + required-for-M2 `extra_`)

```
Van (artboard, transparent, character bbox ≥ 6 % margin; aura-safe empty ring outside it)
└─ root (bone: root) ─ hips
   ├─ body: underlayer, jacket, extra_jacket_back, extra_jacket_collar, extra_accents_cyan
   ├─ neck
   │  └─ head (bone: head; pivot at neck top)
   │     ├─ extra_hair_back, hair (front), extra_hair_lock_l, extra_hair_lock_r
   │     ├─ face, extra_face_shadow, extra_jaw
   │     ├─ eye_l / eye_r ─ extra_sclera_*, extra_iris_*, extra_pupil_*, extra_catchlight_*,
   │     │                  extra_lid_upper_*, extra_lid_lower_*          (clip: eye socket)
   │     ├─ brow_l / brow_r (extra_brow_inner_*, extra_brow_outer_* as mesh points)
   │     ├─ mouth_inner (clip) ─ extra_teeth, extra_tongue; mouth_upper; mouth_lower
   │     ├─ visor_frame, visor_lens (only translucent layer), extra_visor_glint
   │     └─ extra_headband (only if CF-OPUS-001 keeps it)
   ├─ arm_l_upper ─ arm_l_fore ─ hand_l (extra_glove_l, extra_fingers_l_{index,mid_ring_pinky,thumb})
   ├─ arm_r_upper ─ arm_r_fore ─ hand_r (same)
   └─ orb (separate root child; nested artboard optional) ─ orb_shell, orb_core, extra_orb_face, extra_orb_eyes
```

### E2 Bones and constraints
- **Bones:** root, hips, spine, chest, neck, head. Per arm: shoulder, upper, fore, hand, plus three finger groups. Hair: 2–3 two-bone chains for secondary motion. Orb: one bone.
- **IK:** a two-bone IK per arm to a hand target. POINT_* and PRESENT_CARD animate the target, not joint angles, so directions stay exact.
- **Transform constraints:** head follows chest at 30 % (overlap). The orb follows a lag target driven by chest + gaze (damped).
- **Meshes:** face (jaw, cheeks), mouth (weighted to the jaw bone plus viseme shape keys via bones), brows, hair front (weighted to the hair chains), jacket front (weighted to the chest/shoulders). Keep a mesh vertex count ≤ ~60 per mesh.

### E3 Gaze
- `attention_x/y` ∈ [−1, 1], dead zone |v| < 0.05.
- **Eyes lead:** pupils offset up to 35 % of iris radius, via a 1D blend on each axis, clamped inside the socket clip. There is no crossing: both eyes share the same offset.
- **Head follows:** yaw ±12°, pitch ±8°, 120 ms later.
- **Chest follows:** yaw ±4°, 200 ms later.
- **Damping:** implemented as blend-state interpolation (~100 ms eyes, ~220 ms head) so input jumps never snap (board: "Gaze response 100 ms").
- **Micro-saccades:** every 1.2–2.5 s, a small offset ≤ 6 % in IDLE/ATTENTIVE/LISTENING only.

### E4 Blink
- A dedicated state-machine layer, independent of `state`. Interval 3–6 s (random), 120–160 ms. 15 % chance of a double blink.
- **Suppressed** during POINT_*, PRESENT_CARD and the first 300 ms of URGENT/ERROR entry.
- Lids close slightly faster than they open (40/60 split).
- SLEEPING holds the lids closed; WARNING/URGENT lengthen the interval (focus).

### E5 Mouth and visemes
- **Viseme layer:** a 1D blend on `viseme` (0 neutral, 1 small, 2 medium spread, 3 wide vertical, 4 rounded; >4 is treated as 1).
- **Amplitude layer:** `mouth_open` drives the jaw bone (0–100 %) additively on top of the viseme shape.
- **Coarticulation:** shape blend duration 60–80 ms, so consecutive visemes morph rather than cut.
- **Silence:** when `speaking` is false, ease to closed in 120 ms.
- **Speech head motion:** additive nod ±2° correlated with `mouth_open` peaks (layered, not keyed).

### E6 State and action layers (no spaghetti)

| Layer | Driven by | Mode |
|---|---|---|
| L0 base breathing/idle micro-motion | always | additive loop (≈ 4 s, ≤ 2 % scale), period never < 6 s visible (compose 2 non-harmonic sines) |
| L1 durable pose | `state` (0–17) | one blend/state per durable state from "Any State" with `state == n`, entry ≤ 300 ms; unknown values → IDLE |
| L2 urgency intensity | `urgency` | 1D additive blend, active only in WARNING/ERROR/URGENT |
| L3 gaze | `attention_x/y` | 2 × 1D additive |
| L4 face (blink, brows, lids) | internal timers, `state` | additive |
| L5 speech | `speaking`, `mouth_open`, `viseme` | additive over any pose |
| L6 listening | `listening` | additive lean-in / ear-side head tilt |
| L7 finite action | rising edge of `action_code` (authoritative) **or** its trigger | **latched one-shot** (plays to completion 600–1800 ms, ignores `action_code` returning to 0; a new code interrupts after the anticipation phase); upper-body override, speech and blink continue |
| L8 orb | `state`, action | independent loop + reactions |

`action_code` is authoritative because production never fires triggers (CF-OPUS-009). Wire each trigger to the same one-shot so the contract's triggers stay meaningful. Guard against double-play when both arrive in one frame.

### E7 Transitions
- Durable → durable: 200–300 ms, ease-in-out (cubic 0.4, 0, 0.2, 1).
- Into WARNING/ERROR/URGENT: a 80 ms anticipation dip, then a 220 ms rise.
- Out of URGENT: 400 ms settle (board: "Urgent pulse 400 ms").
- Return to IDLE: 300 ms.

### E8 Performance budget
- ≤ 1200 paths (lint), ≤ 20 meshes, ≤ 60 vertices each.
- ≤ 8 simultaneously active animation layers.
- ≤ 6 clipping shapes (eye sockets, mouth, visor); no blur/feather on large shapes.
- Translucency only on the visor lens and orb glow (enforced ≤ 8 % coverage).
- No nested artboard unless the orb needs its own state machine.

### E9 Reset semantics
- An invalid `state` → IDLE.
- An invalid `action_code` → no action.
- `speaking=false` → mouth closes.
- Process recreation starts at IDLE with the inputs the runtime re-pushes on the first `update`. `VanRiveAvatar` pushes all 9 each composition.

### E10 Hybrid Editor lane (only if the stage-5 probe shows RML cannot express a needed feature)
- **Constraint:** Editor edits are not representable as RML, so an Editor-refined `.riv` has no reviewable source. Governance therefore requires an owner decision amending CF-D-02.
- **Deterministic round trip:**
  1. RML build (CLI) → baseline `.riv` + receipt.
  2. Human refinement in the Editor on an **export of that baseline**.
  3. Export a `.riv` plus the Editor's `.rev` backup.
  4. A new receipt with `authoring_tool: rive_editor`, `editor_version`, `rev_sha256` and `parent_candidate_sha256` (the CLI baseline).
  5. `rive inspect` diff (inputs/artboards/state machines) between parent and child must show no contract change.
  6. The full validator runs as normal.
- **Engineering change needed:** gates currently accept only `authoring_tool == rive_cli` (fail-closed by design).

---

## PART F — Motion bible

**Personality:** a calm, capable, owner-oriented professional with a slight futurist edge.

**Motion rules:**
- Motion is **economical**: small amplitudes, confident holds.
- Never bouncy, cute or jittery.
- Squash and stretch only on the orb.
- Anticipation is ≤ 15 % of amplitude.
- Overshoot is ≤ 8 % then settles in 150 ms.
- Secondary motion comes from hair locks and the orb only.

**Readability:** anything that must read at 96 dp is carried by **head angle, arm silhouette and orb position**, not by facial detail. Faces must read at 320 dp and stay plausible at 48 dp.

### F1 Durable states

| State | Intention | Pose / torso | Face & eyes | Head | Arms / hands | Orb | Loop | Entry easing | Interruptible | 96 dp read |
|---|---|---|---|---|---|---|---|---|---|---|
| OFFLINE | unavailable, not broken | slight slump 2° | lids 60 %, no saccades | down 5° | relaxed low | dim, docked at shoulder, no drift | 8 s slow breath | 300 ms ease-out | yes | slump + dim orb |
| CONNECTING | coming online | straightening | lids rising, 1 blink | lifts to neutral | — | orb pulses slow (1 Hz) | 6 s | 250 ms | yes | orb pulse |
| IDLE | present, unobtrusive | neutral, breathing | soft gaze, saccades | tiny drift ±1.5° | rest | slow figure-8 drift | ≥ 8 s composite | — | yes | calm baseline |
| ATTENTIVE | focused on owner | chest +2° toward viewer | lids +10 % open, brows up 5 % | slight forward tilt | rest | orb stops drifting, faces viewer | 8 s | 200 ms | yes | forward lean |
| LISTENING | receiving | lean-in 3°, head tilt 6° | steady gaze at attention target, fewer blinks | tilt toward speaker side | one hand relaxed near chest | orb leans toward owner, faint pulse synced to mic RMS if available | 7 s | 180 ms (board 150 ms) | yes | head tilt |
| THINKING | cognition, not loading | weight shift back 2° | eyes up-left 20 %, slow blink | tilt 4° | hand to chin (right) | orb orbits slowly behind the shoulder | 9 s | 250 ms | yes | hand-to-chin silhouette |
| SEARCHING | scanning outward | upright | eyes sweep L↔R in steps (not smooth) | small yaw scans ±8° | — | orb moves out front as a "lens" | 6 s sweep cycle | 250 ms | yes | head yaw sweep + orb forward |
| WORKING | executing | slight forward, shoulders engaged | eyes down-front | down 4° | both hands low-front "operating" small cycles | orb projects (brighter core) | 7 s | 250 ms | yes | hands forward |
| DELEGATING | sending outward | open posture | eyes follow the orb outward | turns toward the orb | right hand gestures outward then returns | orb travels out 20 % and back | 6 s | 250 ms | yes | arm + orb outbound |
| SPEAKING | articulation layered on activity | inherits underlying pose | L5 speech, eye contact | speech nods | small beat gestures (optional, ≤ 1 per 3 s) | orb brightens with amplitude | per speech | 120 ms (board) | yes | mouth + nods (48 dp: orb brightness) |
| WAITING | patient, ambient | neutral, weight on one leg | slow blinks, occasional glance | occasional look-away | hands clasped | orb idles lower | ≥ 10 s | 300 ms | yes | clasped hands |
| WAITING_FOR_OWNER | explicit request for the owner | faces viewer squarely | direct gaze, brows slightly raised | still | one palm-up "your turn" held | orb hovers at chest, gentle cyan pulse | 8 s | 250 ms | yes | palm-up hold (distinct from WAITING) |
| DEGRADED | reduced capability, still working | posture normal (must not suppress local activity) | one fewer expression layer (brows flatter) | normal | normal | orb desaturated 40 %, flicker ≤ 1/8 s | inherits | 300 ms | yes | orb dimming (activity still visible) |
| WARNING | caution | chest back 2°, shoulders square | brows in 15 %, focused | still, then a slow nod | one hand raised low "hold" | orb amber-free (colour belongs to the aura), moves in front defensively | 8 s | 80 ms anticipation + 220 ms | yes | raised hand |
| ERROR | failure, owning it | slight slump + head down 6° | brows concerned, lids 80 % | down | hands open low (apologetic) | orb drops 15 %, slow | 8 s | same | yes | head-down open hands (colour-blind readable) |
| SUCCESS | satisfied, not childish | upright, chest up 2° | soft smile, eyes narrow slightly | small nod | thumbs-up or small fist, held 600 ms, then relaxes | orb one gentle spin | one-shot flavour then IDLE-like loop | 200 ms | yes | thumbs-up |
| URGENT | needs attention now | forward 4°, squared | wide eyes, no blinks for 300 ms | faces viewer | both hands forward "stop/look" | orb front and centre, fast pulse 2 Hz (`urgency` scales amplitude) | 4 s | 80 + 220 ms | only by owner-driven state | forward lean + both hands (distinct from WARNING/ERROR by posture) |
| SLEEPING | calm, low energy | slump 3°, slower breath (6 s) | eyes closed | tilted 8° | rest | orb dimmed, resting on the shoulder | 12 s | 400 ms | yes (wake via CONNECTING/ATTENTIVE) | closed eyes + tilted head |

**Severity ladder (silhouette):** WARNING = one raised hand, upright → ERROR = head down + open low hands → URGENT = forward lean + both hands. Colour is the aura's job; the character must read in grey.

### F2 Finite actions (latched, 600–1800 ms, anticipation → main → return)

| Action | Duration | Anticipation | Main pose | Return | Notes for 96 dp / crop |
|---|---|---|---|---|---|
| HELLO_WAVE | 1400 ms | shoulder dip 80 ms | right hand up, 2.5 wave cycles (wrist + fingers), head tilt 5°, smile | 300 ms | hand above head line so it survives a bottom crop |
| ACK_NOD | 650 ms | chin up 3° | single nod 8° + blink | settle 150 ms | readable from head alone |
| POINT_LEFT/RIGHT/UP/DOWN | 1200 ms | torso counter-turn 3° | straight arm via IK to a target 1.5 heads out in the direction; index extended; eyes and head look at the target | 300 ms | the arm silhouette alone must indicate the direction; no ambiguity between UP and TARGET |
| POINT_TARGET | 1200 ms | as above | IK target from `attention_x/y` at trigger time | 300 ms | point + gaze converge |
| CELEBRATE | 1800 ms | crouch 3 % | both fists up briefly, orb spins once, smile | 400 ms | no jump (professional) |
| CAUTION | 1000 ms | lean back 2° | palm-out "careful" at chest height, brows in | 300 ms | palm silhouette |
| CONFIRM | 900 ms | — | thumbs-up + nod | 250 ms | distinct from ACK by the hand |
| SHRUG | 1100 ms | — | shoulders up 6 %, palms up, head tilt, eyebrows up | 300 ms | shoulders + palms |
| PRESENT_CARD | 1500 ms | turn 5° | right arm extends palm-up to the side where a card appears; orb moves aside; eyes to the card, then back to the viewer | 300 ms | arm + orb aside |
| OPEN_PANEL | ≥ 600 ms (latched) | — | both hands sweep outward (open) | 250 ms | runtime holds 240 ms: must latch (CF-OPUS-020) |
| CLOSE_PANEL | ≥ 600 ms (latched) | — | hands sweep inward (close) | 250 ms | as above |

**Common rules:**
- Speech continues during actions.
- Gaze resumes 200 ms after the return.
- Blink is suppressed during POINT_* and PRESENT.
- A new action may interrupt only after the current action's anticipation.

---

## PART G — Visual quality plan

| Check | Automated evidence (assists) | Human judgement (decides) |
|---|---|---|
| Identity checklist (hair, visor, skin, eyes, jacket, underlayer, accents, orb, headband/gloves per CF-OPUS-001) | lint palette families; region ΔE2000 vs owner token per region (to build, CF-OPUS-027) | independent reviewer at M1/M3; **owner** at M2/M4 |
| Silhouette | mask IoU of the IDLE 320 dp frame vs the owner reference silhouette (scaled to head height) ≥ 0.85 | reviewer |
| Face | eye-centre / mouth-centre ratios (landmarks, advisory) within 5 % of reference | **owner** |
| Colour | palette ΔE2000 per region ≤ 8 (skin tighter once the tone is fixed) | owner |
| Expression | 18 state frames vs board §06 expressions, side by side on a contact sheet | reviewer + owner |
| Compact avatar | 96 dp and 48 dp captures (now produced) vs the lock sheet's floating/docked frames | **owner on the S24** |
| Overlay readability | the same on light/dark/busy backgrounds | owner |
| Motion consistency | WebM per state/action + transitions (CF-OPUS-021); motion critic scores against Part F | independent motion critic, then owner |
| Screenshot/contact sheet | `W contact-sheet` over `rive/<mode>/*.png` | reviewer |
| Aura separation | translucency ≤ 8 %, transparent corners; S24 "no double glow" | owner on the S24 |
| S24 physical | DEVICE_CHECKLIST (13 checks) with committed evidence files, Perfetto trace, thermal note | **owner (only)** |

Automated checks can **fail** a candidate. They can never **pass** identity. Only owner verdicts (M2 core, M4 acceptance) and the independent review (M1, M3) promote.

---

## PART H — Commander orchestration plan

**Roles (no theatre; one output each):**

| Role | Model / actor | Output |
|---|---|---|
| Manager | ChatGPT/Hermes | plans the next command, reads `STATUS.json`, never promotes |
| Source-art analyst | vision model (independent session) | trait inventory vs canon, flags conflicts (as CF-OPUS-001) |
| Vector artist | **human** in Inkscape (an agent may prepare underlays) | `van_layers.svg` |
| Rive engineer | coding agent via Commander | RML, candidates, receipts |
| Motion critic | independent vision model session (never the author) | scored critique vs Part F |
| Android validator | CI | `van_validation.json` |
| Performance reviewer | owner-run Perfetto on the S24 plus an agent to read the trace | trace summary |
| Independent reviewer | a person, or an agent session that did not author | `review record` line |

**Council:** only at M1 and M3 review. Two independent critics, and disagreement escalates to the owner.

**Sequence** (`W` = `sudo -n -u vanforge /usr/local/libexec/van-character-forge-worker`):

```
W doctor
W status                                   # read next_action and blockers
W qualify                                  # must be GREEN; else stop
W import-toolchain-lock                    # only after a fresh bootstrap/lock
W source-admit                             # ── STOP: owner runs `cli owner confirm-source`
W gate m0
W remove-bg / W vectorize                  # optional underlays → 02–05
                                           # ── STOP: human vector artist produces van_layers.svg
W vector-put van_layers.svg < …; W svg-lint …; W vectors-admit … artist:<id>
                                           # ── STOP: independent reviewer `review record --target layer`
W gate m1
W rive-create …/rml/probe; W rml-put …; W rive-verify; W rive-candidate …/rml/probe core 0
W forge-push forge/probe "rig capability probe"      # ── STOP: owner decides CLI-only vs hybrid
W rive-create …/rml/van
loop:
  W rml-put …/rml/van <files>; W rive-verify …; W rive-inspect …
  W rive-candidate …/rml/van core N
  W rive-receipt <candidate> …/rml/van <svg_sha> agent:<id> 1.1.1
  W rive-stage <candidate> core_rig
  W forge-push forge/core-N "core rig N"
  (Manager downloads CI artifacts; engineer runs `cli rive record-validation`)
  W contact-sheet <frames> core-N.png; W frames-to-webm <frames> core-N.webm
  motion critic → rework until green + critique clean
                                           # ── STOP: owner S24 core verdict (`record-core-verdict`)
W gate m2
(full rig loop as above with `full`)       # ── STOP: independent review `review record --target full`
W gate m3
                                           # ── STOP (engineer, not Commander): `cli android integrate`, push, production validation
                                           # ── STOP: owner S24 checklist, Perfetto, biometric acceptance
                                           # ── STOP (engineer): `cli release promote`
```

**Commander never:** confirms sources, records a verdict or review, integrates, accepts, releases, logs into Rive, or enables cloud write or push.

---

## PART I — Bootstrap and repository remediation (applied)

**Commits on `claude/van-forge-audit-11n4wh`:**

| Commit | Scope |
|---|---|
| `c79c91d` | Inkscape pin fix (CF-002), strict lock import (030), truthful blockers (031), RML source binding (007), palette bypass (013) |
| `dcc9822` | CI outcome binding + blocking gate (005/006), reviewer independence (015), S24 model/evidence (016) |
| `33358bf` | bounded Commander authoring surface, jail, root-owned authority, `rive-login` removal (004/010/012); qualifier (011); bootstrap lock fields; smoke number input + determinism (023) |
| `83c162a` | RiveContractTest noise-floor distinctness, action_code-only actions, translucency bound, 96/48 dp evidence, production VanAvatar path (008/009/033) |
| `aa42245` | canon docs aligned (029) |
| `20e558d` | gfxinfo reset before soak (018 partial) |
| (this commit) | this report; `van-ci` now runs on `forge/**` so worker-pushed candidates are validated |

**Not changed (owner authority or out of scope):**
- `rive_contract.json`
- identity canon
- lint colour families (CF-OPUS-014)
- the required layer list (017)
- runtime voice (019)
- the action hold times (020)
- the MCP test (026)

---

## PART J — Go-live checklist for actual `.riv` development on Netcup

All must be true before ChatGPT/Hermes starts M1/M2 authoring. Items marked **(OW)** are owner-only; **(EX)** are external.

- [ ] **(OW)** CF-OPUS-001 resolved: one canonical skin tone, headband decision, proportions, gloves. `VAN_CHARACTER_VISUAL_IDENTITY.md` + `identity_lock` revised and committed.
- [ ] **(OW)** CF-OPUS-003 resolved: high-res originals committed (≥ 2048 px; front, ¾, side, rear, expressions, gestures, hands, orb, visor). Placeholders renamed or removed from `visual-authority/assets/`.
- [ ] **(OW)** CF-OPUS-014 lint families updated to the resolved canon.
- [ ] `claude/van-forge-audit-11n4wh` merged. `main` CI green, including `character-forge-gate`. CF-OPUS-026 fixed or re-run green.
- [ ] **(EX)** `dial-control` online in Desktop Commander. Bootstrap run as root with `VAN_COMMIT_SHA=<merged main SHA>`. It prints `AUTHORING_WORKSTATION_READY`.
- [ ] `W qualify` GREEN (strict at bootstrap). `qualification.json` committed or attached as evidence. `rive_authoring_smoke` shows `number_input` and `reproducible_build: true`.
- [ ] `W import-toolchain-lock` succeeded. `TOOLS.yaml` shows `rive_cli: 1.1.1` and a bare Inkscape version. The commit is pushed.
- [ ] **(OW)** `vanforge` GitHub credential limited to `forge/*` pushes (branch protection on `main`), then `sudo touch /etc/van-character-forge/allow-git-push`. Cloud write stays **disabled**.
- [ ] `W source-admit` done → **(OW)** `cli owner confirm-source --confirm-complete --date …` → `W gate m0` PASS (`build_ready: true`).
- [ ] Contract integrity: `pytest tests/contracts -q` green on the exact SHA; `test_rive_contract.py` green.
- [ ] Evidence directories exist: `visual-authority/character-forge/{05-vectors-candidate,06-vectors-clean,09-rive-working/rml,10-validation,11-device-evidence}`.
- [ ] CI availability: a push to `forge/*` triggers `van-ci` (`forge/**` added to `on.push.branches` on this branch; confirm after merge with the stage-5 probe push).
- [ ] Android emulator: `W emulator-up` → `EMULATOR_READY` (software accel acceptable, KVM preferred).
- [ ] Stage-5 rig-capability probe run. The CLI-only vs hybrid decision is recorded in `MANIFEST.decisions` **(OW)**.
- [ ] Owner review path: the CI `van-debug-apk` installs on the S24; Settings → Character → "Preview staged candidate" reachable in debug builds.
- [ ] **(OW/EX)** S24 path: the device is available; Perfetto (`record_android_trace`) works over adb; the gateway `/v1/visual/acceptance` is reachable from the device.

---

## Truth answers (§45)

| # | Question | Answer (evidence) |
|---|---|---|
| 1 | Can ChatGPT/Hermes orchestrate the real build through Commander? | **Yes, once the branch is merged and the owner provisions the `forge/*` push credential** (CF-004). Not demonstrated on a live host (dial-control offline). |
| 2 | Can the toolchain reproduce deterministically? | **Scaffold: yes** (CI 35933638590, identical SHA twice). **Real rig: unproven**; the smoke plus `rive-candidate` from committed RML make it checkable. |
| 3 | Premium animation rather than a valid file? | **Not yet assured:** the layer model (017), RML expressiveness (024) and motion evidence (021) are open. |
| 4 | Identity protected against drift? | **Engineering: yes** (lint bypass closed, owner-only promotion). **Canon: no**, until CF-001/003/014 are resolved by the owner. |
| 5 | Every state and action expressible convincingly? | Contract complete; Part F defines it. The validator now fails indistinct states and missing actions. |
| 6 | Natural speech, gaze, attention? | Rig spec E3–E5 defines it; offline-TTS producer defect (019) open. |
| 7 | Readable at floating size? | 96/48 dp captures now produced; judged by the owner on the S24. |
| 8 | Aura separated? | Transparency + translucency bound enforced (033); S24 "no double glow" check. |
| 9 | Android loads and drives the exact candidate? | Candidate: yes (CI). Production: `productionAvatarPathKeepsRive` through the real `VanAvatar`; actions via `action_code`. |
| 10 | Evidence tied to exact bytes? | Yes: receipt → RML digest → candidate SHA → CI run + commit → device SHA → signed acceptance → release manifest. |
| 11 | Bad candidates fail automatically? | Yes: lint, receipt, stage, `ci_binding`, `character-forge-gate`, gates m0–m5 (mutation-tested). |
| 12 | Optional AI tools cannot self-promote? | Yes: lanes write only to `02–05`; admission and reviews refuse authors and Commander. |
| 13 | Route for independent critique? | Yes: the review command enforces non-authorship; Part H assigns an independent critic. |
| 14 | Owner-only gates preserved? | Yes: none were touched; `rive-login` was removed from Commander; switches are root-owned. |
| 15 | Resumable from repository truth? | Yes: `STATUS.json` next_action and blockers (now truthful), this report, pack Rev 2 + 2.1. |

**Production-ready: NO.** The engineering system is now capable and fail-closed. The owner-held identity inputs (CF-OPUS-001, 003, 014) and the rig-capability probe (024) must land before authoring would produce the owner's VAN rather than an approximation of it.
