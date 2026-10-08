# van-browser-stream — deployment package

Rev 1.5 §13. The dedicated **Browser Stream Host**: the machine that runs the Chromium the
owner sees, encodes it, and streams it to the phone — while Stagehand and Browser Harness
keep running on the private Trading Core and control that same Chromium over a narrow mTLS
API.

No live host or physical Android device has been qualified by this package. The source
implements the native runtime and the installer; `qualify.sh` independently decides whether
an installed host meets its requirements. Remote Browser rows requiring that host remain
blocked until genuine host and core canary observations exist.

The runtime entrypoints fail closed when dependencies, TLS, protected producer credentials,
profile bindings or confined staging are missing. `--check-runtime` checks dependencies
without starting a listener; bootstrap uses it before users, profile changes or service
installation, including in dry runs. Certificates and source hashes alone never count as
runtime or Android readiness.

## Why the host is dual-homed

```text
        owner's S24
             │  HTTPS/WSS signalling, WebRTC media
             ▼
  ┌──────────────────────────────────────────┐
  │  BROWSER STREAM HOST                      │
  │                                           │
  │  public interface                         │
  │    signalling, ICE, media                 │
  │                                           │
  │  private VCN interface                    │
  │    van-browser-control-agent (mTLS)       │
  │                                           │
  │  loopback only                            │
  │    Chromium, CDP, capture, encoder        │
  └───────────────┬───────────────────────────┘
                  │ private VCN, narrow mTLS
                  ▼
  ┌──────────────────────────────────────────┐
  │  PRIVATE TRADING CORE                     │
  │  Stagehand, Browser Harness, profiles     │
  └──────────────────────────────────────────┘
```

Four requirements meet on this host at once: it must take owner media from the internet, it
must expose **no public CDP**, the existing private Browser Fabric must be able to drive the
same visible Chromium, and Stagehand's authority must not move onto a public media host.
Dual-homing is what satisfies all four; a single-homed host fails at least one.

## What is installed

| Component | Unit | Interface | Notes |
|---|---|---|---|
| Exact-IP egress proxy | `van-browser-egress-proxy.service` | **loopback only** | Public HTTP(S) only; rejects any hostname with a private/reserved DNS answer and connects to the exact admitted IP. |
| Chromium | `van-browser-chromium.service` | **loopback only** | `--remote-debugging-address=127.0.0.1`; all HTTP(S) is forced through the exact-IP proxy; QUIC and non-proxied WebRTC UDP are disabled. |
| Browser Control Agent | `van-browser-control-agent.service` | private VCN, mTLS | `services/browser_control_agent`; the only cross-host bridge to Chromium |
| Stream runtime | `van-browser-stream.service` | public | signalling + WebRTC; verifies `BrowserStreamGrant` (ES256, `kid` pinned) |
| Profile volume | — | — | encrypted, mounted only here (§13.5 option A) |

## Install

Production uses two isolated stacks: `public_research` (`public`) and
`authenticated_owner` (`owner`). Prepare a private copy of `profiles.example.json` with
the observed listener addresses, encrypted device, pinned Chromium/nginx executable
selectors and SHA-256 hashes, and independently provisioned TLS/credential selectors.
The committed example is deliberately unbound and refuses installation.

```bash
python deploy/van-browser-stream/prepare_profiles.py \
  --profile <bound-browser-profiles.json> --output <private-review-directory>
sudo bash deploy/van-browser-stream/bootstrap.sh \
  --profile <bound-browser-profiles.json> --dry-run
sudo bash deploy/van-browser-stream/bootstrap.sh --profile <bound-browser-profiles.json>
```

Preparation writes per-profile Chromium/control/stream environment files, instance units,
one fixed-route media TLS ingress configuration, a core binding fragment and hash-bound
`PREPARED_NOT_INSTALLED` declaration. Dry-run reads no credential material and starts no
listener. Actual installation requires the already mounted, independently admitted LUKS
volume `/dev/mapper/van-browser-profiles`; it never formats a device or silently migrates
browser state. Existing profile state must be migrated under its exclusive lease, or a
new profile must be separately admitted before acceptance.

