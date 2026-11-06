# VAN core implementation and wireless acceptance — 7 October 2026

The owner-selected architecture is implemented locally: VAN backend on `van-trading-core`; Hermes and Artemis on `dial-control`; a separately admitted VAN-only TLS passthrough on `oracle-admin` preserves the phone's hardware-bound mutual TLS to the private core. The existing typed DIAL product gateway remains a distinct service route. No host deployment, wireless pairing, handset installation or live acceptance occurred.

**Current validation: 5,714 passed, 10 skipped, zero failures.** Actual Android arm64 debug build and lint passed; app units: 203; JVM cases: 1082. The receipt records commands, warnings, skips, source stability, XML cases, logs and APK identity. Focused repetitions and earlier implementation-phase counts are excluded.

## Implemented changes

- Release builds require one consistent core deployment profile, explicit admitted public TLS endpoint and matching trust material. Legacy gateway settings are debug-only. Signed external provisioning supplies runtime credentials and routing without app URL, token or TLS configuration screens.
- Core deployment preparation supplies bounded gateway resources, persistent owner database outside the replaced runtime, scoped Commander/Hermes credentials, private callback relay and fixed TLS passthrough. Effective environment checks preserve the core topology against stale trading settings without overriding independently qualified DIAL feature bindings; unconfigured DIAL stays disabled. Compiler URL and CA validation agree with the actual Android release helper, verified by an emitted-profile interop test. Install/qualification require immutable clean source and accurate staged hashes; rollback refuses incompatible schema, configuration or dependencies. Qualification parses settings as data and protects credentials from redirects. These local checks are not deployment-authority receipts.
- Production DIAL development requests and SSE use the actual product-gateway route with TLS 1.3, pinned CA, client certificate/key and separate bearer. Wrong CA, client identity, hostname and direct-route fallback fail closed.
- Owner work shows proposal/digest, trust and injection signals, missing postconditions and effect references. Browser control prevents simultaneous uncertain mutations and stale heartbeat authority; download review/removal verifies matching metadata receipts and independent readback. Unsupported upload/binary transfer is explicitly unavailable; deleting a record does not claim physical file cleanup.
- Artemis proxy OpenAPI operations now have unique IDs with unchanged governed method coverage. SQLite opening/closing survives cancellation and drains its worker without committing a cancelled transaction.
- The Android boundary scanner distinguishes build documentation comments from executable string literals. Planted direct URLs and comment-looking raw strings still fail the scan; the initial false-positive contract failure and final regression evidence are retained separately.
- DDS stale placement/projection guidance is reconciled in an exact-source-bound unapplied patch; the DDS checkout remains unchanged. Existing projection boundary tests passed separately.

## Frontend and Artemis contract

The [interactive frontend registry](OWNER_FRONTEND_CONTRACT.html) contains 42 owner features, 58 functions, 68 screens/surfaces, 285 endpoint operations and 149 schema definitions. It preserves original baseline coverage, current source citations and hashes, typed Android callsite mappings, authority, error/recovery states and partial implementation labels. Browser rendering/search/filter/authority checks passed in Chromium; these are documentation checks, not handset UI acceptance.

The [Artemis plan](VAN_ARTEMIS_ACCEPTANCE_PLAN_2026-10-07.json) has **684 planned cases and 0 executed device cases**. It binds current implementation/registry/Rive/build hashes, exact handset/APK identity, isolated fixtures, screenshots, Logcat, step traces and independent backend/Hermes/service effects. A CLI success or screen launch is insufficient. Function cases use their own declared action/readback; capability cases retain full happy, error and recovery requirements.

## Why live work remains blocked

The current callable tools expose neither Global DIAL/Artemis Android controls nor an account-connector enabling operation. I cannot enable the connector on the owner's behalf from this session. Fresh cloud status has no configured capabilities, outbound identities or secrets. The owner reports wireless debugging enabled and the S24 unpaired; no device admission or network reachability is verified. The existing DDS Android tools also have no wireless-pairing mutation schema; a secure admitted pairing recipe is required.

There is no current approved public ingress/CA, exact deployed revision, production signing identity, private service binding or isolated fixture receipt. The retained debug APK is **not** an owner-core release and uses the debug configuration. The release gate correctly refuses to invent these missing bindings. Browser binary-transfer transport and certain remote Hermes lost-reply/cancellation semantics remain unavailable or unknown until the service contracts exist and are qualified.

DDS [AGENTS.md](/workspace/dial-development-system/AGENTS.md) requires: “Use `node agent-system/orchestration/project-truth-authority.mjs issue ...` only against an existing owner-originated Oracle instruction job; never fabricate an owner instruction or authorization receipt.” The owner has authorized necessary fixes, but no such job/control is exposed here. Therefore the [source-bound DDS reconciliation proposal](dds-owner-core-reconciliation/proposal.json) is reviewable and unapplied; no Project Truth authorization is invented.

## Remaining execution sequence

1. Attach the existing authorized Global DIAL/Oracle/Artemis controls and secure secret bindings. Establish the existing owner instruction job and reconcile the exact DDS patch at the writer's safe boundary.
2. Verify retained host identities, trading headroom, private routes and recovery; admit the fixed VAN ingress and measured Hermes/Commander/provider bindings. Commit/select the exact implementation SHA, stage backup and execute the governed deployment recipe.
3. Qualify authenticated host/service routes, build the owner-signed arm64 release from its bound profile, then pair and admit the S24 through the secure Artemis wireless recipe. Install and externally provision; independently read back hardware, APK, device certificate and session admission.
4. Execute the registry-derived 684-case matrix, including service effects, credential/permission refusal, network loss, lost reply, rotation, process death and reboot. Use demo trading/disposable fixtures and real owner biometrics where required. Keep failed, unavailable and unknown cases open.

[Machine-readable validation](VAN_OWNER_CORE_WIRELESS_VALIDATION_2026-10-07.json) · [Topology and reconciliation](OWNER_CORE_TOPOLOGY_RECONCILIATION_2026-10-07.md) · [Deployment recipe](../../deploy/van-owner-core/README.md) · [Artemis readiness](VAN_ARTEMIS_LIVE_READINESS_2026-10-07.json)
