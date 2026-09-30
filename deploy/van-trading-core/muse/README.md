# VAN Trading Core — hardened Meta Muse egress enclave

This module gives Hermes/VAN a persistent US or Canadian network identity for the official Meta Muse client while keeping Meta credentials, web content, and the Muse browser **outside VATI's trading authority boundary**.

## Canonical boundary

```text
Muse browser on dial-control / Hermes
        |
        | local SOCKS5 127.0.0.1:17891
        v
persistent SSH local-forward
        |
        v
van-trading-core 127.0.0.1:17890
        |
        v
van-muse network namespace
  ├─ Dante SOCKS5 169.254.77.2:1080
  ├─ no trading/LAN NIC
  ├─ no IPv6 default path
  ├─ private/link-local destinations blocked
  └─ default route = wg-muse only
        |
        v
WireGuard
        |
        v
dedicated static US/Canada exit VPS
        |
        v
muse.ai / Meta
```

The trading host's own default route, VATI sessions, broker connectivity, Commander principals, Supabase, and trading credentials are not changed.

## Security properties

- The Muse SOCKS bridge is bound only to `127.0.0.1:17890` on trading core.
- The namespace has exactly `lo`, `muse-ns`, and `wg-muse`.
- Namespace Internet traffic can leave only through `wg-muse`.
- RFC1918, CGNAT, loopback, link-local/metadata, multicast, and reserved IPv4 destinations are blocked before encryption.
- IPv6 is disabled inside the namespace until an explicitly governed IPv6 peer exists.
- The US/Canada exit also blocks private destinations and drops traffic aimed at the exit VPS itself.
- DNS is performed behind the SOCKS5/WireGuard path. Consumers must use `socks5h` or Chromium remote DNS.
- The health check verifies both a fixed public IP and country code (`US` or `CA`). A mismatch stops the bridge.
- Installation actively proves the kill switch by taking `wg-muse` down and confirming that no public connection succeeds.
- Installation snapshots the trading host default route before/after and removes the enclave if it changes.
- No Meta password, cookie, or Muse profile is stored on the trading VM.

## 1. Stage the trading-core client

From this directory on `van-trading-core`:

```bash
sudo install -m 0600 muse-egress.env.example /etc/van-muse-egress.env
sudo bash install-muse-egress.sh
```

The first run generates the WireGuard client private key and prints:

```text
MUSE_CLIENT_PUBLIC_KEY=...
```

It deliberately exits staged/not-started until a real exit peer is configured.

## 2. Provision a dedicated US/Canada exit

Use a small **dedicated** Ubuntu 24.04 VPS with a static public IPv4 in the US or Canada. Copy only `install-us-ca-exit.sh` to it and run:

```bash
sudo env \
  MUSE_CLIENT_PUBLIC_KEY='<client-public-key>' \
  MUSE_EXIT_EXPECTED_COUNTRY=US \
  bash install-us-ca-exit.sh
```

For Canada use `MUSE_EXIT_EXPECTED_COUNTRY=CA`.

The installer refuses a country mismatch and prints the exact values to place in trading core:

```text
MUSE_WG_PEER_PUBLIC_KEY=...
MUSE_WG_ENDPOINT=<fixed-ip>:51820
MUSE_EXPECTED_EGRESS_IP=<fixed-ip>
MUSE_EXPECTED_COUNTRY=US
```

At the VPS/provider firewall expose WireGuard UDP only. Restrict the source to trading core's public source IP when the provider supports it. Keep SSH administration separately restricted.

## 3. Activate trading-core egress

Edit `/etc/van-muse-egress.env` on trading core with the returned values, then:

```bash
sudo bash install-muse-egress.sh
sudo qualify-muse-egress
```

A successful install emits `MUSE_EGRESS_GREEN`. The normal `deploy/van-trading-core/qualify.sh` also becomes RED if Muse is configured but this enclave fails qualification.

## 4. Give Hermes the persistent path

On `dial-control` / Hermes:

```bash
bash deploy/van-trading-core/muse/hermes/install-muse-egress-tunnel.sh
```

This creates a persistent systemd user tunnel:

```text
127.0.0.1:17891  -> SSH ->  van-trading-core:127.0.0.1:17890
```

The Hermes check is:

```bash
~/.local/bin/van-muse-egress-check
```

It must return the configured fixed IP and `US` or `CA`.

## 5. Persistent Muse browser

Launch the dedicated profile with:

```bash
bash deploy/van-trading-core/muse/hermes/launch-muse-browser.sh
```

The launcher uses a persistent profile, SOCKS5 only, proxy-side DNS, disables QUIC, and disables non-proxied WebRTC UDP. The profile should be dedicated to Muse rather than mixed with unrelated browsing.

## Operational rule

**VAN/Hermes remains the authority.** This enclave supplies a stable network execution path only. It does not grant Muse trading authority, infrastructure credentials, or access to VATI secrets, and it does not guarantee Meta account eligibility.

Do not falsify age, identity, billing, or other account information. The purpose of this module is deterministic network isolation and region-stable egress, not identity spoofing.
