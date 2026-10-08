# VAN implementation and acceptance — prior source snapshot

This report and its aggregate belong to the earlier implementation snapshot. The
[current wiring closure](VAN_WIRING_CLOSURE_2026-10-07.md),
[production source freeze](validation/van-production-source-freeze-2026-10-07.json)
and [current Android receipt](validation/android-owner-controls-final-receipt-2026-10-07.json)
supersede its build, APK and source-gap claims. The current registries describe
42 capabilities, 70 screens/hosted surfaces, 307 endpoint declarations and 165 schemas.
Original feature/screen registry bytes are retained in
[the historical registry archive](validation/registry-before-final-wiring/).

This is the implementation follow-up to the [owner audit](VAN_OWNER_E2E_REVIEW_2026-10-07.md). Baseline `12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af`; changes are local and uncommitted. The [current frontend contract](OWNER_FRONTEND_CONTRACT.html) records functions found by that audit and their implemented controls. Baseline findings remain frozen separately. Local implementation and verification do not establish deployed or S24 Ultra acceptance.

## Automatic owner connectivity

Android has no editable gateway, Hermes, service URL, pairing credential, device identifier, pin or transport-priority form. The deployment installer delivers a short-lived signed envelope to the installed app. Trust belongs to the build and deployment authority: the owner's stable release signing identity, public connectivity verification keys and trusted gateway CA must agree with the gateway's configuration. No standing shared owner credential is put in the APK.

The app stages that envelope in encrypted storage, then resumes provisioning automatically on startup and network availability. Enrollment validates the signed Android certificate chain against configured roots, the leaf public key, challenge, package/signing identity, hardware security levels and locked verified boot. Missing or invalid trust fails closed. Bootstrap credentials issued for this installer expire on the server within ten minutes, including an expiry recheck when consumed. A spent bootstrap can recover its exact active enrollment using a fresh hardware signature. An existing legacy key can certify its original attestation chain without replacing the owner binding.

Pairing persists the exact request and a client-generated high-entropy access token before transmission. The gateway retains hashes and permits recovery only with the same unexpired ticket, matching request/token and the exact active proved binding. Session opening likewise persists an opening identity; concurrent retries recover the same logical session and reject altered parameters or a closed identity. Reconnect retains cursors and the outbox, including sessions with no retained work.

Signed manifests now select the production HTTPS/WSS routes and approved browser signaling/ICE configuration. Pins narrow existing trusted CA validation; a pin never makes an arbitrary certificate trusted. Redirects do not carry credentials elsewhere. A new private CA anchor still requires a trusted build/rotation path. After bounded WebSocket admission failures, the existing POST/SSE transport supplies the same session/command identities. Unknown unkeyed mutation outcomes stay unknown; automatic retries use an endpoint's explicit idempotency contract.

The [installer](../../tools/provisioning/provision_owner_device.py) checks the handset and installs the APK **before** minting the envelope. It reads its machine-scoped credential from an environment variable, never writes the envelope to disk, refuses redirects and waits for `/v1/devices/provisioning-status`. That status requires the exact attested binding, active paired authority, valid issued certificate and an actual accepted WebSocket audit receipt for that certificate/session. It reports historical admission separately from current connection, Hermes execution and owner-command success. An activity launch or payload-staging log cannot pass acceptance.

## Owner functions and authority

The [feature registry](../../registries/owner_features.json), [screen registry](../../registries/owner_screens.json), [endpoint registry](../../registries/owner_endpoints.json) and [schema components](../../registries/owner_endpoint_schemas.json) are the current frontend design inputs. Each implementation retains baseline provenance, source/function citations, endpoint access, information requirements, owner interactions, error/recovery states and live/device verification limits. Source gaps, deferred visual redesign and external qualification remain separate; registry membership does not claim every function is complete. Service-only endpoints are explicitly separated from Android access.

Implemented owner controls include mission messages/record cancellation, reminders, memory inventory/history/provenance/conflicts, understanding confirmation/correction/rejection, adaptation review/reversal, goals and decision/strategy evidence, standing permission withdrawal, autonomy/readiness, knowledge, research, automation, diagnostics and browser outcomes. Voice supports finish and cancellation, with late results blocked after cancellation. New pages use bounded owner read projections and existing signed command authority for consequential actions.

Project rationale now has an actual editor reached from the selected project, typed rationale entries, signed submission and exact receipt/readback before confirmation. Saved navigation restores the selected record's concrete identifier and rejects unresolved route templates. Browser control, pause, close and viewport acknowledgement preserve the last confirmed state on failure, show ambiguous outcomes and hold input until authority is confirmed. A lost reply never causes an automatic replay of those mutations.

