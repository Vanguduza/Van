# Meta Muse Secure Access — Live Green Baseline

Date: 2026-10-02
Repository baseline: `Vanguduza/Van@12feb9033dfc1dd68d7b4d41ac477f0d9dbbc4af`

## Scope

This evidence records only the live secure-access baseline for Meta Muse on `van-trading-core`.
It does **not** define Muse's future role, authority, memory, orchestration, or integration inside the DIAL ecosystem.

## Live access path

```text
S24
  -> WireGuard (10.66.66.2/32)
  -> van-trading-core wg0 (10.66.66.1)
  -> owner-only noVNC 10.66.66.1:6085
  -> persistent Muse Chromium profile
  -> Gluetun network namespace
  -> Proton WireGuard
  -> Canada/US-qualified Internet
  -> https://muse.ai/
```

## Verification evidence

### 1. Baseline services

The following services were observed active before testing:

- `dial-browser-vpn.service`
- `meta-muse-owner-xvfb.service`
- `meta-muse-owner-browser.service`
- `meta-muse-owner-vnc.service`
- `meta-muse-owner-novnc.service`

The owner-only listener was observed at `10.66.66.1:6085`.

### 2. Authenticated session

Before restart, the persistent Chromium profile exposed the page:

- title: `Chat — van muse`
- URL: `https://muse.ai/`

No cookies, tokens, session storage, passwords, card data, or verification secrets were read or recorded.

### 3. Browser restart persistence

The Muse Chromium process was restarted deliberately.

- pre-restart service PID: `524277`
- post-restart service PID: `595572`
- result: `BROWSER_PROCESS_RESTART_GREEN`

After restart, `Chat — van muse` reappeared at `https://muse.ai/`, proving the authenticated session survives a controlled browser restart via the persistent profile.

### 4. VPN egress

Before restart, Muse egress was observed as:

- IP: `212.104.215.152`
- country: `CA`

After the fail-closed/recovery cycle, Muse egress was observed as:

- IP: `185.98.171.249`
- country: `CA`

The exact provider IP is not treated as an invariant; US/Canada qualification is.

### 5. Fail-closed test

`dial-browser-vpn.service` was deliberately stopped.

Observed state:

- VPN: inactive
- Muse owner browser: inactive
- no Muse Chromium process remained for the persistent Muse profile

Result:

`MUSE_FAIL_CLOSED_GREEN`

This proves Muse did not fall back to the Oracle host's ordinary Internet route when the VPN disappeared.

### 6. Recovery test

The VPN was restarted and passed the existing VPN health wait. The Muse owner browser was then restarted.

Observed:

- `VPN_RESTORED_GREEN`
- Muse browser active
- `Chat — van muse` restored
- egress country: `CA`
- owner-only noVNC active on `10.66.66.1:6085`

### 7. Network namespace identity

Observed live process identifiers:

- Gluetun container PID: `599282`
- Muse Chromium process PID: `600053`

Both resolved to:

`net:[4026533669]`

Therefore the persistent Muse Chromium is running in the same network namespace as Gluetun.

Result:

`MUSE_GLUETUN_NETNS_GREEN`

### 8. Owner access boundary

The Muse noVNC listener was observed only on:

`10.66.66.1:6085`

Persistent host firewall state contains the exact owner-only rule:

```text
-A INPUT -i wg0 -s 10.66.66.2/32 -d 10.66.66.1/32 -p tcp -m state --state NEW -m tcp --dport 6085 -m comment --comment "VAN_TRADING_MANAGED meta-muse-owner-novnc" -j ACCEPT
```

The persistent browser profile is owned by `dial-browser:dial-browser` with mode `0700`.

### 9. Host/VATI regression

The Oracle host default route remained:

```text
default via 10.0.1.1 dev enp0s6 proto dhcp src 10.0.1.233 metric 100
```

The following VATI services remained active after the VPN stop/recovery test:

- `vati-automation.service`
- `vati-commander.service`
- `vati-mt5-pull.service`
- `vati-supabase.service`
- `vati-vekl.service`

## Baseline verdict

```text
META_MUSE_SECURE_ACCESS_GREEN
MUSE_SESSION_PERSISTENCE_GREEN
MUSE_FAIL_CLOSED_GREEN
MUSE_RECOVERY_GREEN
MUSE_GLUETUN_NETNS_GREEN
MUSE_OWNER_PRIVATE_ACCESS_GREEN
VATI_REGRESSION_GREEN
```

This baseline closes secure access only. DIAL ecosystem integration is intentionally deferred until after this live working state is accepted.
