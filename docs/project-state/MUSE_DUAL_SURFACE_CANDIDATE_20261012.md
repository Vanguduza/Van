# Muse dual-surface integration — candidate evidence

Checked at: 2026-10-12T15:27:34.532799+00:00

## Scope

Owner requirement: native Muse control inside existing VAN Android and equivalent interaction in the original DIAL Work Tracker Site. Existing task registry, signing boundaries, project identities, VPN, routing, firewall and persistent browser sessions remain separate invariants.

## Implemented in this candidate

- Shared durable Muse source/session/approval/command ledger in the VAN gateway, migration31, strict typed messages and decisions, exact source revisions, scope fencing, idempotent receipts and no crash-redelivery.
- Authenticated native routes, current-source/command reads, replayable SSE, existing biometric challenge flow and default-disabled actuation.
- Cross-client owner verification: a Site Allow request requiring step-up is only a proposal; independently verified VAN biometric intent can link it to the actual command. Native Deny supersedes rather than approving the Site proposal.
- Native Compose Chat, Tasks, Approvals, Projects and Inbox screens; receipt reconciliation, foreground lifecycle handling, shared task API adapter, project/task forms and approval notification deep links.
- Native notification integration through the existing VAN event stream. This is not evidence of OS push delivery when the application process is stopped.
- Framework-neutral web component and authenticated Site BFF package under web/muse-interaction. It consumes the original Site's trusted identity/signing/task functions, not a second task store.
- Browser adapter/stdio driver source candidate. Its executable qualification remains open; it has NOT been deployed or certified.

## Executed tests

### backend

```text
........................................................................ [ 46%]
........................................................................ [ 92%]
...........                                                              [100%]
155 passed in 67.23s (0:01:07)

```

### web

```text
TAP version 13
# Subtest: canonical map ordering is shared with Python
ok 1 - canonical map ordering is shared with Python
  ---
  duration_ms: 1.216839
  ...
# Subtest: unsafe floats are rejected
ok 2 - unsafe floats are rejected
  ---
  duration_ms: 0.308661
  ...
# Subtest: signature binds current exact command
ok 3 - signature binds current exact command
  ---
  duration_ms: 2.22385
  ...
# Subtest: signature rejects changed body
ok 4 - signature rejects changed body
  ---
  duration_ms: 0.419054
  ...
# Subtest: wrong producer is rejected
ok 5 - wrong producer is rejected
  ---
  duration_ms: 0.223489
  ...
# Subtest: expired command is rejected
ok 6 - expired command is rejected
  ---
  duration_ms: 0.207454
  ...
# Subtest: no blanket approval operation exists
ok 7 - no blanket approval operation exists
  ---
  duration_ms: 0.258894
  ...
# Subtest: durable claim prevents replay after restart
ok 8 - durable claim prevents replay after restart
  ---
  duration_ms: 10.809188
  ...
# Subtest: same id with different contents is rejected
ok 9 - same id with different contents is rejected
  ---
  duration_ms: 6.984329
  ...
# (node:2385478) ExperimentalWarning: The Ed25519 Web Crypto API algorithm is an experimental feature and might change at any time
# (Use `node --trace-warnings ...` to show where the warning was created)
# Subtest: authenticated Site read uses its existing owner signer
ok 10 - authenticated Site read uses its existing owner signer
  ---
  duration_ms: 55.218606
  ...
# Subtest: a service label is not an owner session
ok 11 - a service label is not an owner session
  ---
  duration_ms: 0.861433
  ...
# Subtest: cross-origin writes are refused
ok 12 - cross-origin writes are refused
  ---
  duration_ms: 1.125506
  ...
# Subtest: native task bridge requires exact signed gateway owner intent
ok 13 - native task bridge requires exact signed gateway owner intent
  ---
  duration_ms: 10.36796
  ...
# Subtest: changed gateway task arguments cannot be forwarded
ok 14 - changed gateway task arguments cannot be forwarded
  ---
  duration_ms: 2.22334
  ...
# Subtest: unrelated service operations are not admitted
ok 15 - unrelated service operations are not admitted
  ---
  duration_ms: 2.161634
  ...
# Subtest: expired native attestation is refused
ok 16 - expired native attestation is refused
  ---
  duration_ms: 1.642735
  ...
# Subtest: client retry retains its exact intent
ok 17 - client retry retains its exact intent
  ---
  duration_ms: 1.276512
  ...
# Subtest: stale observation is never shown as live
ok 18 - stale observation is never shown as live
  ---
  duration_ms: 0.273597
  ...
1..18
# tests 18
# suites 0
# pass 18
# fail 0
# cancelled 0
# skipped 0
# todo 0
# duration_ms 246.110335

```

