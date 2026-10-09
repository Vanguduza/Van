# VAN pre-phone canaries and handset boundary

This is an execution checklist, not a live receipt. Its source bindings are the clean
final VAN `dfc1557ab99ad8d41cf84714e1bb671e89b045e6`. The adjacent immutable
producer/skip inventory records exact current source hashes. No Commander,
service-provider or handset calls were made while preparing this document.

The current deployment profile is integer schema version 2 / `CORE_ONLY_V2`:
the gateway, direct public mTLS ingress and Hermes profile `van` are on
`van-trading-core`. Browser worker trust zones and their actual placement remain
separate dependencies. Native Artemis runs directly through the admitted
DIAL/Commander path on dial-control; it is not dispatched through Hermes.

## Checks that can finish before the S24 is used

1. Select the exact clean corrected source, actual admitted core recipe and current
   authority receipt. Reuse the existing owner database, device CA, encryption
   keys, connectivity signer and provider identities. Record the existing state
   backup, readbacks and rollback ID. Do not initialize replacement owner state.
2. Observe the actual public address/DNS/SAN, dedicated core VNIC/interface and
   HTTPS/WSS port, existing CA, local Hermes listener, placement/headroom, service
   file ownership/modes and narrow credentials. The profile compiler validates
   bindings; it does not admit an ingress recipe or deploy anything.
3. Install/switch only the admitted VAN resources through the existing bounded
   recipe. Confirm the actual deployed source and configuration hashes before
   qualifying the running services. Preserve trading and the stopped Oracle Admin
   VM; an Oracle/VEKL capability name is not admission to use that VM.
4. Collect local native IPv4/IPv6/listener/NAT evidence and independent current OCI
   NSG/security-list/routing evidence. Verify externally observed public TLS and
   server SAN. `PASS_LOCAL_NETWORK_POLICY_ONLY` is not proof of OCI admission.
5. Run the no-phone host-health collector below. It uses existing local narrow
   machine credentials and verifies public anonymous HTTPS/WSS refusal. It loads
   no phone client certificate and makes no owner-command or provisioning claim.
6. Qualify each required actual service/provider and its current entitlement. A
   configured key, `STATIC` capability, unit being active, aggregate provider-ready
   flag or old canary is insufficient. Keep unavailable dependencies explicit.
7. Prepare the release from the existing owner signer, actual core profile/CA,
   trusted connectivity anchors and sealed voice bundle. Verify the actual APK's
   compiled route/trust/source identity, signer, package, ABI, native 16 KiB
   alignment and bytes. A debug APK or separate BuildConfig text is insufficient.
8. Validate the installer and native Artemis plan inputs before connecting the
   handset. Obtain actual native tool schemas and original artifact/effect
   readback access. No fresh phone enrollment or biometric result is needed to
   complete these preparation checks.

All commands below run from the exact selected VAN checkout through its admitted
host recipe. Uppercase angle-bracket values are selectors obtained from actual
bindings, not example identities or credentials. Use new output paths; preserve
the underlying exit status and retain each producer's source hash.

```sh
python tools/runtime/prepare_owner_core_deployment.py \
  --profile <protected-operator-profile.json> --output <new-generated-profile-directory>

python tools/runtime/preflight_owner_core.py \
  --profile-env <generated-owner-core.env> --gateway-env <existing-gateway.env> \
  --google-env <existing-google-workspace.env> --trading-env <existing-trading-commander.env> \
  --resource-dropin <generated-resource-limits.conf> \
  --repository <exact-checkout> --expected-sha <final-selected-40-hex-sha>

VAN_STATE_ROOT=<actual-state-root> VAN_CONFIG_ROOT=<actual-config-root> \
  VAN_EXPECTED_REPOSITORY_SHA=<final-selected-40-hex-sha> \
  bash tools/runtime/qualify_gateway_host.sh

python tools/runtime/owner_core_network_observations.py \
  --declaration <generated-declaration.json> \
  --expected-declaration-sha256 <actual-declaration-sha256> \
  --host-role van-trading-core --out <new-local-network-receipt.json>

python tools/certification/pre_phone_host_acceptance.py \
  --config-root <actual-config-root> --state-root <actual-state-root> \
  --android-profile <generated-android-owner-core.properties> \
  --expected-sha <final-selected-40-hex-sha> \
  --out <new-pre-phone-host-receipt.json> --timeout 10 --max-canary-age-seconds 3600
```

