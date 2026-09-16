# External certification gates

These require owner credentials, live Google surfaces, provider/runtime access, physical hardware, or environments that repository CI cannot truthfully certify.

Resolved 2026-09-15: the live Hermes `van` profile is installed and certified on `dial-hermes-control`; Sonnet 5 executed a live VAN canary and the core Hermes/DIAL services and delegation suites passed. This is no longer an external gate.

Rechecked 2026-09-16: owner Google consumer and Gemini planes remain authenticated on Hermes. Permanent Workspace Desktop OAuth consent is now complete and the refresh credential is encrypted in the VAN gateway vault. `workspace_api` is `CONFIGURED`; Gmail, Calendar, Drive, People/Contacts and Tasks APIs are still disabled in the Google Cloud project, so live canaries remain blocked until those APIs are enabled. Cloud/Enterprise-only capabilities remain separate.

Resolved 2026-09-15: the delegated `antigravity_worker_account` is authenticated in a separate isolated runtime home. Live model discovery and a Gemini 3.8 Flash generation canary passed; no canonical Google/API credential inheritance is permitted. Token-free evidence is recorded at `artifacts/google/antigravity_worker_live_attestation.json`. Antigravity is no longer an external authentication/generation gate.

Resolved 2026-09-15 (workstation): local Project Truth mounts for `van`, `dial`, `dde`, `gtr`, `goat`, and `aeci` resolve via `registries/project_mounts.json` + `tools/projects/sync_project_truth.py` offline cache. Gateway live PUT still requires a running gateway.

| Gate | Prerequisite | Repo-side readiness |
|---|---|---|
| Canonical owner Google principal | Hermes-authenticated owner Google account | hashed principal registration + Hermes attestation import |
| Google Workspace OAuth live | Desktop OAuth client + owner consent complete; enable Workspace APIs | encrypted refresh credential installed; `workspace_api` CONFIGURED; live Gmail/Calendar/Drive/Contacts/Tasks canaries pending API enablement |
| Gemini runtime | authenticated on Hermes | mesh Gemini family CONFIGURED via Hermes attestation; live READY needs per-capability canary receipt |
| Gemini Live | Hermes runtime + live endpoint canary | deterministic route; CONFIGURED on Hermes auth |
| Deep Research | Hermes Gemini runtime + quota canary | deterministic route; CONFIGURED on Hermes auth |
| Gemini Notebook personal | owner Google session on Hermes | consumer capability CONFIGURED via attestation |
| Gemini Notebook Enterprise | eligible Cloud/Enterprise setup | still EXTERNAL (cloud plane) |
| Mixboard / Stitch / Flow / AI Studio / Workspace Studio | owner Google session on Hermes | consumer capabilities CONFIGURED via attestation |
| Jules | owner Google sign-in on Hermes | CONFIGURED via attestation; READY needs live worker receipt |
| Nano Banana / Veo | Hermes Gemini runtime + quota canary | CONFIGURED via attestation |
| Google ADK/A2A | owner-administered Cloud/runtime | still EXTERNAL (cloud plane) |
| Physical Samsung device | USB device + permissions | `tools/certification/device_cert_probe.py` + `docs/DEVICE_ACCEPTANCE_CHECKLIST.md` |
| Artist `.riv` | Rive editor | contract + Canvas fallback + handoff |
| Owner visual acceptance | owner review | acceptance matrix |
| Signed production release | production keystore | Gradle wiring + `android/keystore.properties.example` |
| GitHub Actions canonical workflow path | credential with workflow scope | `tools/ci/install_github_workflow.py` + YAML in `tools/ci/` |

## Google certification rules

1. `CONFIGURED` is **not** `READY`.
2. Consumer Google sessions may not be certified by cookie presence alone.
3. `READY` requires an evidence pointer recorded through the Google identity broker.
4. No raw Google email, cookie, OAuth token, API key, or service-account private material is stored in the capability registry or artifact provenance.
5. Workspace OAuth, Gemini runtime, Cloud/service identity and consumer sessions must remain separate credential planes. Explicit delegated identities are allowed only for their bound capabilities and may not inherit owner authority or credentials.
6. Missing or unverified capability must return an explicit degraded/auth-required state; never simulate success.
7. Hermes-hosted authentication is recorded as attestation evidence; it does not copy tokens into Van.

## Physical device checklist

Install, overlay, notification listener, mic, TTS, biometric, drag/dock, rotation, process kill, Doze, reboot, offline queue, reconnect, secret notification, barge-in, share-to-VAN routing, Google capability status display, Rive failure → Canvas, reduced motion.