## Open gates — do not merge or deploy as finished

1. Sites source/publishing is unavailable through the current session's tools after actual discovery attempts. The original Site has NOT been edited or republished. The provided BFF must be integrated into its original owner-authenticated backend and actual command relay; callbacks cannot be replaced with mocks.
2. A combined Chromium fixture/approval test operation was blocked by the platform. It was not rerouted. No real Allow/Deny effect has been qualified. A harmless independent read-only Muse browser probe succeeded without needing a permission prompt, which is not approval evidence.
3. The new browser observer/actuator needs independent review, a qualified outbound supervisor and current-job binding source, provider prompt fixtures and live owner-authorized acceptance. Known candidate review items: distinguish an identical replacement DOM prompt; invalidate generation on navigation; account for persistent-permission toggles; require stronger provider outcome confirmation; carry streaming/truncation evidence. Do not activate its Allow route until these are closed.
4. Android exact-head compilation, emulator/phone UX and background notification delivery require their own evidence. Older PR95 green checks do not apply to this candidate.
5. Cross-surface E2E, device pairing/proof, safe rollout and runtime baseline comparison remain pending. Neither gateway nor Site is deployed by this source commit.
6. Reconcile isolated VAN branch with current canonical lineage/parallel work before merge. No main/master update or release is authorized by this report.

## Activation safety

Both VAN_MUSE_ENABLED and VAN_MUSE_ACTUATION_ENABLED default false. Source risk labels cannot remove biometric requirements; A5 remains prohibited. The Site cannot turn a bearer/service credential into owner identity. No credentials, cookies or keys are included here. No browser test was moved into CI to avoid a blocked tool operation.

## Original Site integration

Serve client.mjs and muse-live-controls.mjs as same-origin modules and add the custom element inside the existing Muse portal while retaining its task/history/project/inbox pages. Register createMuseBff before generic route handling. Supply the real requireOwner, signOwnerEnvelope, existing fixed authenticated transport, and invokeExistingTask from the original Site. Configure only the server-side public gateway key and exact owner/audience. The current package returns unavailable when these connections are absent. Do not create a lookalike replacement site and call the task complete.

## First exact-head CI corrections

GitHub run 38270400872 on 6462d4e77c3b7a4756a4a5f14a9957a9230c09d0 found two real integration failures: a duplicate `eventTime` local in MuseNotifications.kt and four Muse tables missing retention classification. The full backend suite had 1971 passes and one retention failure; the earlier 155-test subset did not cover that policy. Both are corrected in the following commit. Muse owner intent, consumed permission IDs, immutable bindings and source watermarks are OWNER_STATE to avoid timer-driven replay or history loss. Offline focused retention/Muse tests are rerun before commit; fresh CI still required. No browser control test or runtime deployment is part of these corrections.


## Continuation evidence — 2026-10-12 (Site relay and dual-client controls)

**Still a draft candidate; no release or live provider permission grant was qualified.**

### Site relay validation and recovery

