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
