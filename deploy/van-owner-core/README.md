# VAN owner backend on van-trading-core

The owner's selected backend is `van-trading-core` (retained Oracle A1, private overlay
`10.77.0.4`). Hermes profile `van` and the ARTEMIS Android testing plane remain on
`dial-control` (`10.77.0.1`). Run the gateway as a separate owner-service identity with
no `vati`, `docker` or unrestricted `sudo` membership. The existing trading installation
and its risk/execution authority remain governed by `deploy/van-trading-core`.

The phone's endpoint is a separate, dedicated **VAN-only TLS passthrough on oracle-admin**,
which forwards TLS bytes to private core `10.77.0.4:8443`. It preserves the phone's client
certificate, pinned server CA, HTTPS, WSS and bootstrap policy at the core gateway. There
is no TLS termination, forwarded certificate header, PROXY protocol or public trading
listener. `dial-control` remains private for product traffic.

This is a prepared implementation, not a currently admitted ingress capability. The
existing DDS product gateway is an overlay HTTP/SSE proxy with a limited development
allowlist; it does not supply this VAN phone/WSS lane. The new capability
`VAN_OWNER_TLS_PASSTHROUGH_V1` needs an exposed, governed deployment recipe and a matching
immutable authorization receipt. DDS topology/role reconciliation must enter through an
owner-originated Oracle instruction job; these files do not modify DDS Project Truth.

## Required bindings

Fill a copy of `profile.example.json` using observations from the admitted host route.
The committed example deliberately has null bindings and exits `BLOCKED`.

- The approved public HTTPS root URI, unprivileged dedicated port, and actual oracle-admin
  VNIC IPv4 on which to bind. Never bind the existing DDS overlay address `10.77.0.2:8443`.
  Behind OCI NAT, the observed VNIC address can differ from the public URI. No URI or DNS
  address is guessed; historical Netcup `62.83.35.103:8443` cannot qualify this profile.
- The exact governed ingress capability receipt ID. The compiler binds this reference;
  the deployment broker must independently verify its signature, scope, host identities,
  source SHA and expiry. A declaration is not an approval.
- The measured Hermes profile API URL on `http://10.77.0.1:<port>` over WireGuard,
  and the separate scoped owner-runtime token file on the Hermes host. The API port is
  explicit and is not the limited DDS development projection port by inference.
- Public device CA file; persistent gateway mTLS directory and owner database file outside
  the replaceable runtime, within `VAN_STATE_ROOT`; existing manifest signer private-key
  selector and key ID. Install matching public manifest-verification anchors into the APK
  through the release build's `VAN_CONNECTIVITY_TRUSTED_KEYS` setting.
- The measured, certificate-matching private typed Commander HTTPS endpoint on the core,
  its CA selector and separate **gateway-purpose** token file. This avoids the gateway's
  development `LocalAccountControl` fallback and does not give Hermes broker credentials.
- Optional `browser_artifact_providers_file` and `mtls_machine_client_ca_file` absolute
  operator file selectors. The compiler emits `VAN_BROWSER_ARTIFACT_PROVIDERS_FILE` and
  `VAN_MTLS_MACHINE_CLIENT_CA_FILE` only when bound; omission retains unavailable machine
  provider defaults. Preflight checks regular files and literal paths without reading
  their contents, refuses symlinks, and requires provider configuration mode 0600. A
  public machine-client CA may be mode 0644. The backend must separately validate actual
  provider endpoint, certificate identity/pin/scope and CA contents before admitting a
  claim. Machine claims use the admitted public TLS passthrough; this selector adds no
  direct private core edge and grants no phone/owner authority.

Prepare in the authorized checkout, without host effects:

```bash
python tools/runtime/prepare_owner_core_deployment.py \
  --profile /authorized/settings/owner-core.json --output /authorized/staging/owner-core
```

