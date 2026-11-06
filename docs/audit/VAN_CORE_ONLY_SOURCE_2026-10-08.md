# VAN core-only source revision — 2026-10-08

The owner's superseding instruction excludes Oracle Admin and places all VAN runtime
components on van-trading-core. Development uses Commander/DIAL MCP directly; physical
testing uses direct Artemis after prerequisites pass. The earlier immutable candidate
652ef3f38717c808f57fcbc97f92d1030f9ab4a8 and r8 manifest remain unchanged.

## Source changes

The version-2 compiler/release profile places gateway, phone ingress and VAN Hermes on
core; uses an observed IPv4 VNIC and direct mTLS HTTPS/WSS; and uses local gateway and
Hermes API bindings. It emits no HAProxy passthrough or inter-host runtime relay.
Production runtime settings allow local Hermes only under the narrow CORE_ONLY_V2
binding checks with the broad loopback override false. Public loopback, wildcard/
overlay ingress, cross-host runtime URLs, unsafe interfaces, public runtime/Commander
ports and unadmitted IPv6 literals are refused.

The firewall evaluator/collector handle the three direct/local core lanes, reject
cross-host runtime admission and forwarding, and retain UNKNOWN for incomplete native
exports or nonempty independent nft rules. Historical v1 semantics remain solely for
old observations/regression. Java target validation, release packet bindings,
preflight and pre-handset host acceptance now require core-only roles.

## Actual source verification

The affected source tests have 277 unique current passes, zero current failures and
one optional actual AGP signing-guard check skipped. The initial bounded run had
270 passes, seven failures and one skip. The seven failures exposed old topology
checks in pre_phone_host_acceptance.py; the final changed-module run has 13 passes.
Counts deduplicate by actual JUnit case identity and do not include earlier DDS
planning tests, unchanged full VAN suites or physical handset cases.

The prior manifest SHA256 remains
c55031c4be0cc6da94b86d103066b4b683d71be3c6d779a56bc3520fffb7b61e.
The new production manifest is
docs/audit/validation/van-production-source-freeze-core-only-2026-10-08-r1.json.
Its base_commit intentionally identifies the prior candidate. A separate final
commit/tree/source readback receipt binds this revision.

## Host observations and unresolved acceptance

A fresh signed read observed van-trading-core running and privately reachable,
aarch64 host identity, enp0s6 10.0.1.233, and about 7.75 GiB available memory.
A separate OCI VNIC read observed public IPv4 84.12.76.70 mapped to that same VNIC.
Neither observation qualifies the direct VAN public endpoint or OCI/native firewall.
No new runtime listener or deployment was installed. The checked standard core VAN
profile/configuration paths and product runtime binary were absent.

The DDS owner-core recipe remains a disabled source draft. The actual loaded schema
still admits only existing unrelated recipes. Full phase executors, signed capability
producer, actual DDS Feature/FRC/Unit/VEKL and forensic pack, independent reviews,
source admission, installed helper/broker hashes and rediscovered loaded schema are
pending. No raw administration is used to bypass that boundary.

Existing owner PKI/state/provider credentials must be migrated consistently to core
before installation, preserving identities and trading. The real owner release signer/
keystore, actual provider target/namespace and qualification, signed provisioning
packet and one private Windows USB/ADB bridge are not qualified by these source tests.
S24 RFCX2054F5W / SM_S928B, com.dial.van: NOT_RUN, zero of 826 executed.
Oracle Admin stays stopped and is not a deployment prerequisite.