Each profile has its own `van-browser-{public|owner}`, `van-control-{public|owner}` and
`van-stream-{public|owner}` Unix users, transfer group, loopback CDP port, private control
port, native HTTPS stream port, Chromium profile path and encrypted quarantine. Profile
parents permit traversal without directory listing; each profile remains mode 0700.
Role PKI directories are separately owned and mode 0700, private keys/tokens mode 0600;
root-only environment files are read by systemd. The installer verifies the actual four
distinct token hashes and independent matching broker client certificates/private keys,
including client-auth purpose and validity. It refuses privileged existing group
memberships. A dedicated nftables output table permits each CDP port only to root and
that profile's three Unix identities, then rejects other local UIDs. This prevents the
public stack from connecting to owner Chromium through a shared loopback network.
The dedicated table is restored at boot and never flushes other firewall tables.

The signed phone origin remains one explicit public HTTPS `/rtc` base. The generated
nginx media ingress exposes only `/rtc/public`, `/rtc/owner`, their download/upload routes
and explicit clipboard actions, returning 404 for other paths. It verifies both native
HTTPS peers' CA and SAN using TLS 1.3, disables request logging and buffering, and confines
any transient body staging to a separate encrypted bind mount owned by
`van-browser-ingress`. This media proxy does not alter gateway device TLS passthrough,
private control mTLS, or claim to authenticate a phone from forwarded headers. Actual
signed one-use stream/transfer grants and producer authority remain enforced by native
runtime and core. Proxy binary capability, public TLS/DNS/SAN, firewall/ingress admission
and actual reachability still require the host recipe and live evidence.

The generated `gateway-browser-profile-bindings.env` binds the two signed signal URLs,
the exact per-profile private mTLS core clients and a CONTROL-only proxy allowlist.
`VAN_BROWSER_CONTROL_PROFILE_CLIENTS` selects the persisted profile's address/port/SAN,
CA/client identity, caller common name and CONTROL fingerprint. Both client objects use
the same configured canonical caller CN. Neither STREAM fingerprint enters the proxy
allowlist; all four credentials have only `browser_stream_producer` consumer scope on
the core, with independent issuer authority. Apply this fragment through the admitted core
configuration recipe, preserving existing service bindings and owner state.

Installed instance units are `van-browser-chromium@{public|owner}.service`,
`van-browser-control-agent@{public|owner}.service`, `van-browser-stream@{public|owner}.service`
and `van-browser-transfer-stage@{public|owner}.service`; shared units install UID fencing,
encrypted ingress staging and fixed media routing. Installation refuses active stacks,
disables quiesced legacy singleton units, validates nginx configuration and writes units
without starting or enabling any listener. The admitted recipe must qualify both stacks
and the shared ingress before recording readiness.

Run qualification separately for each selected instance, using that profile's actual
ports/bind and a current admitted core client certificate/key. The qualifier does not
source a secret-bearing env file automatically:

```bash
sudo env VAN_BROWSER_INSTANCE=public \
  VAN_BROWSER_CONTROL_BIND=<observed-private-bind> \
  VAN_BROWSER_CONTROL_PORT=<public-profile-control-port> \
  VAN_BROWSER_CDP_PORT=<public-profile-cdp-port> \
  VAN_BROWSER_STREAM_PORT=<public-profile-native-stream-port> \
  VAN_BROWSER_PKI_DIR=/etc/van-browser-stream/profiles/public/control-pki \
  VAN_BROWSER_QUALIFY_CLIENT_CERT=<admitted-public-profile-core-client-cert> \
  VAN_BROWSER_QUALIFY_CLIENT_KEY=<admitted-public-profile-core-client-key> \
  bash deploy/van-browser-stream/qualify.sh
```

Repeat for `owner` with its ports, PKI and admitted identity. A successful admitted-client
handshake must establish server reachability/CA/SAN before anonymous/foreign-certificate
denials can qualify. Network or trust failures remain UNKNOWN. Core canaries must also
prove profile routing, cross-profile/UID denial, stream delivery, transfer authority and
sealed-file cleanup; installation and source tests never establish these observations.

`pki/make-stream-pki.sh --instance public|owner` can prepare the independent private
control CA/server/client material on its admitted PKI host. Bind the explicit private
control address and PKI directory; existing CAs are preserved. Before role users exist,
generated material remains root-owned for the installer. CA keys and core client private
keys never belong in a stream role's readable namespace.

The old single-profile package remains a development fixture. Real use requires explicit
`--legacy-single-profile`; it cannot qualify two production profiles. The historical
single-profile commands below describe that fixture:

```bash
sudo bash deploy/van-browser-stream/bootstrap.sh --dry-run   # print the plan, change nothing
sudo bash deploy/van-browser-stream/bootstrap.sh --legacy-single-profile
sudo bash deploy/van-browser-stream/qualify.sh               # JSON report; exit 0 only when every check is GREEN
```

`qualify.sh` is the gate, not `bootstrap.sh`. A bootstrap that completes proves the files
were written; it proves nothing about whether the debugger is fenced or the agent refuses
an unknown caller, and those are the two things that matter on this host.

## What qualify.sh actually checks

It is deliberately short and every check is a refusal that must happen:

1. **CDP and the egress proxy are not reachable off loopback.** The proxy must also
   reject a loopback/private destination, and live Chromium must show the proxy/no-bypass,
   QUIC-disable and non-proxied-WebRTC-disable flags. **CDP is not reachable off loopback.** It connects to the debugging port on every
   non-loopback address the host has. Any answer is a `RED`. This is RB-117 and it is first
   because it is the one that turns this host into a remote shell.
2. **The control agent refuses an unknown client certificate.** A connection with no client
   certificate, and one signed by a different CA, must both be rejected at the TLS layer.
3. **The control agent refuses a known caller with the wrong scope.** mTLS says who; it does
   not say what they may do.
4. **The public interface serves no CDP.** The stream port answers; the debugging port does
   not exist there.
5. **The profile volume is mounted and encrypted**, and Trading Core holds no copy of it.
6. **Chromium is running as an unprivileged user** with no Docker socket in its namespace.

Each check prints its own evidence, and the report records `UNKNOWN` rather than `GREEN`
for anything it could not test. A qualification script that reports success for a check it
skipped is worse than no script.

## What the host needs from this repository

`bootstrap.sh` copies `services/` onto the host, and the input router inside it imports
`van_gateway.browser.input_protocol` — the wire format's one Python implementation. That
module has to be on the host's path too.

It is imported rather than vendored deliberately. The format already exists twice, in
Python and in Kotlin, and keeping those two in step needed a shared vectors file and two
contract tests. A third copy on the Stream Host would be a third thing to keep in step,
and the symptom of failing would be a tap landing somewhere the owner did not touch.

## PKI

`pki/make-stream-pki.sh` issues a private CA, a server certificate for the control agent on
its VCN address, and one client certificate per calling service. The names in those client
certificates are the identities the agent authorises against — there is no other identity
source, and the agent never reads a caller name from a request body.

These credentials are independent of the owner device key, the device HMAC, the
`BrowserStreamGrant` and the Gateway's internal control token. That separation is the point
of §13.3: compromising the service-to-service path must not yield owner authority, and
compromising owner authority must not yield the ability to call this agent.

## Profile storage (§13.5)

Option **A** is chosen: an encrypted volume attached only to this host, with Trading Core
holding metadata and leases but no profile bytes.

The reason is §13.5's own constraint — Chromium executes here, so the bytes must be here —
combined with the fact that profile *authority* stays on Trading Core. Option B (a network
volume with an exclusive lease) puts the owner's authenticated cookies on a wire between two
hosts, and the lease enforcement becomes the thing standing between two Chromiums writing
the same profile. A is fewer moving parts holding the same secret.

## Certifying the host, and what VAN refuses until you do

`qualify.sh` runs on the host and checks it against §13. It is a self-check, and the
Gateway never sees it.

The Gateway's own position is separate and stricter. `browser.interactive.session` — the
capability an interactive browser session binds a Mission under — is declared
`EXTERNAL_RUNTIME` against the probe `browser_stream_host`, so until a canary has measured
this host from the Gateway's side, **a browser session opened for a Mission is refused**,
with `NO_READINESS_EVIDENCE:browser_stream_host` naming the missing thing. Manual browsing
is unaffected; §23.2 says opening a web page is not a unit of agent work, and it needs no
capability.

That is the designed state rather than a gap. Recording that a Mission used a remote
browser, when no remote browser has ever been proven to exist, is the kind of unearned
claim the readiness ladder exists to prevent.

Three canaries clear it, run from the Gateway host against this one:

```
python tools/certification/certify_browser_stream_host.py --canary mtls   --host 10.0.1.240 ...
python tools/certification/certify_browser_stream_host.py --canary observe --host 10.0.1.240 ...
python tools/certification/certify_browser_stream_host.py --canary fence  --host 10.0.1.240 ...
```