Output: `android-owner-core.properties`, `owner-core.env`, `hermes-runtime.env`, two bounded
HAProxy TCP configurations, gateway resource drop-in, and a hash-bound `declaration.json`.
The receipt says `PREPARED_NOT_DEPLOYED`, `ingress_authority_verified=false`, `deployed=false`
and `live_qualified=false`. It never reads or copies private key/token material. Invalid
inputs create no configuration and do not overwrite a prior prepared output.

## Exact deployment recipe boundary

The admitted recipe must perform these checks and effects; do not use generic remote
administration to work around missing recipe capability:

1. Verify fresh identity of the retained core and oracle-admin, exact clean committed VAN
   SHA, the immutable ingress receipt scope, current trading placement admission, recovery
   path and backup. Core must have at least 5 GiB `MemAvailable`: a 1 GiB gateway limit plus
   a 4 GiB floor for existing trading/system work. The live placement governor can require
   more. No trading unit is restarted or broker credential is rotated by this recipe.
2. Bind owner-service secrets in mode 0600 files: independent ingress, device-secret and
   Google-token encryption keys, gateway→Hermes bearer, narrowly scoped Hermes→gateway
   runtime/provider callbacks, operator-only enrollment, owner release signer fingerprint
   and pinned Google Android attestation root fingerprints. Disable the legacy all-scope
   control token. Provisioning credentials never enter Hermes's environment or the APK.
   Each hosted service retains its independent credential and readiness evidence.
3. Confirm the existing device CA and keystore identity before migration. Migrate owner
   state using SQLite's backup API to the persistent `VAN_DATABASE_PATH`; preserve all
   encryption keys, device bindings, issued/revoked certificates, outbox receipts and
   callback inbox/run bindings. Do not regenerate an existing CA or start an empty DB.
   Issue a server certificate whose SAN matches the approved public URI, using the
   existing CA. The selected core profile keeps the device listener private.
4. Admit only these source-preserving private lanes on `wg-dial`, including exact
   corresponding AllowedIPs and hub forwarding where needed: oracle-admin `10.77.0.2`
   → core `10.77.0.4:8443`; dial-control `10.77.0.1` → core `10.77.0.4:8787`; core
   `10.77.0.4` → the measured Hermes API port on `10.77.0.1`. Preserve these sources,
   apply no masquerading, and admit established replies. The private core relay also
   refuses every source except `10.77.0.1/32`. Core `8787`, `8443`, Commander and other
   trading/provider ports receive no public firewall grant.
5. Use the measured, pinned HAProxy binary (version/hash and TLS passthrough module
   capability recorded in the governed recipe). Run `haproxy -c -f` on both generated
   configurations before publishing listeners. Keep the new oracle-admin owner ingress
   on its explicit VNIC/port, separate from its existing DDS overlay listener. It accepts
   only this VAN TCP forwarding workload; no worker or control runtime is installed there.
6. Install the exact clean core source through the gateway recipe, with these explicit
   selectors. `preflight_owner_core.py` checks local identity, source, configuration,
   credential separation, permissions, private interface and resource headroom before
   replacing any runtime. The unit loads `google-workspace.env`, `gateway.env`, optional
   `trading-commander.env`, then `owner-core.env` **last**. The installer, host qualifier,
   rollback inspector and preflight use the same effective merge. The selected topology
   wins over stale trading flags; effective secrets are checked for purpose separation,
   including the Commander token. Staged startup removes ambient `VAN_*` settings from
   the invoking shell so an incomplete unit configuration cannot pass using shell secrets.
   The profile applies `MemoryHigh=768M`, `MemoryMax=1024M`, `CPUQuota=100%`, `CPUWeight=20`,
   `IOWeight=20`, `TasksMax=128`.

```bash
VAN_STATE_ROOT=/authorized/owner-service/state \
VAN_CONFIG_ROOT=/authorized/owner-service/config \
VAN_OWNER_CORE_PROFILE_ENV=/authorized/staging/owner-core/owner-core.env \
VAN_OWNER_CORE_RESOURCE_DROPIN=/authorized/staging/owner-core/van-gateway-resource-limits.conf \
VAN_EXPECTED_REPOSITORY_SHA=<externally-selected-clean-40-hex-SHA> \
  bash tools/runtime/install_van_gateway_service.sh
```