`pre_phone_host_acceptance.py` reads `/health`, `/v1/runtime/status`,
`/v1/automation/health`, `/v1/browser/health`, `/v1/observability/health` over
authorized core loopback and `/p/van/health` on the actual local Hermes API. It
requires exact deployed-source/configuration metadata, current matching CA and
narrow RUNTIME/OBSERVABILITY credentials, plus public no-certificate refusal.
Its strongest outcome is `PASS_HOST_HEALTH_ONLY`; its explicit false handset,
provider-execution, signing, firewall and ingress-authority fields must remain false.

`tools/certification/run_live_acceptance.py` requires an existing client chain
(`VAN_LIVE_CLIENT_CERT_FILE`, `VAN_LIVE_CLIENT_KEY_FILE`). It is not the no-phone
collector and must not cause an artificial requirement to enroll the S24 before
pre-phone host checks can run.

## Existing service/provider producers and required readbacks

| Dependency | Existing producer / service method | Pre-phone qualification and limit |
|---|---|---|
| Hermes profile and model runtime | `HermesBridge.health()`, `capabilities()`, `create_run()` in `backend/van_gateway/hermes/bridge.py` | Verify the real `van` profile and actual configured model entitlement; a harmless admitted bounded run must retain its genuine run ID and independent completion evidence. Health alone does not prove model inference. It cannot authorize an owner effect. |
| Core service stack | `deploy/van-trading-core/qualify.sh`; automation, Supabase and Muse child qualifiers | Bind `VAN_EXPECTED_REPOSITORY_SHA` to the externally selected SHA. Inspect each required row, including scoped credentials, loopback-only services, ledger and firewall. The current broad script contains a Commander health request with disabled TLS verification; that row cannot qualify server trust. Use the separately verified actual CA/SAN and existing typed Commander route. |
| n8n / PostgreSQL / runner | `deploy/van-trading-core/automation/qualify-automation-runtime.sh`; `ExternalRuntimeRegistry.get_evidence()` / `.status()` | Prove actual image/runtime versions, healthy containers, nonprivileged database role, loopback management, isolated runner and a genuine admitted workflow readback. Its runtime GREEN proves topology/health, not owner workflow success. |
| Browser semantic/harness workers | `deploy/van-browser-core/qualify.sh`, installed `guard_canary.py`, `stagehand_production_enabled()` | On the actual admitted browser zone, verify pinned runtime/model, private mTLS edge, known-client success and anonymous/foreign-client refusal, live network-guard canary, no writes after lease revocation and gateway-side current readiness. The trading-core script explicitly forbids Stagehand on trading core. Do not change placement to satisfy a health row. |
| Both browser stream profiles | `VAN_BROWSER_INSTANCE=public bash deploy/van-browser-stream/qualify.sh`; same command with `owner`; `qualify_tls.py` | Qualify both actual profiles independently: separate units/UIDs/listeners, encrypted profile volume, admitted mTLS control client, fenced CDP, exact-IP proxy/private-address refusal, selected profile's real live Chromium PID/arguments and egress UID. The final qualifier uses the selected public/owner unit and UID, verifies live proxy arguments, and validates the complete ordered dedicated nft table, active table flags, per-profile proxy/CDP restrictions and distinct service UIDs. Missing or unsupported observations remain UNKNOWN; inactive or broadened rules refuse GREEN. |
| Computer workspace | `deploy/van-computer-worker/qualify.sh` | This producer creates/removes its own temporary container/volume, so run only inside the admitted recipe. Retain real image ID, network-none/read-only/rootless boundaries, workspace write/read/recreate persistence and resource limits. It qualifies that workspace image, not a phone owner command. |
| Exa research | `POST /v1/runtime/research/certify-canary` → `ExaResearchService.certify_canary()` | Use the existing RUNTIME scope on actual loopback, a bounded public query, QUICK mode and one result; retain provider request/evidence IDs and independently read persisted citations/content digests. A nonempty result is required. Never manufacture a READY row. |
| VEKL read-only projection | `POST /v1/runtime/knowledge/vekl/certify-canary` → `KnowledgeService.certify_vekl()` → `VeklKnowledgeProvider.certify()` | Use an actual current admitted mission ID with observable evidence; retain real query/evidence IDs and independently read their source projection. No new namespace or Oracle job is implied by the API name. |
| Obsidian / Notebook enterprise / consumer | Runtime knowledge certification routes; `KnowledgeService.certify_obsidian()`, `.certify_notebook_enterprise()`, `.certify_notebook_consumer()` | Use actual existing vault/session/project bindings and their own independent evidence. Preserve consumer-session vs cloud-project separation. Missing sessions or unavailable provider contracts remain unavailable; no fabricated notebook or login. |
| Google workspace / model / cloud / consumer planes | `GoogleService` read methods; `plane_health()`; `GoogleIdentityBroker.capability_status()` / `.mesh_status()` | Check all four actual planes separately. A harmless existing GOOGLE-scoped read (`gmail/search`, `calendar/agenda`, `drive/search`, `contacts/resolve`, `tasks`) can prove workspace provider access before phone use. Record actual errors/entitlements and current readback; stored capability evidence/configured OAuth does not prove every plane is live. Sends and owner calendar writes are later signed handset effects. |
| DIAL development / common twin | `DialDevClient.get()` / `.post()` / `.open_stream()` / `UpstreamStream.lines()`; `CognitiveTwinClient.read()` | Use actual account/project-scoped DDS route and existing credential selectors; retain sanitized source/project correlations. Verify initial connectivity and bounded SSE EOF/transport-error/cleanup behavior. Local MockTransport/ASGI regressions prove wiring, not the loaded DIAL route. |
| Trading / Temporal | `TradingService.status()` / positions/tickets readbacks; current core qualification runtime rows | Observe actual ledger/heartbeat/Temporal health and independently bound service identity. No live order is a canary: `trading.vati.submit_order` is `NEVER_ROUTABLE` in the current canonical registry. Owner controls and effects belong to the signed acceptance phase. |
| Oracle owner archive and VEKL owner-candidate ingress | `OwnerArtifactProvider.probe()` / `OwnerArtifactAdmissionService._qualified(provider)` | Probe each required provider separately over its actual CA/mTLS/principal binding. Match current capability digest, provider identity, owner/project namespace, admission issuer/signer, atomic claim/introspection and observation-expiry contract. VEKL additionally requires its actual admitted Oracle instruction job. Aggregate `is_ready()` succeeds when any provider qualifies; it cannot certify both. Contract/route readiness can finish pre-phone; the actual owner-file A4 write/readback is a handset case. |
| Optional local Glimmer model | `tools/cognitive/qualify_glimmer.py` | Only if this model is required/admitted: use the actual already-installed artifact SHA, real license/placement/sandbox receipts, current measured loopback endpoint/PID and independent benchmark evidence. This tool never installs/activates a model. An unavailable optional lane is an explicit registry outcome, not a universal assistant failure. |

