# VAN on van-trading-core

## Current topology

The owner directs all VAN runtime components to van-trading-core. Its gateway owns
the phone's direct mTLS HTTPS and WebSocket endpoint. Hermes profile van and its
owner-runtime MCP are colocated on core. Oracle Admin is excluded and stays stopped.
dial-control hosts development and direct Artemis testing.

| Connection | Binding |
|---|---|
| Owner phone → VAN gateway | Observed core VNIC IPv4 and dedicated public HTTPS/WSS port |
| VAN Hermes → gateway owner-runtime MCP | http://127.0.0.1:8787, separate scoped token file |
| VAN gateway → VAN Hermes API | http://127.0.0.1:<measured port>, separate runtime credential |
| Development and administration | Existing private Commander/DIAL routes |
| Physical handset testing | Direct Artemis after pre-handset qualification |

There is no VAN HAProxy forwarding configuration or inter-host Hermes relay.
The v1 three-host profile belongs to the immutable earlier candidate and historical
receipts. New builds require integer schema_version 2, release profile version 2,
and topology CORE_ONLY_V2.

## Authority and real bindings

The proposed ingress capability is VAN_OWNER_CORE_DIRECT_MTLS_V1. This name, an
example profile, compiler output, or passing synthetic test is not admission.
The bounded DDS recipe must validate the exact source SHA, profile digest, host, phase,
expiry, control epoch and fence through the genuine authority class. Current source
changes do not admit, install or deploy that recipe.

Keep profile.example.json unbound. Populate a separate protected operator profile
with observed values and an actual scoped ingress receipt. Do not invent a public URL,
OCI namespace, provider target, APK signer, attestation roots, identities or receipts.
The observed core VNIC is not by itself proof of a public route. Observe its public
IPv4, any DNS binding, OCI NSG/security lists and server SAN before producing the
release profile. IPv6 literals are refused by this IPv4 capability.

The selected profile requires all three host roles to be van-trading-core; the
actual public HTTPS root with explicit dedicated port; the observed VNIC address
and interface; a local Hermes API port; the existing public device CA; a genuine
ingress receipt; and literal protected file selectors for the connectivity signer,
scoped runtime token, mTLS directory, persistent database, Commander token and CA.
Optional provider/machine-client CA selectors require actual bindings.

Public ports 8787 and 9133, overlay ingress binds, wildcard listeners, cross-host
runtime URLs, credentials in URLs and broad production loopback overrides are refused.

## Preparation

Run tools/runtime/prepare_owner_core_deployment.py with --profile pointing to the
protected profile and --output pointing to a new output directory in the exact selected
checkout. The compiler validates before emitting artifacts and reads only the public
CA needed by Android. Private selectors remain paths; optional provider files are
not copied.

Artifacts are android-owner-core.properties, owner-core.env, hermes-runtime.env,
van-gateway-resource-limits.conf and declaration.json. The declaration reports
PREPARED_NOT_DEPLOYED, lists only core in runtime_hosts, and keeps deployment, authority
and live qualification false.

VAN_ALLOW_LOOPBACK_IN_PRODUCTION=false remains mandatory. Runtime Settings permits
the local Hermes URL only when the exact CORE_ONLY_V2 mTLS/public/local bindings pass.
A public loopback URL still fails.

## Preserve existing identities and owner state

The migrated existing identity/state must be present on core before installation.
Never initialize an empty replacement owner database, regenerate the device CA,
replace the connectivity signer, or let an installer fill absent encryption/ingress
keys with new defaults.

The admitted runner must back up and migrate the existing VAN profile, protected
provider credentials, gateway/Google encryption keys, device records, connectivity
key, mTLS certificates and persistent databases over the private administration route.
Do not export secret values to logs/receipts. Preserve ownership/modes and verify
identities and persisted state independently. Use a consistent SQLite backup for an
active database; retain real source/destination digests, readbacks and rollback ID.
Quiesce only the required VAN writers and preserve trading.

The profile installer does not install the Hermes binary and excludes secrets.
Use the real pinned product runtime and dependencies on core.
tools/hermes/register_owner_runtime_mcp.sh requires the local gateway URL and separate
scoped token file and preserves sibling MCP entries. Product Hermes remains VAN's
runtime. Development of this setup uses Commander/DIAL directly.

## Install and qualify through the admitted recipe

After admission, check exact clean source, real profile and authority envelope,
core identity/architecture, fresh private admin reachability, trading placement
admission and actual memory headroom before effects. The gateway drop-in caps memory
at 1 GiB and CPU at one core-equivalent, with a 5 GiB available-memory preflight floor.
Placement governance can demand more.

Use the existing compiler, preflight_owner_core.py, gateway installer, qualification
and rollback tools under the bounded recipe. The profile wins after ordinary gateway,
Google and trading environment files. Ambient shell secrets cannot replace missing
protected unit-file bindings. Do not restart trading or add public Commander/ADB/trading
listeners.

Qualify actual direct public TLS, CA/SAN identity, no-client-certificate HTTPS/WSS
refusals, local runtime authentication/scopes, sessions, browser/automation canaries,
protected Oracle/VEKL provider operations and independent effects. UNKNOWN provider
writes remain UNKNOWN and must not be resent. Provider capability names do not make
the stopped Oracle Admin VM a VAN prerequisite.

## Network evidence

owner_core_network_observations.py binds the declaration digest and exact core host,
observes its selected VNIC, exact listeners/admin overlay facts, and collects bounded
native firewall evidence without private WireGuard keys. Current declarations refuse
runtime collection on Oracle Admin or dial-control.

owner_core_firewall_policy.py evaluates supported ordered iptables/ip6tables semantics.
Wrong interfaces, cross-host runtime admission, forwarding of these ports, public
runtime listeners and unadmitted IPv6 NEW admission fail. Native local translation
touching a runtime lane fails. Nonempty independent nft hooks, incomplete exports
and unsupported semantics remain UNKNOWN pending independent evaluation.
Historical v1 semantics remain for old receipt interpretation and regression.

A local native-policy PASS cannot qualify OCI policy, provider routes, signing or
handset use. Observe applicable VNIC NSGs/security lists, routing, IPv4, IPv6 and NAT.
An address is not proof of WireGuard peer identity; an IPv6 VNC listener is not proof
of public exposure.

## Release and direct Artemis

The actual Java release validator and tools/release/owner_release.py require version-2
core-only roles, public route, one current pinned CA and matching fingerprint.
Historical debug fixtures cannot serve as release fallback. Build the real owner-signed
com.dial.van APK from existing signing/connectivity trust bindings. Verify APK bytes,
signer, ABI, compiled route/trust, packet lifetime and installed provenance.

No app UI exposes host, token or CA setup. Provision the signed packet through the
authorized installer and existing device identity. Real OS/biometric consent and
private speaker enrollment remain required.

Run the current applicable 826-case Artemis matrix directly through DIAL/Commander
only after pre-handset qualification, on S24 RFCX2054F5W / SM_S928B, with one measured
private Windows USB/ADB bridge. Join native evidence to canonical actions and independent
effects. Until then report physical tests as NOT_RUN.

## Rollback and receipts

Retain actual prior deployment, protected-state backups, interpreter/source hashes
and migration readbacks before switching services. Rollback validates the actual prior
deployment ID and restores only affected VAN resources. Never broaden host scope or
replay consumed approvals.

Retain the earlier candidate/receipts unchanged. Publish the core-only revision under
a new branch/SHA with fresh source/host/release receipts. Report synthetic source
contracts separately from deployment and physical qualification.
