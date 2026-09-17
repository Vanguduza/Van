# Production Acceptance Ledger

**Version under test:** 0.5.0-dev  
**Date:** 2026-09-17
**Verdict:** NOT v1.0 PRODUCTION ACCEPTED — external gates remain

## Previously certified repository gates

| Gate | Status |
|---|---|
| No fake success paths for Hermes/Google offline | PASS (fail closed) |
| Existing backend suite | PASS at prior HEAD |
| Existing cross-cutting contracts/scenarios/hermes | PASS at prior HEAD |
| Android assembleDebug | PASS at fail-closed hardening HEAD |
| Android lintDebug | PASS at fail-closed hardening HEAD |
| Android unit tests | PASS at fail-closed hardening HEAD |
| Visual authority contract tests | PASS at prior HEAD |
| Owner escalation / decisions API | PASS |
| Reminder time-expression parse | PASS |
| Project Truth put/sync tooling | PASS (van/dial/dde/gtr/goat/aeci offline mounts; fail closed if truth missing) |
| Existing Google fake-transport + A4 send gate | PASS |
| Existing migration idempotence | PASS |
| SBOM / provenance / checksums | PASS at prior HEAD |
| Project Truth canonical state contract | PASS — canonical state added and guarded for PR-based integration |
| Backend bootstrap | PASS — repository root resolution and `python3` invocation corrected; bootstrap executed successfully |
| Complete Python suite at current Google/profile closure HEAD | PASS — 99 passed |

## Google Intelligence Mesh repository gates

Validated 2026-09-15 in a clean repository environment after installing the declared backend dependencies: the complete Python suite passed **79/79** tests.

| Gate | Status |
|---|---|
| Migration v2: Google principal/capability/job/artifact tables | PASS |
| Canonical Google subject stored only as hash | PASS |
| Canonical Google identity plus bounded delegated-identity isolation | PASS |
| Antigravity isolated runtime/account binding | PASS — wrapper + registry + route contract tests + live isolated OAuth/model discovery/generation canary |
| Workspace refresh-token → access-token exchange | PASS |
| Deterministic capability routing + fallback | PASS |
| A3 requires grant; project mutation requires truth SHA | PASS |
| A4 requires explicit owner approval | PASS |
| Provider artifact cannot become owner authority | PASS |
| Consumer capability configured != live-certified READY | PASS |
| Google session export / broker bypass policy denial | PASS |
| Hermes remains sole agent runtime | PASS |
| Stitch live generation | PASS — authenticated `generate_screen_from_text` returned screen ID + HTML + image; token-free receipt recorded and VAN broker state is `READY` |
| Gemini runtime credential canary | CAPACITY_LIMITED — dedicated restricted key installed; Hermes reports `gemini: logged in`; authenticated model discovery returned HTTP 200 / 50 models; real `gemini-3.6-flash` inference reached Google but returned `RESOURCE_EXHAUSTED` because prepaid credits are depleted. Receipt: `artifacts/google/gemini_runtime_auth_attestation.json` |

## Live VAN gateway pairing certification — 2026-09-16

Live host: `dial-hermes-control`; certified source: `b075817401fc02ae7ffbaea311f8d9b560c9dea0`. Token-free receipt: `artifacts/runtime/van_pairing_v4_live_attestation.json`.

| Gate | Status | Evidence |
|---|---|---|
| Loopback-only gateway service | PASS | `van-gateway.service` active + enabled on `127.0.0.1:8787`; schema 4 applied |
| Outer ingress boundary | PASS | unauthenticated `/health` returned HTTP 401; ingress-authenticated `/health` remained healthy |
| Single-use pairing ticket | PASS | ticket stored only as SHA-256; first pair HTTP 200; reuse HTTP 400 |
| Device HMAC secret at-rest protection | PASS | live canary secret stored encrypted; plaintext absent from persisted field |
| Per-device access-token protection | PASS | token stored only as SHA-256; ingress bearer alone received HTTP 401 on normal client API |
| Dual-token client authority | PASS | ingress bearer + device token received HTTP 200 before and after gateway restart |
| Restart-durable command authentication | PASS | signed stale command returned `expired` before and after restart, proving HMAC rehydration without executing Hermes |
| Workspace continuity through restart | PASS | `workspace_api` remained `READY` before, after first restart, and after second restart |
| Atomic device/grant revocation | PASS | revoke HTTP 200 and active grants became 0 |
| Revocation survives restart | PASS | old device token received HTTP 401 for API and command after second restart |
| Stable public HTTPS route | EXTERNAL | named Cloudflare Tunnel token + stable hostname still required; quick tunnels are rejected |