* **mtls** — a client certificate from this PKI completes the handshake, *and* one signed
  by a foreign CA does not. Both halves, because a listener that accepts is not a listener
  that refuses, and the second is what §13.3 is about. It needs
  `pki/make-stream-pki.sh --with-foreign-test-cert` to have been run;
* **observe** — a read-only call over the wire protocol answers, and a raw CDP method on
  the same connection is refused. This is the canary that records the readiness evidence,
  because an open port is not a working control agent;
* **fence** — a call naming a superseded control generation is refused. The Gateway's own
  tests prove it *moves* the generation; only this proves the host honours it, and a host
  that does not is one where "Take over" changes a number in a database while the agent
  keeps clicking.

Without a live host all three exit non-zero and record nothing, so the gate stays
`PENDING_LIVE`.

## What this package does not do

It does not provision the VM, open a firewall, or obtain a TLS certificate for the public
interface. Those are the owner's deployment decisions and are recorded as external gates in
`docs/EXTERNAL_GATES.md` rather than guessed at here.

## Native source runtime, implemented 2026-10-07

The source now contains a real loopback CDP discovery/attachment/multiplex transport,
private newline-framed mTLS control listener and aiortc HTTPS `/rtc` signalling/video/input
runtime. `--check-runtime` checks pinned distribution metadata without opening sockets or
reading credentials. The bootstrap uses that mode, including during `--dry-run`.

Install `requirements.lock` with `--require-hashes`. The checked artifact hashes support
CPython 3.12 on Linux x86_64; other platforms require independently downloaded artifact
hashes. `runtime-dependency-receipt.json` records downloads, not a live host installation.

The stream host binds one configured Chromium profile alias and verifies ES256 stream
grants with a public key. It redeems them once against the private typed producer API,
which binds the actual machine credential to current session/profile/control authority.
Its bearer grant identifies the grant subject; the runtime never claims independent
phone TLS authentication from that subject. Owner input is bounded binary protocol v1,
with channel/sequence/pointer checks and fresh broker authorization before every CDP effect.
Navigation kinds 10–15 use fixed navigate/search/history/reload/stop conversations.

Every SDP answer and ordered `browser-state` record binds exact session, control generation,
viewport dimensions/revision and `media_epoch` (the real producer ID). The first actual
captured image emits a `viewport.frame` marker after a typed observation. Android reconnects
on changed geometry/authority and independently requires a decoded frame plus the marker
before acknowledging that exact epoch. Stream state never proves a browser task completed.

The private control listener derives caller identity exclusively from the verified TLS
client certificate. Its scoped credential attests that name to the durable core task-grant
resolver; the configured proxy fingerprint/CN allowlist, target/profile/mission relation,
current lease generation, task domains and consumed step budget remain authoritative.
No request-supplied caller, scope, budget, lease object or raw CDP operation is admitted.

The owner file plane uses `/rtc/files/download/{id}`, `/rtc/files/upload/{chooser_id}` and
`/rtc/clipboard/{copy|paste}`. Each call uses its own broker-issued one-use transfer grant,
`X-Van-Producer-Session`, current owner/frame/target fence, and canonical size/hash metadata.
Files stay on the encrypted profile filesystem through a bind mount exposing only the
quarantine to a separate `van-stream` user. Downloads are GUID-named, bounded to 64 MiB,
classified from actual bytes and sealed under stream ownership before approval. Reconnects
retain sealed artifacts for at most one day; tmpfiles cleans expired staging. Broker-issued
deletions unlink only canonical sealed artifacts and acknowledge cleanup after unlink.
Uploads use real intercepted chooser backend-node identity, single-file owner selection,
hash/size checks, fixed `DOM.setFileInputFiles` and finite cleanup. No path or node ID comes
from Android. Clipboard buttons require explicit one-action grants; automatic sync is off.

Privileged native CDP conversations for fixed quarantine setup, chooser interception and
bounded selection extraction are internal producer code. They do not extend the automation
agent's public method allowlist or admit scripts/paths/method names from callers.

This source implementation does not establish a running deployment, public reachability,
TURN connectivity, provider readiness or physical Android acceptance. Host `qualify.sh`,
core canaries and the separate Artemis acceptance phase still require actual observations.