Fresh provider effects need genuine effect IDs and independent provider/byte readbacks.
For artifact submissions, the actual one-use claim, target PUT and separate persisted
bytes are tested through the canonical signed A4 flow during S24 acceptance. Do not
mint a fake owner approval or report a read-only capability probe as that write test.
An unknown write remains unknown; read-only recovery must not re-send it.

## Release preparation is separate from phone provisioning

Use the existing `android/tools/package_voice_assets.py` and corrected release
`.github/workflows/van-owner-release.yml` to acquire/verify the pinned generic
bundle before assembly. Then run the real release tasks with the existing signing
inputs and generated core profile.
`tools/release/owner_release.py packet` binds the actual APK, profile, trust anchors,
final selected source SHA and independently known owner signer. The final producer
checks the provenance asset inside the signed APK against the selected route, CA,
trust-anchor bytes and exact source; separate BuildConfig text cannot substitute
for that APK-byte binding. This can finish without the phone; no owner speaker
embedding is required in a generic signed APK.


The existing packet command for this frozen source is:

```sh
python tools/release/owner_release.py packet \
  --apk <actual-owner-release.apk> --profile <generated-android-owner-core.properties> \
  --trusted-keys <actual-connectivity-trusted-keys.txt> \
  --build-config <actual-release-BuildConfig.java> \
  --expected-sha dfc1557ab99ad8d41cf84714e1bb671e89b045e6 \
  --expected-signer <independently-known-owner-signer-sha256> \
  --apksigner <actual-sdk-apksigner> --aapt <actual-sdk-aapt> \
  --output <new-owner-release-packet.json>
```

