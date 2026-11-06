# VAN owner-core deployment implementation — 2026-10-07

Scope: local VAN repository implementation. No host deployment, firewall rule, phone
connection, broker action, DDS Project Truth mutation or production qualification occurred.

Selected roles are explicit: VAN backend on retained `van-trading-core`; Hermes profile
`van` and ARTEMIS on `dial-control`; proposed owner-phone ingress on `oracle-admin` as a
separate VAN-only end-to-end TLS passthrough capability. The DDS development HTTP/SSE
proxy remains a different, limited lane. The new phone/WSS ingress is pending governed
capability/role reconciliation; it is not already approved by the current product proxy.

Implementation artifacts:

- `deploy/van-owner-core/README.md`: exact role/lane boundaries, binding requirements,
  source/credential/resource preflight, migration, backup/rollback and phone qualification.
- `profile.example.json`: unbound administrative inputs; execution returns BLOCKED and
  emits no configuration. No public URL, CA or ingress receipt is invented.
- `tools/runtime/prepare_owner_core_deployment.py`: emits the agreed external Android
  Properties profile, gateway/Hermes route env selectors, bounded TCP configurations,
  resource drop-in and output hashes. Requires separate measured public ingress/private
  Hermes/private typed Commander routes, public CA, manifest signing selector, persistent
  owner DB, scoped token selectors and an actual receipt reference. Declaration remains
  PREPARED_NOT_DEPLOYED with authority/deployment/live qualification all false.
- `preflight_owner_core.py`: requires retained ARM host identity, exact clean source,
  private WireGuard interface, persistent owner DB outside runtime, owner release signer
  and pinned Google attestation roots, separate enrollment/runtime credentials, private
  key/token selectors, memory availability floor and bounded gateway cgroup.
- `rollback_owner_core.py`: read-only default plan, externally selected previous SHA,
  file hashes, identical config/dependency/schema contracts and read-only SQLite schema
  observation. Optional admitted-recipe application swaps gateway files only, retains the
  failed runtime, never restores owner data, and reports partial failures truthfully.

Existing runtime fixes:

- Production installer refuses unpinned, mismatched or dirty source; stage-only marks dirty
  source truthfully. Receipts hash deployed runtime files and selected configuration. The
  unit loads the optional selected core profile, resource limits and independent runtime
  paths; it has no local Hermes-unit dependency. Private DB and remote typed Commander
  selectors prevent an empty replacement DB and accidental local account-control fallback.
- Mutual-TLS enablement requires an explicit unicast bind and no longer creates a broad
  UFW public-port grant. The selected owner-core device listener is private `10.77.0.4:8443`.
- Host qualification treats env files as data rather than executable shell, keeps ingress
  credentials out of argv, limits health to loopback, refuses redirects, verifies clean
  exact deployed SHA/file hashes and labels GREEN as local-host readiness only.
- Hermes registration accepts an owner-only scoped token file without copying gateway
  credentials or enrollment authority onto control. It uses explicit private core URL,
  preserves sibling MCP configuration, and records only selectors. The shim prioritizes
  this explicit file, refuses missing/public-readable files without ambient fallback,
  rejects redirects and bounds HTTP requests to 90 seconds.
- Backend/deployment docs now describe selected placement, proof-based pairing/recovery,
  dedicated end-to-end TLS ingress, scoped callback lane, DDS product mTLS and approved A4
  memory erasure, replacing stale direct Netcup/Hermes-host and direct-delete guidance.

Final independent-review fixes: `owner-core.env` loads last after optional trading settings
in the real unit and all effective-environment readers. Startup preflight discards invoking
shell `VAN_*` settings; merged effective credentials, including Commander purpose separation,
are checked. Stale trading topology cannot disable device binding/TLS or replace selected
URLs/DB. The independent DDS service flag is preserved: explicitly bound product mTLS may
enable it, while absent binding remains disabled by Settings default. The compiler rejects
empty userinfo and uppercase schemes on all three URL lanes, requires bounded single-only
CA PEM and certificate-signing KeyUsage when present, and its emitted profile passes the
actual compiled Android release validator.

Validation: **95 passed in 13.14 seconds**, zero failures/skips, in
`/workspace/van-audit/owner-core-final-focused-tests.log`. Focused command covered
`test_owner_core_deployment_profile`, `test_owner_core_rollback`,
`test_owner_runtime_mcp_contract`, `test_runtime_installer_paths`,
`test_van_direct_mtls_deploy`, `test_van_mtls_renewal`, and
`test_backend_dependencies_are_pinned`. These overlap the root aggregate contract suite
and must not be added to its totals. Actual localhost servers proved credential redirect
refusal; real temporary certificates, files/SQLite and the real installer/registration
helpers were exercised. Only service/system effects were mocked. Shell syntax, Python
compilation and git diff whitespace checks passed.

Pending evidence: current governed host/ARTEMIS tool route; immutable receipt verification
and admitted VAN ingress recipe/role; pinned HAProxy binary and actual `haproxy -c` parsing;
current host identities, private overlay handshake/port-scoped forwarding/firewall;
placement/headroom admission; independent credentials and persisted PKI/DB migration;
matching server SAN/CA/manifest anchors/release signer; backup and schema-compatible
rollback receipt; owner-signed release installation through ARTEMIS wireless ADB; all
registry journeys with actual owner/service readback and handset evidence. No local
declaration, TCP check, APK compilation or activity launch substitutes for those receipts.