The paths above are placeholders for bound settings, not live host observations. Stage-only
review can use `VAN_INSTALL_STAGE_ONLY=1`; it never replaces the running runtime or unit and
its receipt marks a dirty source accurately. Production install refuses a dirty or
mismatched checkout, records staged source hashes, and uses locked dependencies. Each
lock selects its own interpreter under `VAN_STATE_ROOT/venvs/<lock-sha256>`; completed
environments are reused without running pip. A new dependency installation and staged
startup happen before the serving runtime/unit changes. Their failure leaves the serving
interpreter untouched. The unit and `RUNTIME_PYTHON_PATH` retain the exact interpreter;
the rollback and mTLS tools select that binding. An incomplete existing dependency
directory is refused until the admitted recipe reconciles it. Old dependency environments
remain available for rollback; cleanup is a separate governed retention operation.

7. On dial-control, supply only the scoped runtime token selector and generated
   `VAN_OWNER_RUNTIME_HOST=van-trading-core`, `VAN_OWNER_RUNTIME_URL=http://10.77.0.4:8787`.
   Run the existing profile installer/doctor and `tools/hermes/register_owner_runtime_mcp.sh`
   through the admitted recipe. The registration writes the token **path**, never its
   value, preserves sibling MCP definitions, and takes a private backup. The shim prefers
   the explicit scoped file, refuses missing/public-readable files, does not fall back to
   ambient all-scope credentials, refuses redirects and bounds requests to 90 seconds.
   Lost replies to mutations require inspecting the existing action/mission identity.
8. Build the owner-signed arm64 release with `VAN_DEPLOYMENT_PROFILE_FILE` pointing at
   `android-owner-core.properties`, matching manifest-verification anchors and the signer
   fingerprint configured on the core. Deliver one short-lived signed provisioning
   envelope through ARTEMIS's admitted private ADB installation lane. The current S24 is
   connected to the owner's Windows PC by USB; native Artemis uses its dedicated private
   loopback ADB bridge without Hermes test orchestration. The app requires
   no URL, token, TLS or pairing settings entered on the phone.

### Owner release delivery and deterministic provisioning

The dedicated `.github/workflows/van-owner-release.yml` builds and uploads an owner-signed
release packet when the `van-owner-release` GitHub environment has these bindings:

- Public variables: `VAN_OWNER_CORE_PROFILE_BASE64` containing the compiler's complete
  `android-owner-core.properties`, `VAN_CONNECTIVITY_TRUSTED_KEYS` containing newline
  separated `kid=PEM` P-256 public anchors with PEM line breaks represented by literal
  `\\n`, and independently approved `VAN_OWNER_SIGNER_SHA256`.
- Private secrets: `VAN_OWNER_KEYSTORE_BASE64`, `VAN_OWNER_KEYSTORE_PASSWORD`,
  `VAN_OWNER_KEY_ALIAS`, `VAN_OWNER_KEY_PASSWORD`. These are never supplied in command
  arguments or artifacts. The runner writes mode 0600 files and removes private signing
  material even on failure. Existing keystore configuration is refused rather than
  overwritten.

`tools/release/owner_release.py` verifies the clean selected SHA, APK signature, exact
owner signer, package `com.dial.van`, non-debuggable manifest, arm64-only native libraries,
generated release BuildConfig's endpoint/CA/anchors, and public profile hashes. Missing
bindings refuse the build. The uploaded packet contains the APK, public deployment profile,
public anchors, and `release-packet.json`; it never contains a keystore, password, enrollment
credential or provisioning envelope. The packet establishes artifact consistency and APK
signer identity; its hashes alone do not authenticate a CI producer or admit an ingress.
Select its source SHA and signer through the existing authorized release channel.

