# VAN whole-project audit before physical testing (2026-09-24)

Audited base: `main` at `be49e8e` (PR #65 merged), whose CI (`van-ci`, `canonical-tree-guard`) was green.
Scope: can a Galaxy S24 Ultra test run start, and will what it measures be true?
Earlier audits are not repeated here. The Fable register (`docs/audit/van-fable-whole-project-2026-09-21/`)
has all 28 of its gaps dispositioned, and its evidence still stands.

## 1. Baseline

| Check | Result |
|---|---|
| `pytest` (whole repository) | 3762 passed, 4 skipped, before any change |
| `tests/` (contracts and repo level) after this audit's changes | 586 passed, 2 skipped |
| CI on `be49e8e` | `van-ci` success; `canonical-tree-guard` success |
| Production acceptance (`tools/ci/production_acceptance.py`) | 104 requirements: 59 repository-proven, 38 blocked external, 7 owner-deployment. Verdict `REPOSITORY_COMPLETE_PENDING_EXTERNAL` |
| Red-team register | 72 scenarios: 63 `PASS`, 9 `BLOCKED_EXTERNAL` |
| Committed secrets | none found (private keys, cloud API keys, bot tokens, keystores, `.env`) |
| Character Forge | `current_stage: admission`; no gate promoted |

## 2. Findings

Severity is relative to the physical test. **P1** means the run cannot start or a checklist row
cannot pass. **P2** means the run would measure the wrong thing. **P3** means documentation truth.

| ID | Sev | Finding | Status |
|---|---|---|---|
| PD-01 | P1 | **The wake listener was never started.** `WakeListenerService` is declared and typed `microphone`, and the component ledger records it as `INTEGRATED` / `COMPLETE`. But nothing in the app called `start()`. The ledger's "production caller" was the service's own `onStartCommand`. With a correct wake bundle installed, VAN would still never listen for "Hey Van". | **Fixed.** `CommandCentreActivity.onResume` → `WakeListenerService.startIfReady` starts it from a visible activity, as Android 14+ requires for a microphone service. It refuses without a ready model or the microphone grant, and never re-arms an armed listener, because `arm()` clears the active turn. Contract test `test_foreground_services_are_started.py` fails on the old code and passes on the new. Ledger corrected. |
| PD-02 | P1 | **The phone cannot be paired until the gateway has an HTTPS ingress.** The gateway signs provisioning payloads only for `https://` (`connectivity/provisioning.py`). The debug APK's loopback allowance (`ProvisioningIntake`, `allowInsecureLoopback = BuildConfig.DEBUG`) is therefore unreachable. That blocks the provisioning, biometric, reconnect, share, Google-status and trading-aura rows. | **Open, external.** Provision the named Cloudflare Tunnel, an existing external gate. A test-only quick tunnel or a debug-only loopback payload would change the provisioning security model, so either is an **owner decision**. The runbook's §2 sets out the choice. |
| PD-03 | P1 | **Nothing produced the connectivity signing key or the APK's trust anchor.** Without the key, provisioning answers 503 `connectivity_signing_unconfigured`. Without the anchor, a debug APK refuses every payload. The anchor's format is a trap: `kid=PEM` on one line with escaped `\n`. A PEM pasted as-is parses to no key, and the phone just waits. | **Fixed.** New `tools/provisioning/generate_connectivity_key.py`: a P-256 key, mode 0600, never overwritten, with a key id checked before anything is written. It prints the gateway settings and the exact anchor line. `test_connectivity_key_tool.py` signs a real payload with the gateway's signer and verifies it through a transcription of the device's parser. |
| PD-04 | P2 | **The device checklist no longer covered the product.** It had no rows for provisioning, the wake word, the Candidate B embodiment, the flame aura or the trading aura. "Rive failure → Canvas" predates the Candidate B rung. The probe did not record which handset was attached, so a run on any phone looked the same, and it broke when two devices were attached. | **Fixed.** Five new rows; renderer-ladder wording corrected. The probe now records model, Android release and SDK, warns on anything that is not an SM-S928*, and takes `--serial`. `test_device_checklist_matches_probe.py` keeps the doc and the probe identical. |
| PD-05 | P2 | **`process_kill` could not pass.** A force-stop skips `onDestroy` and sends no broadcast. The boot receiver covers reboot only, so after a force-stop the overlay stayed off until the owner found Settings › Start. | **Fixed.** A single rule, `OverlayRecovery.restoreIfOwnerHadItOn`, is shared by the boot receiver and `CommandCentreActivity.onResume`. It restores only what the owner left on, because a deliberate stop persists `false`. It never double-starts and needs the overlay grant. Contract-tested. |
| PD-06 | P2 | **No runbook.** `android/README.md` said "adb install the debug APK". That APK can never be paired (PD-02, PD-03). Samsung's battery policy stops foreground services unless VAN is set to Unrestricted, and VAN does not ask for an exemption. Without that setting, `process_kill`, `doze` and `reboot` would fail for Samsung's reasons, not VAN's. | **Fixed.** New `docs/PHYSICAL_TEST_RUNBOOK.md` covers prerequisites, build flags, phone settings, an offline-then-connected order and evidence rules. The README points to it. Whether VAN should request the battery exemption itself is left to the owner. |
| PD-07 | P2 | **The identity lock contradicts an adopted owner decision.** The lock forbids `body_hugging_halo`, yet CF-D-06 adopted a flame envelope that "wraps his silhouette". The lock is hash-bound (`HIGHRES_MASTER_APPROVAL.yaml`), so it was not edited. | **Open, owner decision.** Recommended: an R3 lock that scopes `body_hugging_halo` to the Rive artwork, matching the lock's own rule that `van.riv` stays aura-free. |
| PD-08 | P3 | `VAN_IDENTITY_DO_NOT_CHANGE.md` told the artist to preserve a "cyan holographic orb", which the lock now forbids (`legacy_cyan_face_orb`). | **Fixed.** Rewritten from the lock, and it names the lock as the authority. |
| PD-09 | P3 | `VAN_LIVING_WIND_FIELD_RUNTIME_REV_1.md` read as current, although CF-D-06, CF-D-06-REV1 and CF-D-08 replaced it. | **Fixed.** A superseded banner now points to the flame runtime and its contract. |
| PD-10 | P3 | `EXTERNAL_GATES.md` counts had drifted: red team 57/9 out of "sixty-six" and acceptance 60/37/7, against the tools' 63/9 out of 72 and 59/38/7. Its physical list lacked the new rows. | **Fixed.** Counts restated from the tools; the list now links the checklist and the runbook. |

## 3. Areas checked with no new finding

- **Android manifest and services.**
  - Foreground-service types are correct: the overlay is `specialUse` with its subtype, and the wake listener is `microphone`.
  - The exported components are the launcher, the `van://` deep link, the browser link handler, share, and provisioning (guarded by signature, expiry and single use). Everything else is not exported or is protected by a system bind permission.
  - Cleartext is allowed only in the debug manifest. `allowBackup=false`.
  - Onboarding requests the runtime permissions: notifications, microphone, overlay, notification listener.
- **Release build.** It refuses a non-HTTPS gateway, a debug keystore or alias, and an empty trust anchor. `minSdk` 31 is guarded against the voice policy.
- **ARTEMIS WebView.** Same-origin navigation only; no file or content access; no mixed content; Safe Browsing on; no JavaScript bridge.
- **Trading.** Accounts default to `demo=True`. `LIMITED_LIVE` and `AUTONOMOUS_LIVE` need a mandate. The README states that nothing has traded on demo or live. A device run cannot place a real-money order.
- **Interim art.** Candidate B is a 593×593 image (332 KB), loaded once through `imageResource`. Its alpha mask is computed once per image.

## 4. Known, unchanged risks to watch on the device

1. **Aura cost.** The flame planner allocates per frame, and the Rive silhouette sampler (48×48 at about 12 Hz) is untested until a `.riv` exists. Measure with `dumpsys gfxinfo … framestats`; the threshold is 5% janky frames.
2. **Wake word.** The trained keyword bundle, the second-pass speech recogniser and the speaker profile are external artefacts. On this run the wake-word row can only be tested in its negative case: no microphone notification, and Settings says why.
3. **Provider capacity.** Gemini inference is `CAPACITY_LIMITED` (credits depleted). Answers that need it degrade by design; that is not a device fault.
4. **Remote Browser.** There is no stream host, so nothing about the browser stream can be tested on the phone.

## 5. What this audit did not do

It did not compile the Android changes. The Android Gradle Plugin cannot be fetched in this
container, so CI is the compile authority for `WakeListenerService`, `CommandCentreActivity` and
`OverlayRecoveryReceiver`. It ran nothing on a phone. It promoted no gate and recorded no owner,
device or biometric evidence.