The packet intentionally leaves deployment, provisioning, live qualification and
producer authenticity false. Those require their own original evidence.

Attestation *roots*, production signing certificate fingerprint, trusted server CA,
and provisioner credential/route are pre-phone bindings. An S24 attestation chain,
hardware-key fingerprint, biometric signature and enrolled voice profile can only
be measured on that phone. Their absence before installation is not a host failure.

## S24 phase after those prerequisites pass

1. Recheck the current owner-paired private wireless ADB endpoint directly through
   native Artemis on dial-control. Retain original successful `get-state`,
   `shell getprop ro.serialno` = `RFCX2054F5W` and `shell getprop ro.product.model`
   = `SM-S928B` readbacks. The wireless ADB serial is the actual private IPv4:port,
   distinct from the hardware serial. `SM_S928B` from `adb devices -l` is a sanitized
   descriptor and is rejected as physical acceptance identity. The native binding
   requires the paired TLS authentication type and readbacks no older than 300
   seconds; it verifies offline consistency only, so recheck the actual device
   before each dispatch and after transport loss/reboot. No Windows USB prerequisite
   applies to this wireless route. Backend/product Hermes remain on van-trading-core;
   handset actuation stays direct native Artemis on dial-control.
2. Run `tools/provisioning/provision_owner_device.py` with the actual owner release
   APK/packet/profile/anchors/source/signer and admitted serial/model. It obtains
   the signed short-lived gateway packet and waits for real binding, pairing,
   certificate and session admission; token staging is not provisioning success.
3. Observe hardware-backed attestation and real Android OS permissions/biometric
   consent. No in-app URL, port, CA, model or token configuration is required.
4. Execute the current source-bound registry/Artemis matrix directly through native
   Artemis tools. Use `tools/certification/artemis_acceptance.py prepare
   --native-schema <actual-schema.json>` and `native-call` with actual identity
   evidence. Retain current source/APK/deployment/fixture IDs, screenshots, logcat,
   native trace and independent effects for each case, including error/recovery.
5. Measure the phone-only behaviors: wake/audio/ASR/TTS quality and barge-in, private
   biometric speaker enrollment/removal, overlays, notifications, lifecycle/Doze/
   reboot, browser media/input/download/share, permissions, signed owner actions,
   stale context/refusal, offline queues/reconnect and provider write recovery.


Prepare the native wireless candidate plan and one exact case's tool arguments
with the existing producers (preparation does not dispatch or mark a case passed):

```sh
python tools/certification/artemis_acceptance.py prepare \
  --device-transport WIRELESS_ADB --native-schema <actual-current-native-schema.json> \
  --source-manifest <actual-frozen-source-manifest.json> --out <new-native-plan.json>

python tools/certification/artemis_acceptance.py native-call \
  --plan <new-native-plan.json> --native-schema <actual-current-native-schema.json> \
  --case <exact-registered-case-id> --device-serial <actual-private-ipv4:port> \
  --device-binding <fresh-original-wireless-identity-readback.json> \
  --out <new-exact-native-call.json>
```