The installation recipe invokes this step only after host wiring is qualified, with the
verified packet staged privately and the operator-only enrollment credential bound in the
process environment. The operator API below is core-local; it is different from the
public phone URL in the profile. Artemis must already independently admit the exact ADB
endpoint, handset identity and device serial. For example, with bound paths and serial:

```bash
python tools/provisioning/provision_owner_device.py \
  --gateway http://127.0.0.1:8787 \
  --device-gateway-url <public-root-from-selected-profile> \
  --internal-token-env VAN_DEVICE_ENROLMENT_TOKEN \
  --apk <verified-packet>/owner-release.apk \
  --release-packet <verified-packet>/release-packet.json \
  --deployment-profile <verified-packet>/android-owner-core.properties \
  --trusted-keys <verified-packet>/connectivity-trusted-keys.txt \
  --expected-release-sha <approved-clean-source-SHA> \
  --expected-signer <approved-owner-release-signer-SHA256> \
  --apksigner <observed-build-tools>/apksigner --aapt <observed-build-tools>/aapt \
  --serial RFCX2054F5W --expected-model SM_S928B
```

The recipe must place the operator-local call and the admitted ADB access on the correct
host/transport; this example does not establish that either is present. The installer
refuses implicit device selection, a mismatching model, tampered APK/profile/anchors,
wrong signer/SHA/route, invalid envelope signature, standing credentials, or a stale or
overlong enrollment window before handing the payload to Android. It installs before
minting the short-lived payload and never automatically retries credential issuance.
It waits for the gateway's hardware binding, pairing, client certificate and observed
WebSocket admission receipt. Explicit `--allow-development-artifact` is retained for
development only and prints `owner_release_artifact_verified=false`; it never qualifies
this production release lane. No host or handset acceptance is inferred from CI success.

## Qualification and rollback

`tools/runtime/qualify_gateway_host.sh` is a **host-local** check: it requires production
binding, scoped credentials, authenticated loopback health, an externally selected SHA,
clean deployment metadata and matching staged file hashes. It parses configuration as
data, does not execute shell substitutions, does not put credentials in arguments, and
refuses health redirects. GREEN explicitly leaves owner/Hermes/phone E2E unverified.

Record and verify a SQLite backup before startup migrations. Back up private encryption
keys and PKI through the governed secret-backup plane; the generic DB backup tool cannot
discover these external configuration selectors by itself. Keep the previous runtime and
unit. The new `rollback_owner_core.py` defaults to a read-only plan and requires the
externally selected previous SHA, matching runtime hashes, unchanged configuration,
identical locked dependencies, the exact available previous immutable interpreter and an
identical current/previous/DB schema version.

```bash
python tools/runtime/rollback_owner_core.py --state-root <bound-state-root> \
  --config-root <bound-config-root> --expected-previous-sha <previous-40-hex-SHA>
```

Only an admitted deployment recipe may add `--apply`, under its deployment lock with owner
ingress quiesced. It swaps only gateway runtime/unit files, retains the failed runtime,
does not restore or delete owner data, and reports restart with health still unverified.
A schema/configuration/dependency mismatch blocks this automatic rollback; an explicit
migration/data recovery plan is required. Failed or ambiguous service operations produce
`ROLLBACK_FAILED_RECONCILE` with the last reached phase rather than claiming no effect.

Phone acceptance must separately prove pinned TLS/SAN, Android attestation, exact device
binding, matching client certificate, WebSocket admission, signed commands, real Hermes
callback and independent service readback. Use the owner feature/screen registry for all
ARTEMIS journeys, including errors, Wi-Fi/mobile switching, process death/reboot,
revocation, permissions and biometric refusal. A TCP health check, activity launch,
instrumentation compilation or registry coverage entry is not phone acceptance.

### Host acceptance before handing a packet to ARTEMIS

