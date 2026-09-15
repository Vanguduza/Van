# Production Acceptance Ledger

**Version under test:** 0.5.0-dev  
**Date:** 2026-09-14  
**Verdict:** NOT v1.0 PRODUCTION ACCEPTED — external gates remain

## Previously certified repository gates

| Gate | Status |
|---|---|
| No fake success paths for Hermes/Google offline | PASS (fail closed) |
| Existing backend suite | PASS at prior HEAD |
| Existing cross-cutting contracts/scenarios/hermes | PASS at prior HEAD |
| Android assembleDebug | PASS at prior HEAD |
| Android lintDebug | PASS at prior HEAD |
| Android unit tests | PASS at prior HEAD |
| Visual authority contract tests | PASS at prior HEAD |
| Owner escalation / decisions API | PASS |
| Reminder time-expression parse | PASS |
| Project Truth put/sync tooling | PASS (van local dry-run; others fail closed without truth) |
| Existing Google fake-transport + A4 send gate | PASS |
| Existing migration idempotence | PASS |
| SBOM / provenance / checksums | PASS at prior HEAD |

## Google Intelligence Mesh repository gates

These gates are implemented in this change but must not be called `PASS` until the updated test suite executes against the declared repository dependencies in a suitable checkout/CI environment.

| Gate | Status |
|---|---|
| Migration v2: Google principal/capability/job/artifact tables | IMPLEMENTED — TEST ADDED |
| Canonical Google subject stored only as hash | IMPLEMENTED — TEST ADDED |
| Same-account ownership with credential-plane isolation | IMPLEMENTED — TEST ADDED |
| Workspace refresh-token → access-token exchange | IMPLEMENTED — TEST ADDED |
| Deterministic capability routing + fallback | IMPLEMENTED — TEST ADDED |
| A3 requires grant; project mutation requires truth SHA | IMPLEMENTED — TEST ADDED |
| A4 requires explicit owner approval | IMPLEMENTED — TEST ADDED |
| Provider artifact cannot become owner authority | IMPLEMENTED — TEST ADDED |
| Consumer capability configured != live-certified READY | IMPLEMENTED — TEST ADDED |
| Google session export / broker bypass policy denial | IMPLEMENTED — TEST ADDED |
| Hermes remains sole agent runtime | IMPLEMENTED — CONTRACT TEST UPDATED |

## External gates blocking v1.0

See `docs/EXTERNAL_GATES.md`. Google account registration, Workspace OAuth, Gemini runtime, Notebook/Mixboard/Stitch/Antigravity/Jules/Workspace Studio/media live certifications and existing device/signing gates remain blocked until the corresponding owner credentials/environments are available. Live Hermes is certified below.

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
| Google account authentication for Google worker plane | PASS | cached Google OAuth present; Antigravity model discovery succeeds |
| Google live generation capacity | DEGRADED | authenticated/model-discovery verified; latest live qualification classified `CAPACITY_LIMITED`; do not mark Google execution `READY` until provider quota permits a passing canary |

**Live Hermes gate verdict:** COMPLETE. Google provider capacity is a separate Google-capability external gate and does not invalidate Hermes/VAN runtime acceptance.
