# VAN Implementation Ledger

**Updated:** 2026-09-14  
**Version:** 0.5.0-dev  
**Repository:** `Vanguduza/Van`

## IMPLEMENTED (repository-side)

- Canonical authority: Project Truth, Security Policy, visual identity/Rive contract, external gates.
- VAN secure gateway: owner enrollment, signed commands, idempotency, stale-intent expiry, A4/A5 gates, prompt-injection rejection, attention, briefing, reminders, notification intelligence, audit, events and Project Truth cache.
- Hermes pack: profile `van` SOUL, skills, fail-closed policy hook, Bot Chat/councils contracts and install/doctor tooling.
- Android embodiment: overlay, Command Centre, encrypted queue, notification listener, share intent, voice/TTS hooks, biometric gate, onboarding and degraded-mode model.
- Google Workspace token vault: encrypted refresh tokens, narrow scopes, revocation and prompt scrubbing.
- **Google OAuth correctness:** live Workspace transport exchanges encrypted refresh tokens for short-lived access tokens before Google API requests.
- **Google Account Sovereignty:** one logical owner Google principal with separate Workspace OAuth, Gemini runtime, Cloud/service and consumer-session credential planes.
- **Google Intelligence Mesh:** versioned capability registry covering Gemini, Gemini Live, Deep Research, Gemini Notebook (personal + Enterprise), Mixboard, Stitch, Antigravity, Jules, Workspace API/Studio, Nano Banana, Veo, Flow, AI Studio and ADK/A2A.
- **Deterministic Google router:** action-class, approval, grant and Project Truth gates; registry-order deterministic selection; explicit fallback; persisted input hash and job state.
- **Google readiness model:** READY / CONFIGURED / UNVERIFIED / AUTH_REQUIRED / DEGRADED / RATE_LIMITED / POLICY_BLOCKED / UNSUPPORTED / UNAVAILABLE.
- **Google provenance:** persistent jobs and artifact lineage with project, provider, tool version, input/output hashes, validation state and evidence pointer; provider artifacts can never be marked `OWNER_SIGNED`.
- **Google operator tooling:** hashed owner-principal configuration and certification/status scripts.
- **Hermes Google skills:** google-intelligence, gemini-notebook, google-design, google-development; Google providers remain subordinate to Hermes.
- **Policy hardening:** Google broker/registry protected; session-cookie export, credential-plane collapse and broker bypass are prohibited patterns.
- Comprehensive canonical specification: `docs/GOOGLE_INTELLIGENCE_MESH.md`.
- Test coverage added for migration v2, principal hashing, deterministic routing, mutation/approval gates, provenance authority, OAuth refresh exchange and credential-plane separation.

## EXTERNALLY BLOCKED / REQUIRES LIVE CERTIFICATION

- Owner Google principal has not been registered in a deployed VAN gateway.
- Workspace OAuth consent/client credentials are not supplied in repository.
- Gemini runtime/API credentials are not supplied in repository.
- Consumer Google surfaces require normal owner Google sign-in and live certification evidence.
- Notebook Enterprise / Cloud-service capabilities require eligible owner-administered Google Cloud/Enterprise setup.
- Live Hermes install, physical Samsung certification, `.riv` authoring, cross-project truth mounts and production signing remain external gates.

## SUPERSEDED / FORBIDDEN

- Embedded/on-device second VAN agent loop.
- Consumer Gemini web scraping as a model credential.
- A single Google master credential shared across capability families.
- Copying/exporting Google browser cookies or sessions.
- Treating `CONFIGURED` as proof of live success.
- Direct Google project mutation that bypasses Hermes, Project Truth, grants, action classes, audit or evidence.

See `docs/EXTERNAL_GATES.md` for exact live gates.
