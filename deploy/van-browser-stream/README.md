# van-browser-stream — deployment package

Rev 1.5 §13. The dedicated **Browser Stream Host**: the machine that runs the Chromium the
owner sees, encodes it, and streams it to the phone — while Stagehand and Browser Harness
keep running on the private Trading Core and control that same Chromium over a narrow mTLS
API.

Nothing in this directory has ever been run. There is no host. Everything here is the
package that would install one, and `qualify.sh` is what decides whether an installed one is
actually what it claims to be. Until that script has returned green on a real machine, every
Remote Browser row that depends on a host stays `BLOCKED` in
`docs/project-state/REMOTE_BROWSER_IMPLEMENTATION_MATRIX.json` (RB-002, RB-010).

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
| Chromium | `van-browser-chromium.service` | **loopback only** | `--remote-debugging-address=127.0.0.1`. The debugger is the reason this host is fenced. |
| Browser Control Agent | `van-browser-control-agent.service` | private VCN, mTLS | `services/browser_control_agent`; the only cross-host bridge to Chromium |
| Stream runtime | `van-browser-stream.service` | public | signalling + WebRTC; verifies `BrowserStreamGrant` (ES256, `kid` pinned) |
| Profile volume | — | — | encrypted, mounted only here (§13.5 option A) |

## Install

```bash
sudo bash deploy/van-browser-stream/bootstrap.sh --dry-run   # print the plan, change nothing
sudo bash deploy/van-browser-stream/bootstrap.sh
sudo bash deploy/van-browser-stream/qualify.sh               # JSON report; exit 0 only when every check is GREEN
```

`qualify.sh` is the gate, not `bootstrap.sh`. A bootstrap that completes proves the files
were written; it proves nothing about whether the debugger is fenced or the agent refuses
an unknown caller, and those are the two things that matter on this host.

## What qualify.sh actually checks

It is deliberately short and every check is a refusal that must happen:

1. **CDP is not reachable off loopback.** It connects to the debugging port on every
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

## What this package does not do

It does not provision the VM, open a firewall, or obtain a TLS certificate for the public
interface. Those are the owner's deployment decisions and are recorded as external gates in
`docs/EXTERNAL_GATES.md` rather than guessed at here.
