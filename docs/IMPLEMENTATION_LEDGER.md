# VAN Implementation Ledger

**Updated:** 2026-09-16
**Version:** 0.5.0-dev  
**Repository:** `Vanguduza/Van`

## IMPLEMENTED (repository-side)

- Canonical authority: Project Truth, Security Policy, visual identity/Rive contract, external gates.
- VAN secure gateway: owner enrollment, signed commands, idempotency, stale-intent expiry, A4/A5 gates, prompt-injection rejection, attention, briefing, reminders, notification intelligence, audit, events and Project Truth cache.
- Hermes pack: profile `van` SOUL, skills, fail-closed policy hook, Bot Chat/councils contracts and install/doctor tooling.
- Android embodiment: overlay, Command Centre, encrypted queue, notification listener, share intent, voice/TTS hooks, biometric gate, onboarding and degraded-mode model.
- Google Workspace token vault: encrypted refresh tokens, narrow scopes, revocation and prompt scrubbing.
- **Restart-durable device authentication:** per-device HMAC credentials are encrypted at rest with a dedicated Fernet key, rehydrated at gateway startup, and fail closed on key mismatch.
- **Atomic device revocation:** revoking an owner device marks the device and all outstanding capability grants revoked in one transaction; revoked credentials are never rehydrated.
- **Three-layer owner gateway boundary:** stable ingress requires `X-Van-Ingress-Token`; normal client APIs additionally require a revocable per-device access token stored only as a hash server-side; command authority additionally requires the independent encrypted per-device HMAC. Pairing is short-lived, single-use, internal-control-issued, and atomic with device/grant creation.
- **Live schema-4 pairing certification:** token-free canary evidence confirms pairing-ticket single use, hash-only device-token persistence, dual-token restart continuity, HMAC restart continuity, atomic revocation, and post-restart denial while Workspace remains `READY`; see `artifacts/runtime/van_pairing_v4_live_attestation.json`.
- **Named tunnel production tooling:** `van-cloudflare-tunnel.service` + installer require a token file and stable HTTPS hostname, reject `trycloudflare.com`, and require an authenticated public health canary.
- **Google OAuth correctness:** live Workspace transport exchanges encrypted refresh tokens for short-lived access tokens before Google API requests.
- **Google Account Sovereignty:** `owner_google_account` remains VAN's canonical/default Google identity with separate Workspace OAuth, Gemini runtime, Cloud/service and consumer-session credential planes. Explicit delegated identities are bounded to named capabilities and cannot inherit owner authority or credentials.
- **Google Intelligence Mesh:** versioned capability registry covering Gemini, Gemini Live, Deep Research, Gemini Notebook (personal + Enterprise), Mixboard, Stitch, Antigravity, Jules, Workspace API/Studio, Nano Banana, Veo, Flow, AI Studio and ADK/A2A.
- **Deterministic Google router:** action-class, approval, grant and Project Truth gates; registry-order deterministic selection; explicit fallback; persisted input hash and job state.
- **Google readiness model:** READY / CONFIGURED / UNVERIFIED / AUTH_REQUIRED / DEGRADED / RATE_LIMITED / CAPACITY_LIMITED / POLICY_BLOCKED / UNSUPPORTED / UNAVAILABLE.
- **Antigravity capacity scoping:** live generation `CAPACITY_LIMITED` records `ANTIGRAVITY_CAPACITY_LIMITED` and falls back to Jules when configured; does not fail Workspace/Gemini/Jules planes.
- **Project Truth mounts:** `registries/project_mounts.json` + sync tool prefer per-project `truth_path`; offline cache under `artifacts/project-truth/`.
- **Google provenance:** persistent jobs and artifact lineage with project, provider, tool version, input/output hashes, validation state and evidence pointer; provider artifacts can never be marked `OWNER_SIGNED`.
- **Google operator tooling:** hashed owner-principal configuration and certification/status scripts; `tools/google/mark_antigravity_capacity_limited.py`; `tools/google/import_hermes_google_attestation.py` for Hermes-hosted auth evidence.
- **Hermes Google skills:** google-intelligence, gemini-notebook, google-design, google-development; Google providers remain subordinate to Hermes.
- **Antigravity delegated identity:** Antigravity alone is bound to `antigravity_worker_account` and executes through an isolated HOME/XDG/OAuth store with inherited Google/API credentials stripped. Live OAuth, 14-model discovery and a Gemini 3.8 Flash canary are certified on `dial-hermes-control` (2026-09-15); token-free evidence is stored in `artifacts/google/antigravity_worker_live_attestation.json`.
- **Policy hardening:** Google broker/registry protected; session-cookie export, credential-plane collapse and broker bypass are prohibited patterns.
- Comprehensive canonical specification: `docs/GOOGLE_INTELLIGENCE_MESH.md`.
- Device/CI helpers: `tools/certification/device_cert_probe.py`; `tools/ci/install_github_workflow.py`; Windows `tools/bootstrap_backend.ps1`, `tools/run_gateway.ps1`, `tools/sync_project_truth_live.ps1`.
- Fail-closed hardening: unsigned release refused; `/health` `ok` tracks Hermes; Project Truth PUT requires internal token; Google mesh defaults unverified until evidence; Rive load failures fall back to Canvas.

## EXTERNALLY BLOCKED / REQUIRES LIVE CERTIFICATION

- Google credential planes are authenticated on Hermes and imported into Van as `CONFIGURED` (not `READY` without canary receipts).
- The delegated Antigravity worker is live-certified. Capacity/rate limits, if they recur, remain capability-scoped and may fall back to Jules without degrading other Google planes.
- Notebook Enterprise / ADK-A2A require eligible owner-administered Google Cloud/Enterprise setup.
- Live Hermes install is certified on `dial-hermes-control` (2026-09-15). Local Project Truth mounts for van/dial/dde/gtr/goat/aeci are resolved on this workstation. Physical Samsung certification, stable named Cloudflare hostname/token provisioning, `.riv` authoring, production signing, and GitHub workflow-scope install remain external gates.

## SUPERSEDED / FORBIDDEN

- Embedded/on-device second VAN agent loop.
- Consumer Gemini web scraping as a model credential.
- A single Google master credential shared across capability families.
- Copying/exporting Google browser cookies or sessions.
- Treating `CONFIGURED` as proof of live success.
- Direct Google project mutation that bypasses Hermes, Project Truth, grants, action classes, audit or evidence.

See `docs/EXTERNAL_GATES.md` for exact live gates.
