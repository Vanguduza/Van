# Physical test runbook: VAN on the Galaxy S24 Ultra

Written 2026-09-24 by the pre-device audit (`docs/audit/pre-device-2026-09-24/PRE_DEVICE_AUDIT.md`).
The checklist that records results is [`DEVICE_ACCEPTANCE_CHECKLIST.md`](DEVICE_ACCEPTANCE_CHECKLIST.md).
This document does not record any result. It says what has to be true before each part of the
checklist can be run honestly, and in what order to run it.

## 1. What a run can and cannot prove

| Can prove on this device | Cannot prove yet, whatever the run shows |
|---|---|
| install, onboarding grants, the overlay and its motion, rotation, process kill, reboot, Doze | the authored `van.riv` rig (none exists; VAN is shown as Candidate B art) |
| Candidate B embodiment, flame aura, reduced motion, renderer fallback | the Rive silhouette sampler (it only runs when a `.riv` loads) |
| provisioning, pairing, hardware binding, biometric A4, offline queue and replay, trading aura (once §2 is done) | "Hey Van" acceptance (the trained wake bundle is an external artefact), Gemini-backed answers (credits depleted), the Remote Browser stream (no stream host) |

Only an SM-S928* counts. `device_cert_probe.py` records the model and warns on anything else.

## 2. Prerequisites for the connected half of the checklist

The gateway only signs a provisioning payload whose `gateway_url` is **HTTPS**
(`backend/van_gateway/connectivity/provisioning.py`). The debug APK's allowance for a loopback
gateway is therefore unreachable, since no payload for a loopback address can be signed. **Until the
gateway has an HTTPS ingress, the phone cannot be paired.** That leaves `provisioning`,
`biometric`, `offline_queue` replay, `reconnect`, `share_to_van` routing,
`google_capability_status` and `trading_aura_overlay` blocked.

1. **Ingress.** Provision the named Cloudflare Tunnel (`tools/runtime/install_van_cloudflare_tunnel.sh`;
   it refuses `trycloudflare.com` and needs `~/.config/van/cloudflare-tunnel.token` and
   `public-gateway.env` with `VAN_PUBLIC_GATEWAY_URL=https://…`). It is an open external gate in
   `EXTERNAL_GATES.md`, and it is needed for production anyway.
   Using a throwaway quick tunnel for a test session instead is an **owner decision**. The device
   pins the URL it is provisioned with, so every tunnel restart means provisioning again, and
   nothing measured that way is production evidence.
2. **Connectivity signing key** on the gateway host. Nothing produced one before this audit:
   ```
   python3 tools/provisioning/generate_connectivity_key.py --out ~/.config/van/connectivity-1.pem
   ```
   Put the printed `VAN_CONNECTIVITY_SIGNING_KEY_FILE` and `VAN_CONNECTIVITY_SIGNING_KID` into the
   gateway environment and restart it. Keep the printed `VAN_CONNECTIVITY_TRUSTED_KEYS=…` line
   for step 3; it is one line on purpose.
3. **Enrolment credential.** A `DEVICE_ENROLMENT`-scoped internal-control token (see
   `backend/van_gateway/auth/control_scopes.py`), for the provisioning tool only.

## 3. Build and install

```
cd android
./gradlew :app:assembleDebug -PVAN_CONNECTIVITY_TRUSTED_KEYS='connectivity-1=-----BEGIN PUBLIC KEY-----\n…'
python3 ../tools/certification/device_cert_probe.py --install
```

A debug APK built without `VAN_CONNECTIVITY_TRUSTED_KEYS` installs and runs, but it refuses
every provisioning payload (`ProvisioningIntake.configured == false`). That is fine for §4.1 and
useless for §4.2. The debug APK is signed with the building machine's debug key, so build every
test APK on the same machine, or uninstall before installing a new one.

**Phone settings before the first run.** On the S24, set:
- Settings › Apps › VAN › Battery › **Unrestricted**;
- Settings › Battery › Background usage limits: VAN **not** in sleeping or deep-sleeping apps.

One UI otherwise stops the overlay's foreground service. That failure is Samsung's policy, not
VAN's, and it would make `process_kill`, `doze` and `reboot` fail for the wrong reason. VAN does
not request a battery-optimisation exemption itself.

## 4. Order of the run

### 4.1 Offline half (no gateway needed)
`install` → onboarding grants (`overlay`, `notification_listener`, `mic`, the notifications
permission) → `embodiment_candidate_b` → `flame_aura` → `drag_dock` → `rotation` →
`reduced_motion` → `rive_failure_to_canvas` → `secret_notification` → `tts` → `barge_in` →
`wake_word` (negative case: no bundle means no microphone notification, and Settings shows why)
→ `process_kill` → `reboot` → `doze`.

For `flame_aura`, capture frame timing with
`adb shell dumpsys gfxinfo com.dial.van framestats` while the overlay animates. Janky frames at
or below 5% is the threshold the instrumentation job uses.

### 4.2 Connected half (after §2)
```
ssh -L 8787:127.0.0.1:8787 dial-hermes-control      # the gateway stays loopback-only
python3 tools/provisioning/provision_owner_device.py \
    --gateway http://127.0.0.1:8787 --device-gateway-url https://<public host> \
    --internal-token "$VAN_DEVICE_ENROLMENT_TOKEN" --note s24-physical-test
```
Then run `provisioning` → `biometric` → `google_capability_status` → `share_to_van` →
`offline_queue` (airplane mode, issue commands) → `reconnect` (airplane mode off, queue replays)
→ `trading_aura_overlay` (a demo or paper account only: every account defaults to demo, and live
modes need a signed mandate).

## 5. Recording

Fill the `Pass?` column with evidence pointers (screenshots, `framestats` output, gateway
audit rows), never with a bare tick. Owner sign-off and biometric acceptance remain the
owner's own act (Character Forge M5). Nothing in this runbook records them.
