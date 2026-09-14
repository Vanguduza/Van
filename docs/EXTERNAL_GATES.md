# External certification gates

These require owner credentials, live Google surfaces, provider/runtime access, physical hardware, or environments that repository CI cannot truthfully certify.

| Gate | Prerequisite | Repo-side readiness |
|---|---|---|
| Live Hermes profile install | SSH/API to Hermes host | install/doctor scripts, profile/policy tests |
| Canonical owner Google principal | owner runs identity setup with their Google account subject | identity broker + hashed-subject registration tool |
| Google Workspace OAuth live | OAuth client + owner consent + refresh token | encrypted vault + proper refresh→access-token exchange + revoke/status |
| Gemini runtime | separate Gemini runtime credential under owner-administered Google environment | capability registry, Hermes provider policy, planner |
| Gemini Live | runtime credential + live endpoint access | deterministic capability route; live session adapter remains external-runtime work |
| Deep Research | supported Gemini runtime + quota | deterministic route + provenance contract; live execution requires provider runtime |
| Gemini Notebook personal | owner Google session/account availability | consumer capability bridge contract + Android/share/Drive path; no private API dependency |
| Gemini Notebook Enterprise | eligible Cloud/Enterprise setup and service identity | separate cloud-service capability route |
| Mixboard | owner account + current Labs availability | governed artifact packet/consumer-surface route; no fake public API |
| Stitch | owner account + current Labs availability | governed design route; no private API dependency |
| Antigravity | owner Google sign-in + authorised dev environment | Hermes worker contract + deterministic route |
| Jules | owner Google sign-in + GitHub connection | bounded repo-worker contract + deterministic route |
| Workspace Studio | eligible owner Workspace/account surface | governed consumer workflow route |
| Nano Banana / Veo | Gemini/API runtime credential and quota | media capability routes and provenance contract |
| Flow / AI Studio | owner Google session | governed consumer-surface route |
| Google ADK/A2A | owner-administered Cloud/runtime where used | interoperability route; Hermes remains orchestration authority |
| Physical Samsung device | USB device + permissions | Android app and share ingress exist; device checklist required |
| Artist `.riv` | Rive editor | contract + Canvas fallback + handoff |
| Owner visual acceptance | owner review | acceptance matrix |
| Live Project Truth mounts for other projects | accessible truth files + SHA capture | sync tooling exists |
| Signed production release | production keystore | Gradle wiring/docs ready |
| GitHub Actions canonical workflow path | credential with workflow scope | YAML retained in `tools/ci/` |

## Google certification rules

1. `CONFIGURED` is **not** `READY`.
2. Consumer Google sessions may not be certified by cookie presence alone.
3. `READY` requires an evidence pointer recorded through the Google identity broker.
4. No raw Google email, cookie, OAuth token, API key, or service-account private material is stored in the capability registry or artifact provenance.
5. Workspace OAuth, Gemini runtime, Cloud/service identity and consumer sessions must remain separate credential planes even though they trace to the same owner Google account.
6. Missing or unverified capability must return an explicit degraded/auth-required state; never simulate success.

## Physical device checklist

Install, overlay, notification listener, mic, TTS, biometric, drag/dock, rotation, process kill, Doze, reboot, offline queue, reconnect, secret notification, barge-in, share-to-VAN routing, Google capability status display, Rive failure → Canvas, reduced motion.