- The original private Site returned HTTP 422 with `INVALID_ARGUMENT`: `progress_summary must contain 0–4000 printable characters.` The durable outbound event sequence **852** contained 177 task records and a maximum preview length of 8,065 characters.
- The dedicated relay source was cloned into a new immutable release rather than modified in place. Preview normalization is per-record, capped below the 4,000-character limit, with explicit coverage notes and full captured artifacts preserved separately.
- Isolated tests against all 177 records passed: 177 records retained, no invalid previews, maximum preview 3,888 characters. The original rejected event was retained under the root-protected repair quarantine, SHA-256 `ce001e797c64b267324755f2dc2b7cc89f828f7a044d8c459961e1feeec998fc`. The corrected event retained sequence 852 but uses a distinct immutable event ID; later acknowledged Site source observations resumed. No historical task was deleted.
- Active dedicated relay release: `/opt/dial-muse-site/releases/muse-site-owner-v1-preview-contract-20261012`; corrected relay script SHA-256 `d66eaa69468327d39fb18350fd0a5ae215fb6696847a711fc900efb3261ac1a3`. Only `dial-muse-site-relay.service` was stopped/started for this specific release change.
- The recorded before/after IP address, routes and policy-rule hashes matched. A raw nftables ruleset hash varied during the observation interval and is **not** evidence of a firewall configuration change or a completed network-invariance certification. No VPN/firewall/routing/browser configuration was intentionally mutated.
- The relay is **receiving** again, not operationally qualified: Global DIAL native host health reports `MUSE_HOST_UNREACHABLE`; the fixed SSH route to the existing VAN host timed out. The existing `wg-dial` interface is up and the route to `10.77.0.4` is present, but this does not prove a live WireGuard peer or a healthy Muse browser.
- A short-lived observation exposed a separate original-Site logic risk: controls may appear available when the source is fresh but native session health is `UNOBSERVED`. Later source observations reported `NOT_READY` / `DEGRADED` and the original Site disabled controls. A runtime health-gate tightening operation was **blocked before execution** by the owner execution approval system and was not rerouted; it is **not deployed**. The candidate Site client requires both health and watchdog GREEN, independently of control admission.

### PR 95 source improvements and unit qualification

- Initial Android issue corrections: Android 13+ notification permission check, actual Compose use of typed live approval/source-health fences. Six exact-head checks succeeded on `7fa406e9f7909dd96c722c4f0b83e406c21f385a`; these do not qualify browser interaction.
- Added DOM-identity fencing for visually identical replacement Muse approval prompts, rejects persistent/Always Allow controls, requires current complete source observations before browser actuation, and refuses to equate a disappeared button with an actual provider-confirmed permission grant.
- Added Site presentation checks for exact prompt binding/revision/fingerprint and refusal when source health or watchdog is degraded.
- At candidate source `b5320201b19a835b5a29aee3da6c2a03847da640`, **26/26 isolated Node tests passed** on DIAL control (browser adapter, signed protocol and Site BFF/client tests). These use fakes and contain no real Muse clicks. The new exact-head CI/Zuul evidence, live session acceptance, Android device delivery and original Site publication remain separate requirements.
- No branch merge, VAN gateway deployment, Android APK installation, original Site publication, VPN change, or new browser actuator activation was performed by these source corrections.

### Required acceptance order

1. Restore and verify the existing VAN Muse host/watchdog via approved unchanged transport; do **not** rewrite VPN, DNS, WireGuard, routing, firewall, VNC or browser profiles in response to the outage.
2. Qualify the live browser source adapter with realistic provider prompt fixtures, exact mutable DOM identity, persistent-toggle rejection, and independent provider-side outcome confirmation. Only then admit permission actuation.
3. Wire and publish the BFF + live web controls to the **original** private ChatGPT Site via its actual authenticated identity and signed DIAL transport. Do not deploy a lookalike replacement.
4. Qualify signed VAN gateway producer/command path, S24 Android A4 biometric approval, live Web/Android message convergence and push delivery with traceable receipts.
5. Reconcile concurrent VAN PR lineages and Zuul qualification, then owner-accept the exact release. Do not mark `QUALIFIED` from unit tests or Site relay liveness.
