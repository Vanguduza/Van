# PR #60 Audit — Character Forge M0–M5, Netcup Bootstrap, and `.riv` Completion Build

- **Repository:** `Vanguduza/Van`
- **PR:** #60 `gpt/van-character-forge-engineering-20260922` (draft)
- **Head audited:** `e796563` (`character-forge: reject unversioned host toolchain locks in tests`)
- **Base:** `3c337ef` (post PR #58 `main`)
- **Diff size:** 59 files, +4302 / −153, 44 commits
- **Reference canon:** `docs/character_forge/VAN_CHARACTER_FORGE_DEVELOPMENT_PACK_REV_2.md` (Rev 2 pack), plus the PR's own `VAN_CHARACTER_FORGE_RIVE_CLI_SUPPLEMENT_REV_2_1.md` (Rev 2.1 supplement)
- **Audit date:** 2026-09-23

## 1. Verdict

| Question | Answer |
|---|---|
| Were M0–M5 *implemented* (tooling, gates, tests, bindings) correctly? | **Mostly yes, with one blocking defect.** M0, M1, M4 and M5 are faithful to the pack. M2/M3 engineering is present but **cannot pass as written**: the gates and the stage command still require a pinned Rive Editor version and a `rive_editor_version` receipt field, while TOOLS.yaml and the receipt writer moved to `rive_cli` / `authoring_version`. |
| Were M0–M5 *executed* (character actually built)? | **No, and the PR does not claim so.** `MANIFEST.yaml` has `sources: []`, `owner_confirmed_complete: false`; STATUS.json has `build_ready: false`, QUAL-EMB-01 `EXTERNAL_ARTEFACT`. All six gates fail with truthful reasons. |
| Is the Netcup bootstrap set up correctly? | **Structurally sound, with two concerns.** Scripts parse, refuse non-control hosts, pin Android command-line tools by SHA, confine the Commander to a non-owner worker surface. Concerns: the Rive installer is trust-on-first-use, and the workstation installs every optional lane on the critical-path host. |
| Is the `.riv` completion build set up correctly? | **Partially.** The validator path (test APK asset → `RiveContractTest` on the API 31 emulator → gate reads run URL) is correct and proven in CI (8 tests skip as `NO_RIVE_ASSET` today). The build-authority premise changed from Rive Editor to the Linux Rive CLI without updating the gate logic, and the Rive CLI is a technical preview whose state-machine authoring surface is not yet demonstrated by anything in the PR. |

Recommended disposition: **do not merge yet**. Fix the three code defects in §4.1 (small, mechanical), decide the Rive-CLI canon question in §4.2 explicitly, and split or justify the off-scope changes in §6. Everything else is ready.

## 2. Evidence collected

All runs were performed on a clean checkout of head `e796563`.

| Check | Result |
|---|---|
| `tests/contracts/test_character_forge_*.py` + `test_rive_contract.py` | 40 passed |
| `backend/tests/test_visual_acceptance.py` | 6 passed |
| Full `tests/contracts` | 435 passed, 1 skipped |
| `python -m tools.character_forge.cli status` | Honest: build_ready false, EXTERNAL_ARTEFACT, next_action → Netcup bootstrap |
| `python -m tools.character_forge.cli gate m0..m5` | All FAIL with accurate blockers (source not admitted, owner confirmation pending, Inkscape/Rive CLI unpinned, **Rive Editor unpinned**, no candidate, no acceptance) |
| GitHub checks on `e796563` (run 35812420733) | 5/5 green: backend, android-and-visual-evidence, android-instrumentation, mutation, canonical-tree |
| Instrumentation log | `RiveContractTest` 8 tests SKIPPED (`NO_RIVE_ASSET`); "Tests 21/13 completed (8 skipped) (0 failed)"; screenshots artifact uploaded |
| `evidence/van-system-audit/component_ledger.json` | Present on the branch (226 KB); written by `_update_release_truth` |
| `tools/ci/github-actions-ci.yml` vs `.github/workflows/van-ci.yml` | Byte-identical |
| Rive CLI existence | Confirmed via public search: official Rive CLI, technical preview, installer `https://releases.rive.app/cli/install.sh`, Linux x86_64 supported, authors `.riv` from Rive Markup Language (RML). `rive.app` and `releases.rive.app` are egress-blocked from this environment, so the docs and installer bytes could not be inspected directly. |

## 3. Milestone-by-milestone assessment

### M0 — Source admission and baseline (pack §6.0)

**Correct.** `cli source admit` hashes the declared source set, writes `sources[]` with SHA-256, records `baseline_sha`, resets `owner_confirmed_complete` to false when the set changes, and appends a receipt. `gates.m0()` requires owner confirmation, admitted sources, and a baseline SHA that matches. Mutation test `test_mutated_baseline_sha_is_rejected_by_m0` covers tampering.

**Defect (minor):** after admission, `cmd_source_admit` resets `status["blockers"]` to a hard-coded list containing `RIVE_EDITOR_UNPINNED`. The rest of the CLI removes `RIVE_CLI_UNPINNED` after `tools import-toolchain-lock`, so the stale Editor blocker can never be cleared and STATUS.json will lie about what blocks the build. (`tools/character_forge/cli.py:67`)

**Not executed:** `sources: []`. The owner has not run admission. This is expected at this stage.

### M1 — Vector layer sheet (pack §6.1, §11)

**Correct.** `svg_lint.py` enforces required layer groups, geometry presence, and the hair palette lock (`PALETTE_OUTSIDE_LOCK:hair:` is rejected by `test_mutation_dark_hair_is_rejected`). `gates.m1()` requires Inkscape pinned, an admitted `layer_svg` artifact, and an independent/owner review whose SHA matches the current layer. Vectorization is recorded as a `vectors` receipt. Matches pack §11 requirements.

**Not executed:** no `layer_svg` artifact admitted.

### M2 — Core rig candidate on the emulator (pack §6.2, §12)

**Engineering present, gate unpassable.** Three inconsistent authorities coexist:

1. `TOOLS.yaml` now has `critical_path.rive_cli` (`UNPINNED`, `required_from: M2`) and moved `rive_editor` to `review_lanes` with `version: OPTIONAL`.
2. `receipts.packaging_receipt` writes `authoring_tool: rive_cli` and `authoring_version`; `cli rive receipt` refuses an `--authoring-version` that differs from the pinned `rive_cli` version. This is the new, intended path.
3. `gates.m2()` (`gates.py:102`) still appends `"Rive Editor version unpinned"` when `critical_path.rive_editor.version` is empty. Because `rive_editor` no longer lives under `critical_path`, this branch **always** fires. `gates._receipt_problems` (`gates.py:53-54`) compares `row["rive_editor_version"]` (always `None`, since receipts no longer carry that field) with `str(critical_path.rive_editor.version)` (the string `"None"`). The two never compare equal, so every receipt is flagged "Rive Editor version mismatch". `cli.cmd_rive_stage` (`cli.py:180`) refuses any receipt whose `rive_editor_version` differs from `_pinned_tool("rive_editor")`, so `rive stage-candidate` refuses every receipt produced by `rive receipt`.

Net effect: even with a perfect `.riv`, a pinned Rive CLI, a matching receipt, and a green emulator run, **M2 cannot reach PASS and the candidate cannot be staged into the test APK**. This is the single blocking defect of the PR.

Why CI did not catch it: no test drives a receipted candidate through `rive stage-candidate` or into an `m2()` PASS. `test_unreceipted_candidate_is_not_stageable` only checks the negative. The M4 fixture monkeypatches `gates.m3` to `[]`, which also bypasses M2. Recommend adding a positive-path test: pin `rive_cli`, write a receipt via `packaging_receipt`, stage, and assert that `_receipt_problems` returns only the emulator/owner items.

The rest of M2 is faithful: candidate ≥1024 bytes, staged to `androidTest/assets/van_candidate.riv` and debug assets, `RiveContractTest` is the sole validator, `core_rig` records `candidate_sha256`, `ci_run`, `emulator_validation`, `owner_verdict`, and baseline PNG evidence is required when validation is PASS.

### M3 — Full rig (pack §6.3, §13)

Same structure as M2 and inherits the same defect via `_receipt_problems`. The `RiveContractTest.kt` (394 lines) covers the pack §10 cases: artboard/state-machine names, 9 inputs, 8 triggers, 18 durable states, 14 finite actions, identity lock, and the janky-frame threshold read from STATUS.json `performance.max_janky_percent`. The `RiveCandidateHostActivity` debug host is appropriately confined to the debug manifest.

### M4 — Owner acceptance and device qualification (pack §6.4, §15)

**Correct and well-tested.** Backend `VisualAcceptanceService` verifies an `OwnerAuthorityToken` with act `visual-accept` and subject `sha256:<riv sha>`, persists to `visual_acceptances` (MIGRATION_30, SCHEMA_VERSION 30), refuses replay of a token against a different artifact, and is retained via `ops/retention.py`. Routes `POST/GET /v1/visual/acceptance` are registered and listed among device-proof endpoints. Android `VanCharacterAcceptance` + `SettingsRoute` sign via `BiometricGate.requestA4CommandApproval` and call `recordVisualAcceptance` / `latestVisualAcceptance`. `gates.m4()` requires DEVICE_CHECKLIST.yaml for `SM-S928B` with `renderer_rive_active: PASS`, matching `rive_sha256`, and a `final` acceptance record. Mutation tests cover deleted acceptance and changed bytes.

### M5 — Release binding (pack §6.5, §16)

**Correct.** `cli release` writes `visual-authority/rive/manifest.json` with artboard, state machine, git SHA, `rive_sha256`, contract SHA, rive-android pin, authoring tool/version, emulator run, device checklist and acceptance pointers. `record_apk_signing_identity.sh` gained the `rive_sha256` extension. `_update_release_truth` flips QUAL-EMB-01, the identity doc, and `component_ledger.json` only when M4 passes. `test_shipped_asset_matches_source_when_present` and `test_release_requires_acceptance_receipt` guard the binding. Drift guards from pack §22 (no input renames, no contract edits, CLI-only integration, no hand-written ACCEPTANCE.yaml) are enforced by `test_contract_guard_*` and the gate's contract-SHA checks.

## 4. Findings

### 4.1 Blocking defects (code)

| # | Location | Problem | Fix |
|---|---|---|---|
| D1 | `tools/character_forge/gates.py:102-103` | `m2()` requires `critical_path.rive_editor.version`; TOOLS.yaml no longer has it → permanent "Rive Editor version unpinned" | Delete the Editor branch; keep the `rive_cli` branch at line 98 |
| D2 | `tools/character_forge/gates.py:53-54` | `_receipt_problems` compares `rive_editor_version` to the Editor pin; receipts carry `authoring_tool`/`authoring_version` | Compare `row["authoring_tool"]=="rive_cli"` and `row["authoring_version"]==critical_path.rive_cli.version` |
| D3 | `tools/character_forge/cli.py:180` | `cmd_rive_stage` refuses receipts lacking `rive_editor_version` → every candidate refused | Same field swap as D2 |
| D4 | `tools/character_forge/cli.py:67` | `source admit` resets blockers with stale `RIVE_EDITOR_UNPINNED` | Replace with `RIVE_CLI_UNPINNED` |
| D5 | `tests/contracts/` | No positive-path test for receipt → stage → M2 | Add one so D1–D3 cannot regress |

### 4.2 Canon deviation (decision required)

The Rev 2 pack states CF-D-02 "Rive Editor is the final authoring tool; version pinned in TOOLS.yaml" and CF-D-03 "minimal critical path is Inkscape → Rive; AI reconstruction, segmentation and motion labs are optional lanes". PR 60 introduces a Rev 2.1 supplement that makes the **Linux Rive CLI** the M2/M3 build authority and demotes the Editor to an optional review lane, and the bootstrap installs rembg/BiRefNet, VTracer, Blender and Chrome on the same control host with `lanes.rembg_birefnet`, `vtracer`, `blender` all `enabled: true`.

This is a legitimate direction (it makes the build reproducible on Linux, which the Editor cannot be), but:

- The Rive CLI is an official **technical preview** as of this audit. Nothing in the PR demonstrates that RML can express the contract's 9 inputs, 8 triggers, 18 durable states and 14 finite actions, nested artboards, or the identity lock. The bootstrap only probes `rive --help`. Before M2 depends on it, a smoke test should author a minimal `.riv` with one state machine, one boolean input and one trigger, stage it, and get `RiveContractTest` to fail for the right reasons (missing states) rather than for load failure.
- The supplement should be adopted into the Rev 2 pack as an explicit amendment to CF-D-02/CF-D-03 (with owner sign-off), not left as a side document that the gates half-follow. Half-adoption is what produced D1–D4.
- Enabling every lane on the critical-path host contradicts CF-D-03's intent to keep the deterministic path minimal. Either move lanes to `enabled: false` by default or document why they are on the control host.

### 4.3 Bootstrap (`deploy/character-forge/*`)

Good:
- `bootstrap-netcup-authoring.sh` refuses non-control hosts (tested), pins Android command-line tools by SHA-256 (tested), shares image pins with `requirements-authoring.txt` (tested), runs the forge user unprivileged, and cannot promote forge truth (tested).
- `commander-worker.sh` exposes an allow-listed command surface; `test_commander_surface_cannot_perform_owner_or_release_authority` proves owner/release commands are excluded.
- `qualify-netcup-authoring.sh` emits a JSON check list and a `toolchain.lock.json` that `cli tools import-toolchain-lock` consumes to pin `rive_cli` and `inkscape`; the head commit adds rejection of unversioned locks.

Concerns:
- **B1 — Trust-on-first-use installer.** The Rive installer is fetched over HTTPS and its SHA is recorded on first run into `rive-cli-installer.sha256`; later runs fail only if the bytes change. The first run has no independent expectation. Given the Rive CLI is a preview and the installer likely fetches a versioned binary itself, record the expected installer SHA in the repo (like `ANDROID_CLI_SHA256`) or pin a specific CLI release tarball and verify its checksum, so the pin is reviewable in git rather than only on the host.
- **B2 — Sudoers passthrough.** The Commander sudoers rule grants `NOPASSWD` to the worker with `*` args and the worker `exec rive "$@"`. Any Rive CLI subcommand (including future ones that write outside the workspace or publish) is reachable. Constrain to a fixed set of `rive` subcommands or a working-directory jail.
- **B3 — Single-host blast radius.** GPU/AI lanes, Blender, Chrome and the Android emulator on the Netcup DIAL control host make the qualification lock large and slower to reproduce. Acceptable if the owner accepts it, but it should be stated as a decision.

### 4.4 `.riv` completion build (validator and integration)

Correct as designed by the pack:
- Candidate lives in the test APK (`androidTest/assets/van_candidate.riv`), so the production APK is untouched until `cli release`.
- `RiveContractTest` is the sole validator; CI job `android-instrumentation` runs it on the API 31 x86_64 emulator and uploads screenshots via AGP `additionalTestOutputDir`. Today it skips 8 tests with `NO_RIVE_ASSET`, which is the honest state.
- Gate reads `ci_run` URL and `emulator_validation` from STATUS.json; `test_pass_without_instrumentation_run_is_invalid` prevents a PASS without a run.

Gaps:
- The gate trusts STATUS.json's `emulator_validation: PASS` and `ci_run` as written by the CLI operator. There is no check that the referenced run actually executed `RiveContractTest` against the candidate SHA. A cheap improvement: have the instrumentation job emit `van_candidate.sha256` into the artifact and have `cli android record-run` verify it against `core_rig.candidate_sha256` before writing PASS.
- The D1–D3 defects sit exactly between "receipt" and "stage", so the completion build is presently blocked before the emulator step.

## 5. Honesty of the PR's own status claims

The PR does not overclaim. STATUS.json, MANIFEST.yaml, `cli status` and `cli gate` all report the true state (nothing admitted, nothing built). The README and Rev 2.1 supplement describe the Netcup bootstrap as the next action. This is compliant with pack §18/§22 truthfulness rules.

## 6. Off-scope changes bundled in the PR

These are unrelated to Character Forge and should be split out or explicitly justified in the PR description:

| File | Change | Risk |
|---|---|---|
| `android/.../FloatingOverlayService.kt` + new `OverlayLifecycleReceivers.kt` | Refactor to 447 lines, receivers extracted | Behavioural change to a production service with no forge relevance; instrumentation stayed green, but reviewers need to know |
| `android/.../HistoryScreen.kt` | Formatting only | Noise |
| `deploy/van-trading-core/qualify.sh` | −50 lines: repairs a corrupted block | Good fix, wrong PR |
| `trading/architecture/stack_lock.json` + `trading/tests/test_stack_lock.py` | `durable_workflows.pin_status: PINNED_POST_FABLE_CLOSURE`; test loosened | Loosening a stack-lock test is a governance change and needs its own review |
| `pytest.ini` | `pythonpath` adds `.` | Enables `tools.character_forge` imports in tests; fine, but note it |
| `tools/audit/fable_anti_gap_check.py` | GAP-F-013/026 regex changes | Changes what the anti-gap checker accepts; must not weaken the closure evidence — worth a one-line rationale |
| `docs/VAN_RIVE_AUTHORING_HANDOFF.md` | Rewritten for Rive CLI | Consistent with the supplement |

## 7. Recommended next steps (ordered)

1. Fix D1–D4 and add the positive-path test (D5). Small, mechanical, unblocks M2/M3.
2. Ratify Rev 2.1 as an amendment to the Rev 2 pack (CF-D-02/CF-D-03), or revert to Editor authority. Record the decision in MANIFEST.yaml `decisions` and the pack.
3. Add the Rive CLI smoke test described in §4.2 before anyone spends authoring time.
4. Replace the trust-on-first-use installer lock with a repo-committed expected SHA or a pinned release checksum (B1); narrow the sudoers/worker `rive` passthrough (B2).
5. Split the off-scope changes in §6 into their own PR(s), or list and justify each in the PR body.
6. Then run the bootstrap on Netcup, qualify, import the toolchain lock, and begin M0 (source admission and owner confirmation).
