# External certification gates

These require owner credentials, live Google surfaces, provider/runtime access, physical hardware, or environments that repository CI cannot truthfully certify.

Resolved 2026-09-15: the live Hermes `van` profile is installed and certified on `dial-hermes-control`; Sonnet 5 executed a live VAN canary and the core Hermes/DIAL services and delegation suites passed. This is no longer an external gate.

Resolved 2026-09-16: permanent Workspace Desktop OAuth consent is complete, the refresh credential is encrypted in the VAN gateway vault, and live Gmail, Calendar, Drive, People/Contacts and Tasks metadata canaries all returned HTTP 200. `workspace_api` is `READY`. Cloud/Enterprise-only capabilities remain separate.

Resolved 2026-09-16: Stitch live generation is certified independently of Workspace OAuth. The authenticated Google Stitch MCP route returned a real generated screen with screen ID, HTML and image artifacts; VAN records this capability `READY` via a token-free receipt. Broader DIAL visual-acceptance and orchestrated-use proofs remain separate from VAN generation readiness.

Resolved 2026-09-16: the loopback VAN gateway is restart-persistent and the schema-4 owner pairing boundary is live-certified. Pairing tickets are hash-only and single-use; normal client APIs require the outer ingress bearer plus a revocable per-device token; commands additionally require the encrypted per-device HMAC. Both client credentials and HMAC verification survive restart, while device revocation atomically revokes grants and remains denied after a second restart. Token-free evidence is recorded at `artifacts/runtime/van_pairing_v4_live_attestation.json`.

Resolved 2026-09-15: the delegated `antigravity_worker_account` is authenticated in a separate isolated runtime home. Live model discovery and a Gemini 3.8 Flash generation canary passed; no canonical Google/API credential inheritance is permitted. Token-free evidence is recorded at `artifacts/google/antigravity_worker_live_attestation.json`. Antigravity is no longer an external authentication/generation gate.

Resolved 2026-09-15 (workstation): local Project Truth mounts for `van`, `dial`, `dde`, `gtr`, `goat`, and `aeci` resolve via `registries/project_mounts.json` + `tools/projects/sync_project_truth.py` offline cache. Gateway live PUT still requires a running gateway.

Resolved 2026-09-17: the canonical GitHub Actions workflow is live at `.github/workflows/van-ci.yml` and repeatedly certifies backend, Android unit/build/lint, shared geometry, visual rendering and artifact upload. Workflow installation/scope is no longer a production gate.

| Gate | Prerequisite | Repo-side readiness |
|---|---|---|
| Canonical owner Google principal | Hermes-authenticated owner Google account | hashed principal registration + Hermes attestation import |
| Google Workspace OAuth live | permanent Desktop OAuth + owner consent | READY — encrypted refresh credential installed; Gmail/Calendar/Drive/Contacts/Tasks live canaries all HTTP 200 |
| Gemini runtime | dedicated Google-account-owned API/runtime credential + inference credits | CAPACITY_LIMITED — restricted `van-gemini-runtime` key installed; Hermes reports `gemini: logged in`; authenticated model discovery returned HTTP 200 / 50 models; `gemini-3.6-flash` inference returned `RESOURCE_EXHAUSTED` because prepaid credits are depleted. Receipt: `artifacts/google/gemini_runtime_auth_attestation.json` |
| Gemini Live | authenticated Gemini runtime credential + live endpoint canary | CAPACITY_LIMITED — shared credential is authenticated and a bidi Live model is discoverable; live generation not promoted while project prepaid credits are depleted |
| Deep Research | authenticated Gemini runtime credential + quota canary | CAPACITY_LIMITED — Deep Research models are visible through authenticated discovery; execution awaits restored project prepaid credits |
| Gemini Notebook personal | owner Google session on Hermes | consumer capability CONFIGURED via attestation |
| Gemini Notebook Enterprise | eligible Cloud/Enterprise setup | still EXTERNAL (cloud plane) |
| Stitch | Google Cloud Stitch MCP credential plane | READY — authenticated live `generate_screen_from_text` canary passed; token-free receipt: `artifacts/google/stitch_live_attestation.json` |
| Mixboard / Flow / AI Studio / Workspace Studio | owner Google session on Hermes | consumer capabilities CONFIGURED via attestation; per-capability live canary still required |
| Jules | owner Google sign-in on Hermes | CONFIGURED via attestation; READY needs live worker receipt |
| Nano Banana / Veo | authenticated Gemini runtime credential + quota canary | CAPACITY_LIMITED — image and Veo models are visible through authenticated discovery; generation awaits restored project prepaid credits |
| Google ADK/A2A | owner-administered Cloud/runtime | still EXTERNAL (cloud plane) |
| Android owner gateway authentication | ingress bearer + revocable device token + enrolled device HMAC | LIVE-CERTIFIED on schema 4 — single-use pairing, hash-only device token persistence, restart continuity, atomic revoke, and post-restart denial all passed |
| Stable public HTTPS ingress | named Cloudflare Tunnel token + stable hostname | EXTERNAL — fail-closed installer/service ready; `trycloudflare.com` is rejected for production |
| Physical Samsung device | USB device + permissions | `tools/certification/device_cert_probe.py` + `docs/DEVICE_ACCEPTANCE_CHECKLIST.md` |
| Artist `.riv` | Rive editor | contract + Canvas fallback + handoff |
| Owner visual acceptance | owner review | acceptance matrix |
| Signed production release | production keystore | Gradle wiring + `android/keystore.properties.example` |

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

## Android production gateway ingress

Repository and host-side closure require the VAN gateway itself to remain loopback-only on `dial-hermes-control`. Android release builds must receive `VAN_GATEWAY_BASE_URL` as a stable `https://` endpoint; release assembly fails closed when it is absent or insecure.

The externally reachable API uses layered client authority. `VAN_INGRESS_TOKEN` / `X-Van-Ingress-Token` is the outer transport bearer. Except for ingress-only `/health`, normal Android API calls also require a revocable per-device access token. Device command execution additionally requires the enrolled per-device HMAC secret. New devices can obtain these credentials only through a short-lived single-use pairing ticket issued by the internal control plane. Privileged Hermes control routes retain their separate internal-control credential and that credential is not accepted as a general external bearer.

A volatile `trycloudflare.com` quick tunnel is not production authority. Repo-side named-tunnel tooling is provided by `deploy/systemd/van-cloudflare-tunnel.service` and `tools/runtime/install_van_cloudflare_tunnel.sh`; the installer rejects quick-tunnel hostnames and requires an authenticated public `/health` canary before success. The remaining external routing gate is provisioning a named Cloudflare Tunnel token and stable hostname mapped to `http://127.0.0.1:8787`. This gate does not affect Workspace OAuth durability or live Google READY certification.