The admitted core recipe can execute `tools/certification/pre_phone_host_acceptance.py`
before any S24 operation. Bind its `--config-root`, `--state-root`, public
`--android-profile`, approved `--expected-sha` and evidence `--out` selectors. It verifies
the installed runtime and effective environment hashes, core identity, matching public
endpoint/CA and single-scope operator acceptance credentials before network observations.
It reads local service health and the measured private Hermes profile, then checks pinned
TLS 1.3 public HTTPS/WSS refusal without a device certificate. It never mints a ticket,
loads a client key, installs an app, or changes host/firewall state. See
[LIVE_ACCEPTANCE.md](../../tools/certification/LIVE_ACCEPTANCE.md) for the command and
credential purposes. `PASS_HOST_HEALTH_ONLY` keeps deployment authority, actual firewall
admission, APK signer, fresh provider execution and device acceptance unverified.

The final host recipe must also produce these independent observations before provisioning:

1. A verified immutable capability/deployment receipt covering the observed oracle-admin
   VNIC/public URI and port, private `10.77.0.4:8443` target, source SHA, TLS passthrough/WSS
   capability, identities and expiry. The compiler's declaration and receipt ID supply
   references, not signatures or authorization.
2. Current `wg-dial` peer/handshake and source-preserving firewall observations on the
   three hosts, with the exact private lanes in step 4 and no public core listener. Validate
   the actual installed firewall rules and listener observations; local parser fixtures
   cannot attest a remote kernel or OCI security-list/NSG policy.
3. `haproxy -c` against the generated configurations with the recipe's measured binary,
   observed listener/source bindings, and the gateway's local source/health qualification.
   Public CA/SAN verification must use the generated APK profile without a TLS-terminating
   intermediary.
4. Fresh service-specific functional canary execution and independent readback for the
   enabled Hermes, browser profiles, n8n callbacks, trading Commander and hosted-provider
   features. Bind their admitted operation identities and evidence pointers into the
   service readiness plane. A historical `READY` body alone does not prove this run.
5. Current SQLite backup plus secret/PKI recovery receipts and a read-only rollback plan
   for the selected previous deployment. Do not test rollback by restoring live owner data
   or restarting trading units.
6. Independent owner-signature and exact-source verification of the complete release
   packet using `tools/release/owner_release.py`, with matching server signer/attestation
   policy and public manifest anchors. No debug APK or freshly invented owner signer is
   admitted as the owner's release identity.

Missing capability, endpoint, signer, PKI or provider bindings are deployment prerequisites.
The cloud developer-workspace draft does not supply them. Publishing that draft makes
workspace setup reusable; it does not deploy this recipe or qualify production hosts.

### OCI image firewall observation

`deploy/van-trading-core/oci/harden-oracle-image-firewall.sh --verify` performs only
`iptables -S`/`-C` reads and persistent-file inspection. It can run without UID 0 where
the admitted observation identity can read the actual kernel rules; insufficient kernel
privilege fails RED. Mutation still requires root and an exact supported CLI. Verification
refuses malformed/ambiguous VCN admin `/32` sources, global SSH grants and either SSH or
Commander ACCEPT rules after the OCI reject anchor in live or persistent configuration.
The fixture tests run without privilege, so their success is local behavior evidence;
the deployment recipe still needs actual OCI and host-kernel rule observations.

### Source-bound local network policy observations

Through the admitted read-only host route, execute this on each declared host with the
externally selected compiler declaration SHA and a new private receipt destination:

```bash
python tools/runtime/owner_core_network_observations.py \
  --declaration <selected-staging>/declaration.json \
  --expected-declaration-sha256 <approved-declaration-sha256> \
  --host-role <van-trading-core-or-dial-control-or-oracle-admin> \
  --out <new-private-network-receipt.json>
```

The collector refuses a wrong local hostname or declaration before running commands. It
reads exact listeners, local overlay addresses and outgoing route/source selections;
`wg show wg-dial latest-handshakes` and `allowed-ips` expose no private/preshared keys.
It reads complete IPv4/IPv6 iptables-save and nft JSON observations with bounded output
and timeouts. Receipts contain observation/binary/source hashes, not raw peer identifiers,
firewall bodies or stderr. No interface, rule, service or OCI configuration is changed.

