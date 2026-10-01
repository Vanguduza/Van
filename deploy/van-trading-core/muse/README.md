# VAN Trading Core — hardened Meta Muse enclave

This module gives VAN/Hermes a persistent Muse browser on the existing ARM64 Trading Core while keeping Muse outside VATI authority and forcing all browser Internet traffic through one fixed US/Canada egress.

## Canonical execution path

```text
Hermes
  |
  v
VAN Browser Gateway / BrowserSubagentRunner
  |
  +--> Browser Harness 0.1.13        deterministic actuator + verifier
  |
  +--> Stagehand 4.1.0               semantic/deep worker
  |
  +--> Jev fast lane                  staged separately; same authority envelope
  |
  v
127.0.0.1:17922  (host-loopback CDP handoff)
  |
  v
gVisor / Systrap Muse sandbox
  |
  +-- root supervisor                lifecycle only; no shell/exec endpoint
  |
  +-- Chromium uid 10001             retains Chromium's own sandbox
  |
  +-- persistent muse_owner profile
  |
  v
172.31.77.1:17892  (sandbox-only SOCKS bridge)
  |
  v
127.0.0.1:17890   (hardened Trading Core egress bridge)
  |
  v
van-muse netns -> wg-muse only
  |
  v
fixed US/Canada exit
  |
  v
muse.ai
```

The former design with a Muse browser on dial-control and an SSH SOCKS hop into Trading Core was removed from this branch. Trading Core's gVisor sandbox is the single Muse browser runtime.

## Authority boundary

Hermes has full browser-operational control through the existing Browser Gateway, Harness, Stagehand and the sandbox supervisor. It does **not** receive Docker-group access or host root.

The root supervisor exists only inside the gVisor sandbox. It can start, stop and restart Chromium. Chromium itself runs as uid 10001 and is never launched with `--no-sandbox`.

There is deliberately no supervisor endpoint for:
- shell;
- arbitrary exec;
- host filesystem access;
- Docker access;
- VATI commands;
- broker access;
- authority or mandate mutation.

## Sandbox isolation

The sandbox uses:
- gVisor `runsc`, pinned to `release-20260928.0`;
- Systrap, so the ARM64 OCI VM does not require nested KVM;
- an internal-only Docker bridge;
- read-only container root filesystem;
- only three bind mounts: Muse profile, downloads, and the control token;
- no Docker socket;
- no privileged mode;
- Linux capabilities dropped except `SETUID`, `SETGID`, and `KILL` for the in-sandbox supervisor;
- CPU, memory, PID and file-descriptor limits;
- no swap beyond the memory limit;
- an increased OOM score so the Muse sandbox is reclaimed before trading-critical workloads under memory pressure.

Default resource ceiling:

```text
CPU                  0.75 OCPU
memory max           4 GiB
memory reservation   2 GiB
PIDs                  512
profile               8 GiB
downloads             2 GiB
```

VATI remains outside these limits and retains resource precedence.

## Network fail-closed properties

The sandbox Docker network is created with `--internal`.

A host nftables policy additionally proves:
- packets from the sandbox cannot be forwarded;
- the sandbox may reach the host only on its dedicated SOCKS port;
- host processes may reach sandbox CDP only through the dedicated control principal;
- sandbox supervisor control is not publicly published.

The live qualifier explicitly attempts and requires failure for:
- direct `1.1.1.1:443`;
- cloud metadata `169.254.169.254:80`;
- VAN Trading Core control port `10.0.1.233:9133`.

It then performs a SOCKS5 handshake through the admitted proxy to prove there is exactly one usable network path.

The upstream egress layer separately verifies:
- WireGuard-only namespace default route;
- fixed public egress IP;
- expected `US` or `CA` country code;
- no IPv6 fallback;
- no private/link-local destination access;
- kill-switch behavior when `wg-muse` is taken down.

An identity mismatch stops the egress bridge.

## Existing VAN browser reuse

`muse_owner` is an admitted managed browser profile.

The existing Browser Harness now supports one pinned external-CDP mapping:

```text
muse_owner=http://127.0.0.1:17922
```

For that profile only, Harness attaches to the gVisor Chromium rather than starting a native Chromium process.

Stagehand already consumes the same `cdp-endpoint.json` handoff, so it is reused unchanged.

Other profiles such as `public_research` and `authenticated_owner` continue using the existing browser runtime.

## Persistent state

Only these browser-owned paths survive sandbox recreation:

```text
/var/lib/van-muse-sandbox/profile
/var/lib/van-muse-sandbox/downloads
```

The browser root filesystem and temporary process state are disposable. Meta cookies/session material stay inside the profile and are never exported through Browser Gateway evidence.

## Installation sequence

### 1. Configure hardened US/Canada egress

Stage the Trading Core side:

```bash
sudo install -m 0600 muse-egress.env.example /etc/van-muse-egress.env
sudo bash install-muse-egress.sh
```

The first run generates the WireGuard client key and refuses to enable placeholder peer values.

Provision a dedicated static US/Canada exit with:

```bash
sudo env \
  MUSE_CLIENT_PUBLIC_KEY='<client-public-key>' \
  MUSE_EXIT_EXPECTED_COUNTRY=US \
  bash install-us-ca-exit.sh
```

Use `CA` for Canada.

Place the returned peer key, endpoint, expected IP and country in `/etc/van-muse-egress.env`, then rerun:

```bash
sudo bash install-muse-egress.sh
sudo qualify-muse-egress
```

### 2. Install the gVisor Muse sandbox

After the existing Browser Harness/Stagehand runtime exists:

```bash
sudo bash sandbox/install-muse-sandbox.sh
```

The installer:
1. verifies ARM64;
2. downloads the exact pinned gVisor archive and verifies SHA-256;
3. merges only the `runsc-muse` Docker runtime entry;
4. validates `daemon.json`;
5. reloads Docker rather than restarting it;
6. rolls the Docker config back if runtime registration fails;
7. creates the internal-only Muse network;
8. builds and records an immutable local image ID;
9. installs the systemd/network policies;
10. starts the sandbox only if the US/Canada egress is already GREEN;
11. runs the adversarial qualification.

## Qualification

```bash
sudo qualify-muse-egress
sudo qualify-muse-sandbox
sudo env VAN_EXPECTED_REPOSITORY_SHA=<exact-sha> bash deploy/van-trading-core/qualify.sh
```

A configured Muse runtime is not accepted unless all required sandbox and egress checks are GREEN.

## Security rule

Muse, Stagehand, Jev, Browser Harness and page content are all subordinate to Hermes and the VAN Browser Gateway.

They cannot:
- create owner authority;
- increase a task action class;
- extend their own step/deadline/domain budget;
- place, modify or cancel a trade;
- access broker credentials;
- access VATI control endpoints;
- perform a payment;
- certify their own success.

A worker result is a claim until the existing independent browser evidence path verifies it.

The egress mechanism provides deterministic network isolation and a stable regional exit. It does not falsify age, identity, billing or other account information and does not guarantee Meta account eligibility.
