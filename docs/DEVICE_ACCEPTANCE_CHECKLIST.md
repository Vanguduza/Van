# Physical device acceptance checklist

Use with `python tools/certification/device_cert_probe.py` (fails closed when adb has no device,
and records the handset model: only an SM-S928* counts). Run the items in the order and with the
prerequisites in [`PHYSICAL_TEST_RUNBOOK.md`](PHYSICAL_TEST_RUNBOOK.md). The item keys match the
probe's `CHECKLIST`; `tests/contracts/test_device_checklist_matches_probe.py` keeps them equal.

| Item | Expected evidence | Pass? |
|---|---|---|
| install | debug APK installed via adb | |
| provisioning | signed provisioning payload accepted; device paired and hardware-bound (`/v1/devices` lists it) | |
| overlay | floating Van visible; drag/dock works | |
| notification_listener | permission granted; triage items appear | |
| mic | speech input permission + capture | |
| tts | spoken response audible | |
| biometric | A4 prompt succeeds/denies correctly | |
| drag_dock | overlay reposition persists | |
| rotation | overlay survives orientation change | |
| process_kill | overlay/service recovers after force-stop | |
| doze | queued intent survives Doze | |
| reboot | service/onboarding state recovers | |
| offline_queue | commands encrypt to queue while offline | |
| reconnect | queue replays after gateway returns | |
| secret_notification | OTP/secret content redacted | |
| barge_in | speech interrupt behaves safely | |
| share_to_van | share intent routes into Command Centre | |
| google_capability_status | Command Centre shows mesh configured/unverified (never assumed WORKING) | |
| rive_failure_to_canvas | missing/bad `.riv` falls back to Candidate B art (renderer ladder `RIVE → CANDIDATE_B → CANVAS`); Settings › Character names the renderer in use | |
| reduced_motion | motion respects system setting / Canvas still legible | |
| wake_word | with the wake bundle installed, "Hey Van" is heard from the Command Centre and the overlay; without it, no microphone notification appears and Settings says why | |
| embodiment_candidate_b | Candidate B art is on-model in the overlay (compact/expanded) and the Command Centre; state marks readable in grayscale | |
| flame_aura | flame envelope follows the figure, no line geometry, no flame over the face; 60 fps with the aura on (janky frames ≤ 5%) | |
| trading_aura_overlay | with the overlay visible and a paired device, a trade state change recolours the aura within ~6 s; a closed position shows one white pulse | |

Owner sign-off remains an EXTERNAL gate even when this matrix is filled.
