# External certification gates

These require owner credentials, live Google surfaces, provider/runtime access, physical hardware, or environments that repository CI cannot truthfully certify.

Resolved 2026-09-15: the live Hermes `van` profile is installed and certified on `dial-hermes-control`; Sonnet 5 executed a live VAN canary and the core Hermes/DIAL services and delegation suites passed. This is no longer an external gate.

Resolved 2026-09-16: permanent Workspace Desktop OAuth consent is complete, the refresh credential is encrypted in the VAN gateway vault, and live Gmail, Calendar, Drive, People/Contacts and Tasks metadata canaries all returned HTTP 200. `workspace_api` is `READY`. Cloud/Enterprise-only capabilities remain separate.

Resolved 2026-09-16: the loopback VAN gateway is restart-persistent and live-certified behind an owner ingress bearer. Device HMAC credentials are encrypted at rest, rehydrate after restart, and device revocation atomically revokes grants and survives a second restart. Token-free evidence is recorded at `artifacts/runtime/van_ingress_live_attestation.json`.

Resolved 2026-09-15: the delegated `antigravity_worker_account` is authenticated in a separate isolated runtime home. Live model discovery and a Gemini 3.8 Flash generation canary passed; no canonical Google/API credential inheritance is permitted. Token-free evidence is recorded at `artifacts/google/antigravity_worker_live_attestation.json`. Antigravity is no longer an external authentication/generation gate.

Resolved 2026-09-15 (workstation): local Project Truth mounts for `van`, `dial`, `dde`, `gtr`, `goat`, and `aeci` resolve via `registries/project_mounts.json` + `tools/projects/sync_project_truth.py` offline cache. Gateway live PUT still requires a running gateway.

| Gate | Prerequisite | Repo-side readiness |
|---|---|---|
| Canonical owner Google principal | Hermes-authenticated owner Google account | hashed principal registration + Hermes attestation import |
| Google Workspace OAuth live | permanent Desktop OAuth + owner consent | READY — encrypted refresh credential installed; Gmail/Calendar/Drive/Contacts/Tasks live canaries all HTTP 200 |
| Gemini runtime | authenticated on Hermes | mesh Gemini family CONFIGURED via Hermes attestation; live READY needs per-capability canary receipt |
| Gemini Live | Hermes runtime + live endpoint canary | deterministic route; CONFIGURED on Hermes auth |
| Deep Research | Hermes Gemini runtime + quota canary | deterministic route; CONFIGURED on Hermes auth |
| Gemini Notebook personal | owner Google session on Hermes | consumer capability CONFIGURED via attestation |
| Gemini Notebook Enterprise | eligible Cloud/Enterprise setup | still EXTERNAL (cloud plane) |
| Mixboard / Stitch / Flow / AI Studio / Workspace Studio | owner Google session on Hermes | consumer capabilities CONFIGURED via attestation |
| Jules | owner Google sign-in on Hermes | CONFIGURED via attestation; READY needs live worker receipt |
| Nano Banana / Veo | Hermes Gemini runtime + quota canary | CONFIGURED via attestation |
| Google ADK/A2A | owner-administered Cloud/runtime | still EXTERNAL (cloud plane) |
| Android owner gateway authentication | owner ingress bearer + enrolled device HMAC | LIVE-CERTIFIED — unauthenticated requests rejected; encrypted device credential survived restart; atomic revoke survived second restart |
| Exa research provider | owner-provisioned Exa API key in gateway secret plane + live canary | repo-side adapter, egress policy, evidence ledger and canary endpoint implemented; `VAN_EXA_EGRESS_ENABLED` remains fail-closed until certified |
| sherpa-onnx Android runtime | pinned official `v1.13.8` Android AAR/native bundle | integration boundary and wake pipeline implemented; production bundle must match official release SHA-256 `633c24321e06b1fe79feafa03ea16cbc0f8a286641e2da3559bac91bdb13bd96` |
| Wake KWS model | owner-approved redistributable/local model capable of `Hey Van` | KWS/verifier interfaces, VAD, thresholds and tests implemented; do not ship official sherpa pretrained KWS weights until model licence/redistribution authority is explicitly established |
| Voice physical certification | Galaxy S24-class device + microphone/TTS/on-device-recognizer runtime | API-tiered on-device STT, single AudioRecord arbiter, 750 ms pre-roll, AEC/noise suppression, signed voice turns and local `hie van` cache implemented; remaining device SLO/certification evidence required |
| Stable public HTTPS ingress | named Cloudflare Tunnel token + stable hostname | EXTERNAL — fail-closed installer/service ready; `trycloudflare.com` is rejected for production |
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

## Rev 3.1 research and voice certification rules

1. Exa credentials live only in the gateway secret plane; Android, Hermes prompts and evidence artifacts never receive the raw key.
2. Exa is not `READY` until a live canary returns usable sources and a token-free evidence receipt is persisted.
3. sherpa-onnx source/runtime and wake-model weights are separate supply-chain objects. Runtime checksum verification does not establish model redistribution rights.
4. A wake model may be used in production only after its licence/redistribution authority is recorded with the model bundle revision and SHA-256 digests.
5. Wake acceptance must never treat speaker similarity as authentication. A low owner-speaker score cannot veto independently strong phrase evidence.
6. The exact spoken wake acknowledgement is `hie van`. Certification must measure wake-to-ack latency and command recognition while acknowledgement audio overlaps owner speech.
7. Physical voice certification records the Android build fingerprint, recognition service identity/version, wake-model revision, sherpa runtime revision, acknowledgement-asset hash and VAN commit SHA.

## Physical device checklist

Install, overlay, notification listener, mic, TTS, biometric, drag/dock, rotation, process kill, Doze, reboot, offline queue, reconnect, secret notification, barge-in, share-to-VAN routing, Google capability status display, Rive failure → Canvas, reduced motion. Rev 3.1 additionally requires continuous capture ownership, telephony/mic-privacy yield, wake false-accept/reject runs, `hie van` overlap/AEC testing, on-device STT verification, word-evidence checks on API 34+, no-stale-replay voice commands, and device-revocation voice disarm.

## Android production gateway ingress

Repository and host-side closure require the VAN gateway itself to remain loopback-only on `dial-hermes-control`. Android release builds must receive `VAN_GATEWAY_BASE_URL` as a stable `https://` endpoint; release assembly fails closed when it is absent or insecure.

The externally reachable API is separately gated by `VAN_INGRESS_TOKEN` / `X-Van-Ingress-Token`. Android stores this bearer in encrypted preferences; it is never embedded in the APK. Device command execution remains independently protected by the enrolled per-device HMAC secret. Privileged Hermes control routes retain their separate internal-control credential and that credential is not accepted as a general external bearer.

A volatile `trycloudflare.com` quick tunnel is not production authority. Repo-side named-tunnel tooling is provided by `deploy/systemd/van-cloudflare-tunnel.service` and `tools/runtime/install_van_cloudflare_tunnel.sh`; the installer rejects quick-tunnel hostnames and requires an authenticated public `/health` canary before success. The remaining external routing gate is provisioning a named Cloudflare Tunnel token and stable hostname mapped to `http://127.0.0.1:8787`. This gate does not affect Workspace OAuth durability or live Google READY certification.
