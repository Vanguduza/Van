# Physical device acceptance checklist

Use with `python tools/certification/device_cert_probe.py` (fails closed when adb has no device).

| Item | Expected evidence | Pass? |
|---|---|---|
| install | debug APK installed via adb | |
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
| rive_failure_to_canvas | missing/bad `.riv` falls back to Canvas | |
| reduced_motion | motion respects system setting / Canvas still legible | |

Owner sign-off remains an EXTERNAL gate even when this matrix is filled.