Retain the direct native MCP result/trace and original independent artifact/effect
bytes separately. Do not submit native results to the legacy DDS validation path.

`device_cert_probe.py` is a physical identity/checklist helper. It never marks a
case passed. An Artemis process exit code or generated acceptance plan also cannot
substitute per-case original evidence and independently verified effects.

## Backend qualification coverage and skip inventory

The authoritative full backend selection is the clean final
`dfc1557ab99ad8d41cf84714e1bb671e89b045e6`. Its full-run outcomes are **PENDING**
as of this checklist's creation. The new runner uses short `/tmp/vbf-dfc1557a`
and separate immutable receipt prefix
`/workspace/van-audit/canon-corrected-backend-full-dfc1557a-2026-10-09`.
Do not substitute an earlier candidate, a focused pass, or running progress for
this exact final run's completed JUnit/terminal outcomes.

The preceding 805f3b67 full run completed: **5,100 passed, 2 failed, 5 skipped**,
with zero errors or expected failures. Its source and installed dependencies
remained unchanged. This is a complete diagnostic run, not a complete pass. It
exposed two reproducible browser runtime defects: the shared URL parser decoded
encoded dots inside a nondot path segment differently from Chromium, and the
Harness center hit test treated a directly owned CSS pseudo-element as an
unrelated node. Both runtime defects are corrected in the final frozen source;
the original major-5 and major-3 Chromium regression assertions remain intact.
The new pseudo ownership test file adds 17 real-Chromium guarded-click, foreign
normal/pseudo overlay, nested control, late-overlay and live-CDP fault regressions.
The selected-source focused receipt is separate from full backend acceptance.

Earlier candidates remain historical diagnostics. The 4ad run was interrupted
after 440 completed passes; 7526d3e9 was deliberately interrupted after 693 passes
for a stale services-test assertion and README/registry metadata correction.
The 8d0104f5 run was interrupted with 1,192 terminal-confirmed passes, 8 failures,
36 errors and 1 prerequisite skip. Its 44 failure/error records reported AF_UNIX
paths exceeding the Linux limit because the outside runner chose a long temporary
root; one unfinished unannotated JUnit record is unknown. The same first-error
case passed unchanged using a short `/tmp` root. No source assertion or runtime
behavior was weakened to resolve that runner mistake.

The current backend selection is exactly `backend/tests`, with all 4,015 tracked source,
test, fixture, registry and documentation bytes bound before and after execution.
The isolated test venv matches the prepared dependency versions and adds actual
`pypdf==6.19.0`; Chromium is the actual installed Chrome for Testing 153.0.8010.12.
Tests must not weaken assertions, add environment skips or alter frozen inputs.

| Existing skip family | Condition / interpretation |
|---|---|
| Browser actual Chromium tests | Chromium/Playwright unavailable; the existing installed binary and pinned Playwright will be selected, so this should not be used to skip ordinary local browser tests. |
| Browser TLS/guard tests | `/usr/bin/openssl` or required local non-loopback address absent. OpenSSL is present; actual address prerequisites must be recorded, not assumed. |
| Configured-client UID isolation | Root and `setpriv` are required by the existing cross-UID test. The cloud executor is uid 1000. Its skip is not live UID/firewall qualification; the admitted host qualifier must measure real selected browser identities. |
| Historical upstream DDS reproduction | The optional DDS checkout/39d3777 object is absent. Vendored DDS blob assertions execute before that skip. An actual historical upstream comparison remains distinct from current loaded-host behavior. |
| Intentional B1 operation exclusions | Three parameters (`click`, `scroll`, `select`) skip because they are members of the allowed closed set, while this test checks forbidden operations. They are intentional applicability skips, not missing browser prerequisites. |
| PKI fixture script presence | The two existing rotation tests skip only if their production PKI script is absent; it exists in the selected source. |

JUnit outcomes must report passes, failures, errors, skips, expected failures and
interruption separately. Even a complete green local run cannot prove live
deployment, OCI policy, actual provider entitlements, owner signing or S24 behavior.