`owner_core_firewall_policy.py` evaluates a bounded native rule language: CIDRs, literal
interfaces, TCP port ranges, protocol/state predicates, negation, ordered user-chain
jump/goto/RETURN and ACCEPT/DROP/REJECT. It enumerates every supported source/destination,
source-port and interface equivalence class for protected external NEW traffic, and
checks the declared IPv4 lanes and established replies. World grants, wrong source or
interface, an earlier broad allow/deny, blocked reverse policy, IPv6 grants or a proven
translation of a declared private lane produce FAIL. The oracle-admin DDS overlay
listener remains separate when it shares the new ingress's numeric port.

Supported complete local IPv4/IPv6 observations with empty NAT and no independent nft
hooks can produce `PASS_LOCAL_NETWORK_POLICY_ONLY`. Missing observations, unknown matches,
auxiliary hooks, nonempty nft hooks or unrelated translations remain UNKNOWN rather than
being assumed safe. The CLI exits nonzero for that incomplete policy result. A native
firewall observation can require kernel read privileges; lack of them remains BLOCKED.
OCI VNIC NSGs/security lists, exact peer identity/AllowedIPs admission, governed receipt
scope and actual provider callback routing need independent current observations. The
receipt always keeps overall firewall admission, OCI, owner release, device provisioning
and live E2E unverified; local parser fixtures cannot certify an actual host.

The trading qualifier also uses `check_ufw_commander_scope.py` on one `ufw status verbose`
observation. It requires an observed default incoming deny and ordered Commander 9133
admission only for the configured VCN admin `/32` sources. IPv6/world grants, ranges that
include 9133, wrong sources and earlier denies are rejected. Unknown UFW syntax is RED;
this summary check does not replace the native or OCI policy observations.

## Separate DIAL development projection

The selected topology profile leaves this independent service binding intact. Settings
default to `VAN_DIAL_DEV_ENABLED=false`; an explicitly bound `gateway.env` may enable it
only after the independent DEC-056 product proxy is qualified: base URL
`https://10.77.0.2:8443`, `VAN_DIAL_DEV_TOKEN_FILE`, `VAN_DIAL_DEV_TLS_CA_FILE`,
`VAN_DIAL_DEV_TLS_CLIENT_CERT_FILE`, `VAN_DIAL_DEV_TLS_CLIENT_KEY_FILE` (private key 0600).
The production client requires TLS 1.3 with hostname verification and client identity for
GET and SSE, refuses direct dial-control HTTP or incomplete TLS, and supplies no fallback.
This limited lane never substitutes for Hermes run/capability/callback endpoints or the
phone's HTTPS/WSS connection.

## Hosted feature bindings

[services.env.example](services.env.example) records the additional machine settings for
browser profiles, private delegated control, canonical n8n callbacks and independent
GitHub verification. Merge admitted values into the protected gateway environment;
the template contains no working listener or credential. The owner APK receives its
gateway, browser origin/prefix, trust anchors and device binding through the signed
installer provisioning flow. These machine settings never become app configuration
screens.

Run separate browser producer instances for `public_research` and
`authenticated_owner`, each with its own Chromium profile, debugger and quarantine.
The signed browser prefix admits their mapped signalling routes. Public media and the
private control proxy use separate `browser_stream_producer` scoped credentials;
only the verified control proxy credential fingerprint is mapped to the admitted core
client certificate name. Core task issuance retains its separate `browser` scope.

Use the actual private HTTPS gateway listener for `/v1/automation/worker/step`, bind
the dedicated `automation_worker` credential, and provision the admitted n8n helper
workflows before enabling dispatch. A compiled candidate, stored receipt or configured
URL alone does not establish runtime readiness. GitHub observations similarly require
an allowlisted repository and fresh remote exact-head/run readback.
