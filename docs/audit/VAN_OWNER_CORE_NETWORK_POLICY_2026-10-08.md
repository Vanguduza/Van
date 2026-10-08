# Owner-core deployment policy closure — 2026-10-08

Source implementation is complete for this bounded local review. No DIAL host, OCI
security list, provider callback route, owner release or S24 was qualified in this run.

## Confirmed defect and fix

The exact remote VAN base `12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af` contained a trading
qualification check that marked firewall GREEN from active UFW plus any `9133` substring.
The remotely read `deploy/van-trading-core/qualify.sh` SHA256 was
`15fb88c5c27ae9808310151c3326927859fa7023c91d11e6f6f9e6d768cb26fb`; its bytes matched the
local script before this change. A world-open rule, wrong source or blocked rule could
therefore receive the same GREEN detail as the required scoped Commander rule.

The qualifier now evaluates one `ufw status verbose` observation as data through
`tools/runtime/check_ufw_commander_scope.py`. It requires active status, observed incoming
default deny and ordered admission only from the configured VCN admin `/32` sources.
World/IPv6 grants, port ranges covering Commander, wrong sources, earlier blocking rules,
missing observations and unsupported syntax fail RED. This is UFW summary evidence;
the separate OCI image helper and native policy observations remain necessary. The
existing DDS-managed overlay Commander lane is not changed by this VAN source patch.

## Native policy and deployment selectors

`tools/runtime/owner_core_network_observations.py` binds an externally selected compiler
declaration hash and checks the actual local hostname before any probe. It observes exact
listeners, private addresses, source-preserving outgoing routes and fresh WireGuard
handshake metadata; reads `allowed-ips` without private keys; and reads native IPv4/IPv6
and nft rules. Actual reads are bounded by time/output limits. Receipts retain hashes
and verdicts, discard stderr and raw peer/rule bodies, and bind both collector and
policy source hashes. Nothing changes network, service or cloud state.

`tools/runtime/owner_core_firewall_policy.py` checks ordered supported iptables semantics
across every source/destination, source-port and literal-interface equivalence class.
It checks core `10.77.0.4:8443` from oracle-admin `.2`, core `:8787` from dial-control `.1`,
core `.4` to the measured private Hermes port on `.1`, source-preserving hub forwarding,
exact public ingress binding and established replies. It rejects world grants, wrong
sources/interfaces, narrow CIDR/source-port holes, earlier broad rules, blocked reverse
policies, IPv6 openings and proven translation of a declared private lane.

Complete supported local IPv4/IPv6 observations with empty NAT and no independent nft
hooks may PASS local native scope. Unknown rule matches, auxiliary hooks, nonempty nft
hooks, unrelated translation and incomplete observations remain UNKNOWN. OCI VNIC NSG/
security-list policy, exact peer identity/AllowedIPs admission and governed ingress scope
require independent host/provider observations. Overall firewall admission and production
qualification remain false even when the bounded local native policy passes.

The compiler also accepts optional absolute `browser_artifact_providers_file` and
`mtls_machine_client_ca_file` selectors. It emits their environment paths only when
bound and includes them in the generated artifact hash. Preflight observes literal,
regular non-symlink files and private provider configuration permissions without reading
contents. The backend must separately validate actual provider identity, certificate pin,
CA, route and scope. Machine claims reuse the admitted public TLS passthrough with a
separate machine CA; no extra direct private core grant or phone authority is introduced.

## Focused validation

The retained source-bound receipt is
[core-network-provider-selectors-source-final-2026-10-08-receipt.json](validation/core-network-provider-selectors-source-final-2026-10-08-receipt.json).
All 268 captured source inputs were identical before and after execution:

- 41 native policy, UFW and safe collector fixtures passed, including the exact modified
  qualifier branch against controlled UFW command output.
- 71 owner-core profile/preflight fixtures passed, including actual Java Android release
  profile interoperability and optional binding refusal.
- 24 OCI image helper fixtures passed without a live kernel/OCI claim.

Total: **136 passed, 0 skipped, 0 failures**. Bash syntax and Python compilation checks
also passed. Tests exercised only controlled local fixtures and a temporary subprocess
for bounded-output behavior; no DIAL host command or packet probe ran.

## Publication and actual host prerequisites

The cloud's actual OIC manifest has `connections=[]`; no DIAL/Commander host tool,
cloud runtime credential or outbound identity is bound. The supported public MCP
operator route is `https://mcp.dialuniverse.co.zw/mcp/claude-code`, but anonymous initialize
was refused with HTTP 401 and made no tool call. The owner's online Commander report
therefore does not yet create a callable authorized cloud host route.

The shared VAN fixes remain uncommitted. Outside-checkout review helpers prepare an exact
source selection and, only after root approves that selection, can materialize it into
an isolated local bare Git revision while preserving the shared checkout. Four synthetic
Git fixtures verify exact file modes/deletions, clean clone bytes, tamper refusal and
source preservation. No actual VAN commit or push has been executed. A local immutable
source revision, cloud-draft publication and successful source fixtures do not establish
remote source publication, admitted deployment, real signing keys/PKI, provider execution,
firewall admission or phone acceptance.