## External gates blocking v1.0

See `docs/EXTERNAL_GATES.md`. Canonical Google auth lives on Hermes and is imported into the VAN mesh as `CONFIGURED` evidence unless a capability has its own live canary. The delegated Antigravity worker is live-certified. Remaining blockers include Cloud/Enterprise Google planes, uncertified per-capability Google surfaces, physical Samsung certification, artist `.riv` / owner visual acceptance, production keystore, and stable named Cloudflare ingress. Local Project Truth mounts are closed on this workstation.

## Tag policy

Do **not** tag `v1.0` until all applicable gates are green. Current version remains `0.5.0-dev`.

## Live VAN profile preservation and inference certification — 2026-09-17

Token-free receipt: `artifacts/runtime/van_profile_live_attestation.json`. Certified installer source: `270da5d3a8756a19458307968a9c30e2fe138f1a`.

| Gate | Status |
|---|---|
| Runtime-owned profile state preservation | PASS — `.env`, `state.db`, sessions, memories, logs, pairing, caches, platform/cron/hooks/sandboxes retained identity/hash/count evidence |
| Runtime-installed extra skill preservation | PASS — `skills/software-development/github/scripts/git-credential-token.py` survived unchanged |
| Installed profile doctor | PASS — all 13 VAN-managed skills verified; root `.env` mode `0600`; no credential filenames in managed static content |
| Live VAN primary inference | PASS — exact `VAN_PROFILE_CANARY_OK`; provider `anthropic`; model `claude-sonnet-5`; one API call |

## Live Hermes certification — 2026-09-15

Live host: `dial-hermes-control`; control path: authorised `oracle-admin` Commander → private SSH. Canonical VAN source under certification: `66f6c6ef0d8cc2289dc7a851746194148405b10d`.

| Gate | Status | Evidence |
|---|---|---|
| VAN profile installed and recognised by Hermes | PASS | `doctor_van_profile.sh` all checks passed; `van` profile present with canonical SOUL/AGENTS/policy/skills |
| VAN primary model policy | PASS | live profile resolves `anthropic` / `claude-sonnet-5` |
| VAN primary model live turn | PASS | Hermes `van` profile canary returned `VAN_SONNET5_OK` |
| Claude owner account authentication | PASS | Claude CLI reports logged in with Max subscription through `claude.ai` |
| Bot Chat / roster / relay | PASS | live Hermes-source tests: 41 passed |
| `message_agent` | PASS | live Hermes-source tests: 42 passed, 1 skipped |
| Native rooms/councils + grants/execution fencing | PASS | live Hermes-source tests: 67 passed |
| Fallback chain | PASS | live Hermes-source tests: 24 passed |
| Delegation core | PASS | live Hermes-source tests: 81 passed |
| Delegate capability inheritance / toolset scope | PASS | live Hermes-source tests: 10 passed |
| Core Hermes/DIAL services | PASS | runtime, orchestrator, gateway, chat-control, owner-steering and private-MCP-bind all active |
| Canonical Google identity authentication | PASS | authenticated on Hermes; VAN imports hashed attestation evidence without copying tokens |
| Hermes Google mesh usable (gemini/jules/workspace_api) | PASS | `workspace_api` READY via live Gmail/Calendar/Drive/Contacts/Tasks HTTP 200 canary receipt; other Google capabilities retain their independently evidenced states |
| Delegated Antigravity worker identity | PASS | isolated OAuth store, no inherited canonical Google/API credentials, 14 models discovered; token-free receipt: `artifacts/google/antigravity_worker_live_attestation.json` |
| Delegated Antigravity live generation | PASS | isolated pre-deploy canary returned `VAN_ANTIGRAVITY_SECONDARY_OK`; installed profile doctor passed, wrapper hash matched, 14 models were discovered, and installed-profile canary returned `VAN_INSTALLED_ANTIGRAVITY_OK` |
| Antigravity capacity fallback contract | PASS | if the delegated route later becomes `CAPACITY_LIMITED`/`RATE_LIMITED`, deterministic routing may fall back to owner-account Jules while preserving identity attribution |

**Live Hermes gate verdict:** COMPLETE. The delegated Antigravity worker is live-certified. Remaining Google capability readiness is evaluated independently per capability and credential plane.
