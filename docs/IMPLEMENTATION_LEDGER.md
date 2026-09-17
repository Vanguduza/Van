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
- **Stitch live generation certification:** authenticated Google Stitch MCP generation is live-qualified and recorded `READY` in VAN with token-free hashes for the generated screen, HTML and image artifacts; DIAL visual acceptance/orchestrated-use remain independent acceptance gates.
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

## AUTOMATION & BROWSER FABRIC (Rev 1.3) — REPOSITORY-SIDE BUILT, OWNER-GATED

- **Implementation base:** reconciled from `main` plus the certified Rev 3.1 owner-runtime lineage (`87f5a22`) and the in-flight trading-core bootstrap branch. Evidence and ancestry: `docs/project-state/AUTOMATION_BROWSER_FABRIC_PREFLIGHT.md`.
- **Schema:** migration 6 adds automation capability/artifact/run/event/intent state, `standing_automation_authorities`, `automation_run_nonces` and browser task/evidence/profile tables.
- **Standing automation authority:** a scheduled or event run derives an ordinary `CommandAuthorityRecord` through the existing `CommandAuthorityService` — no second authorization plane. The originating owner device stays the revocation root, every run seals a fresh `ContextSnapshot`, and trigger, workflow version and parameter surface are digest-bound. A4 can never become standing authority.
- **Run capability grants:** MAC-bound, run-scoped, durable. Single-use mutation nonces consume via one conditional `UPDATE`, so concurrent redemption yields exactly one winner and a restart cannot resurrect a consumed nonce. n8n never holds a general-purpose VAN token.
- **Workflow pipeline:** platform-neutral `WorkflowIR`, a static analyser that rejects unsafe graphs before compilation, a deterministic compiler whose semantic digest excludes canvas position, and VAN-owned artifact lineage that never overwrites an admitted row.
- **Verification:** `engine_success_is_owner_success: false` is enforced — an n8n 200 with an absent postcondition fails the run; an uncorrelated observation is `PARTIAL_SUCCESS`; no declared verifier yields `UNVERIFIABLE`.
- **Browser Fabric:** Browser Harness (`browser-use/browser-harness`, MIT) as the deterministic actuator and Stagehand (MIT) as the semantic layer, both behind the Browser Gateway. Production autonomy is capped at **L3** (observe → deterministic action); L4/L5 require an owner amendment to the Hermes execution boundary. Session material is `secretref://` only; evidence is digest-only and is refused if secret-shaped.
- **Health:** `/v1/automation/health` and `/v1/browser/health` (internal control only) report runtime readiness, governance state, lifecycle counts and the T0 isolation invariant, and drive nine new `DegradedCode` members.
- **Hermes skills:** `automation-fabric` and `browser-intelligence` registered in the `van` profile pack.
- **Certification:** `tools/certification/certify_automation_runtime.py` and `tools/certification/certify_browser_fabric.py` are the only paths to READY. Both refuse while the feature flags are off and fail without recording evidence when no runtime answers. CI proves this fail-closed behaviour on every run.
- **Every external switch defaults off:** automation, ingress, egress and browser attachment all ship disabled.

## AUTOMATION & BROWSER FABRIC — PENDING OWNER DECISION

Rev 1.3 §365 makes these owner decisions, not implementation decisions. An implementation agent creates the artifacts and must not mark them signed.

- `docs/decisions/VAN-ADOPT-N8N-001.yaml` — n8n is source-available under the Sustainable Use License (`SOURCE_AVAILABLE`), which stack-lock principle 5 requires an owner-signed adoption decision for. **PENDING.**
- `docs/decisions/VAN-ADOPT-STAGEHAND-001.yaml` and `docs/decisions/VAN-ADOPT-BROWSER-HARNESS-001.yaml` — both MIT; adoption and the L3 ladder cap still need owner sign-off. **PENDING.**
- `docs/decisions/VAN-AMEND-SECURITY-POLICY-001.md` — seven proposed authority texts covering the automation boundary, credential isolation, browser session sovereignty, egress, ingress, generated workflows and browser workers. `docs/SECURITY_POLICY.md` is a locked authority and is **unmodified**; a contract test pins its digest. **PENDING.**
- `trading/architecture/proposed/automation_browser_fabric_layers.json` — three stack-lock layers (`integration_automation` T2, `semantic_browser` T3, `deterministic_browser` T2) held outside the lock until the adoption decision is recorded. They already satisfy every assertion `test_stack_lock.py` applies to admitted layers, so promotion is mechanical.

## EXTERNALLY BLOCKED / REQUIRES LIVE CERTIFICATION

- VATI Rev 5 repository implementation is integrated: trading core, risk authority, execution adapters, commander/VEKL, Android Trading Command Center, signed account onboarding and fail-closed tests are present. Remaining gates are deployment/live-market/device gates: `van-trading-core` bootstrap/qualification, real broker/demo account connection, real market data validation, MT5 EA/terminal attachment where used, independent security review and owner-signed LIMITED_LIVE promotion.
- Google readiness is credential-plane-specific. Workspace OAuth and Stitch are `READY`; the Gemini runtime plane is authenticated with a dedicated API-restricted key and is currently `CAPACITY_LIMITED` because project prepaid inference credits are depleted. Consumer/Cloud capabilities retain their independently evidenced states.
- The delegated Antigravity worker is live-certified. Capacity/rate limits, if they recur, remain capability-scoped and may fall back to Jules without degrading other Google planes.
- Notebook Enterprise / ADK-A2A require eligible owner-administered Google Cloud/Enterprise setup.
- Live Hermes install is certified on `dial-hermes-control` (2026-09-15). Local Project Truth mounts for van/dial/dde/gtr/goat/aeci are resolved on this workstation. Physical Samsung certification, stable named Cloudflare hostname/token provisioning, `.riv` authoring, and production signing remain external gates.

## SUPERSEDED / FORBIDDEN

- Embedded/on-device second VAN agent loop.
- Consumer Gemini web scraping as a model credential.
- A single Google master credential shared across capability families.
- Copying/exporting Google browser cookies or sessions.
- Treating `CONFIGURED` as proof of live success.
- Direct Google project mutation that bypasses Hermes, Project Truth, grants, action classes, audit or evidence.

- Automation & Browser Fabric live gates are all `PENDING_LIVE`: the self-hosted n8n runtime, workflow generation, security audit, backup/restore, webhook ingress, standing automation, Stagehand, Browser Harness, authenticated browser profiles, prompt-injection containment, Trading Core isolation under load, and browser→automation route promotion. Repository-side code exists and fails closed; none of it is READY, and §369 forbids promoting a gate because code exists.

See `docs/EXTERNAL_GATES.md` for exact live gates.