Every device-authenticated mutation requires hardware proof once the owner is bound. It covers method, the exact path **and query**, device, timestamp and body digest; a durable nonce refuses reuse. Strict deployments also require certified hardware attestation. Polling reads do not perform hardware signatures. Fact withdrawal and permission revocation bind the exact target.

Memory erasure is a canonical A4 `memory.erase` command with fresh biometric approval for the sealed store scope. Direct `DELETE /v1/context/memory` refuses with 409, including in its OpenAPI declaration and endpoint registry. The eraser rechecks live authority and expiry while holding the database write lock, commits actual counts and identity commitments, invalidates hot context caches and verifies the resulting state independently. The owner receives per-store removed counts and deliberate retention only from a verified effect receipt. The `intent_nodes` scope includes its exact dependent edge/mission rows and retains unrelated records. Stopping standing automation revokes the exact device-owned authority and independently verifies that new gateway work is disabled.

Gateway callbacks now use a durable inbox and immutable run bindings, so an early callback can be reconciled after the accepted run receipt is stored. Observed acceptance binds its original command/request identity; arbitrary evidence strings cannot clear an irreversible-action gate. Actual terminal effects still require the existing independent success contract. No invented Hermes lookup/cancel route was added.

## Verification and remaining live gates

Exact final commands, counts, source hashes, APK identity and logs are recorded in [the implementation validation receipt](VAN_IMPLEMENTATION_VALIDATION_2026-10-07.json). Focused regressions overlap and are excluded from its aggregate. The [prior validation receipt](VAN_OWNER_E2E_VALIDATION_2026-10-07.json) belongs to the earlier source snapshot and is historical evidence.

| Historical local check | Prior snapshot result |
|---|---|
| Backend | 2,157 passed; 352 source/test hashes unchanged |
| Gateway/frontend contracts | 616 passed, 4 skipped |
| Services, Hermes profile/policy and scenarios | 204 passed, 1 skipped |
| Trading | 1,276 passed, 5 skipped |
| Android JVM logic/session tests | 1,068 passed across 122 suites |
| Android app unit tests | 203 passed across 36 suites |
| Full arm64 debug app compilation, APK assembly and lint | Passed; build inputs unchanged |
| Searchable frontend contract in Chromium | Passed; tabs, filters, search and authority details |

That historical aggregate was **5,524 passed, 10 skipped**. Its prior debug APK was 123,474,978 bytes, SHA-256 `87ff0cbd549fb70cae10c002dbef143704e8cda9d1ffef760b0f5e9b567ccf5f`; it is superseded by the linked current Android receipt. Neither artifact has production owner signing or handset qualification. Earlier x86 app/instrumentation compilation is retained separately and does not certify the final UI on an emulator. The prior backend run reported two intermittent SQLite worker closed-loop warnings during test teardown, alongside dependency/async-mark/OpenAPI warnings; those remain historical observations and do not establish a live shutdown result.

The acceptance handset is the owner's **S24 Ultra**. Repository-declared hosts are `dial-control`/`dial-hermes-control` (Netcup, Hermes/gateway), `van-trading-core` (Oracle, trading/runtime services), `oracle-admin` (Oracle, product gateway/recovery), and `vekl-worker` (Oracle, background work). Those declarations do not establish current connectivity. This session exposes only the cloud workspace, no governed DIAL host or handset connector, and no configured live machine credentials. The committed direct gateway is `https://62.83.35.103:8443`; the cloud proxy presents an interception certificate rather than the pinned device CA. This observation does not demonstrate gateway CA drift.

Live acceptance remains **BLOCKED**, rather than passed: no current deployed-source identity, stable-owner-signed release APK enrollment, physical attestation/biometric session, Hermes command/provider readback, Google/knowledge/automation/browser canary/media or broker postcondition was verified. The [bounded live health runner](../../tools/certification/LIVE_ACCEPTANCE.md) records missing prerequisites and can run through an existing authorized trusted route. Its successful health result would still be insufficient for owner E2E acceptance.

Additional integration limits are explicit in the registry: Hermes remote lookup/cancellation lacks an evidenced supported protocol; cancellation prevents new gateway work but cannot certify a remote process stopped. Arbitrary browser/free-form work without an independent observer remains UNVERIFIED/UNVERIFIABLE. Provider readiness needs actual credentials, pinned runtime versions and fresh canary evidence. The Rive asset/redesign and rendered handset screen states remain separate work.

Cloud setup instructions are [saved](CLOUD_SETUP_2026-10-07.md), including SDK/JDK/Gradle and the now-resolving pinned native dependencies. Saving the environment draft does not publish it: review/save the environment settings and publish to activate the saved configuration. No production deployment, credential rotation or live trading action was performed.
