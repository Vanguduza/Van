# External certification gates

These require environments/credentials not available in pure repository CI.

| Gate | Prerequisite | Repo-side readiness |
|---|---|---|
| Live Hermes profile install | SSH/API to Hermes host | `tools/hermes/install_van_profile.sh`, doctor script, policy tests |
| Google OAuth live | OAuth client + owner consent | Google service + encrypted vault + revoke/refresh APIs + tests |
| Gemini runtime | Separate API key in Hermes | `hermes/providers/gemini.md` |
| Physical Samsung device | USB device + permissions | Debug APK assemble; certification checklist below |
| Artist `.riv` | Rive editor | Contract + Canvas fallback + handoff doc |
| Owner visual acceptance | Owner review | Acceptance matrix |

## Physical device checklist (manual)

Install, overlay, notification listener, mic, TTS, biometric, drag/dock, rotation, process kill, Doze, reboot, offline queue, reconnect, secret notification, barge-in, Rive failure → Canvas, reduced motion.
