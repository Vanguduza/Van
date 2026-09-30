# VAN Trading Core - hardened Muse egress enclave

This package gives Hermes a fixed US/Canada network egress for the official Meta Muse client without putting Muse, Meta credentials, or web content inside VATI's trading authority boundary.

## Security boundary

`van-trading-core` remains the network relay only. A dedicated `van-muse` Linux network namespace contains the WireGuard interface and SOCKS5 process. It has no trading/LAN NIC, no route to OCI metadata, no RFC1918 route, no IPv6 escape, and no inbound public listener. The host exposes the proxy only on `127.0.0.1:17890`; `dial-control` consumes it through the existing SSH path.

The design deliberately does **not** change the trading core's host default route, VATI services, broker routes, UFW public policy, trading credentials, or Commander principals.

## Flow

```text
Hermes browser on dial-control
        |
  SSH local forward
        |
van-trading-core 127.0.0.1:17890
        |
 isolated SOCKS5 / van-muse namespace
        |
 WireGuard only
        |
dedicated static US/Canada exit VPS
        |
      muse.ai
```

Use `socks5h://` so hostname resolution happens behind the tunnel. Keep the Muse browser profile persistent on `dial-control`; do not store Meta credentials on the trading VM.

## Provision an exit

Create a small VPS physically hosted in a Muse-supported US/Canada region with a fixed IPv4. Generate the trading-core client key first:

```bash
sudo install -d -m 0700 /opt/van-muse-egress/secrets
sudo sh -c 'umask 077; wg genkey > /opt/van-muse-egress/secrets/wg-private.key'
sudo wg pubkey < /opt/van-muse-egress/secrets/wg-private.key
```

On the US/Canada VPS, run `MUSE_CLIENT_PUBLIC_KEY=<printed-key> sudo -E bash install-us-ca-exit.sh`. Put the returned server public key and the VPS fixed public IPv4 into `/etc/van-muse-egress.env` on trading core. Provider firewall should expose UDP/51820 only, plus whatever separate SSH administration rule you already require.

## Install on trading core

```bash
sudo install -m 0600 muse-egress.env.example /etc/van-muse-egress.env
sudoedit /etc/van-muse-egress.env
sudo bash install-muse-egress.sh
sudo bash qualify-muse-egress.sh
```

A GREEN qualification proves the bridge is loopback-only, namespace default route is WireGuard, metadata and trading-LAN access are blocked, and the observed internet address exactly matches `MUSE_EXPECTED_EGRESS_IP`.

## Hermes consumption

From `dial-control`, create an SSH local forward using the existing `van-trading-core` alias:

```bash
ssh -N -L 127.0.0.1:17890:127.0.0.1:17890 van-trading-core
```

Point the dedicated persistent Muse browser at `socks5://127.0.0.1:17890`. For automated Chromium/Playwright, ensure proxy-side DNS is used; do not fall back to host DNS. Keep this browser/profile dedicated to Muse so account cookies and location/network history do not mix with unrelated browsing.

## Fail-closed behavior

`van-muse-egress-check` compares the live public IP through SOCKS5 with the configured fixed exit IP. Any mismatch stops `van-muse-bridge.service`, so the browser loses connectivity rather than silently falling back to the Johannesburg host route. A five-minute systemd timer repeats that check.

This only supplies a stable supported-region network path. It does not guarantee Meta account eligibility, and it should not be used to falsify identity, age, billing details, or other account information.
