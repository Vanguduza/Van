# Production Acceptance Ledger

**Version under test:** 0.5.0-dev  
**Date:** 2026-09-15
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
| Complete Python suite at closure HEAD | PASS — 72 passed |

## Google Intelligence Mesh repository gates

Validated 2026-09-15 in a clean repository environment after installing the declared backend dependencies: the complete Python suite passed **72/72** tests.

| Gate | Status |
|---|---|
| Migration v2: Google principal/capability/job/artifact tables | PASS |
| Canonical Google subject stored only as hash | PASS |
| Same-account ownership with credential-plane isolation | PASS |
| Workspace refresh-token → access-token exchange | PASS |
| Deterministic capability routing + fallback | PASS |
| A3 requires grant; project mutation requires truth SHA | PASS |
| A4 requires explicit owner approval | PASS |
| Provider artifact cannot become owner authority | PASS |
| Consumer capability configured != live-certified READY | PASS |
| Google session export / broker bypass policy denial | PASS |
| Hermes remains sole agent runtime | PASS |

## External gates blocking v1.0

See `docs/EXTERNAL_GATES.md`. **Google auth lives on Hermes** and is imported into Van mesh as `CONFIGURED` evidence (not `READY`). Remaining blockers: Antigravity live generation capacity, Cloud/Enterprise Google planes, physical Samsung certification, artist `.riv` / owner visual acceptance, production keystore, and GitHub `workflow` scope for `.github/workflows/ci.yml`. Local Project Truth mounts are closed on this workstation.

## Tag policy

Do **not** tag `v1.0` until all applicable gates are green. Current version remains `0.5.0-dev`.

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
| Google account authentication for Google worker plane | PASS | authenticated on Hermes; Van imports attestation (`artifacts/google/hermes_live_attestation.json`) |
| Hermes Google mesh usable (gemini/jules/workspace_api) | PASS | CONFIGURED via attestation import; not claimed READY without canary receipts |
| Antigravity live generation capacity | DEGRADED (`CAPACITY_LIMITED`) | Antigravity-only; Jules fallback selected when configured; other Google planes remain usable/CONFIGURED |

**Live Hermes gate verdict:** COMPLETE. Antigravity provider capacity is a separate Google-capability external gate and does not invalidate Hermes/VAN runtime acceptance.
