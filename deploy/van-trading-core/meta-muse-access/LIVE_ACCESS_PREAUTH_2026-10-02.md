# Meta Muse secure-access pre-authentication receipt — 2026-10-02

Status: LIVE / OWNER AUTHENTICATION PENDING

## Proven live

- meta-muse-access-firewall.service: active
- meta-muse-xvfb.service: active
- meta-muse-browser.service: active
- meta-muse-vnc.service: active
- meta-muse-novnc.service: active
- dial-browser-vpn.service: active
- noVNC listener: 10.66.66.1:17980 only
- VNC backend: 127.0.0.1:15901 only; IPv6 wildcard removed
- persistent browser page title: Muse — Your Personal AI Agent
- persistent browser URL: https://muse.ai/
- browser network namespace: net:[4026533669]
- Gluetun network namespace: net:[4026533669]
- namespace equality: GREEN
- observed Proton egress: CA, 212.104.215.152
- host access to 10.66.66.1:17980: blocked
- firewall owner allow: wg0 source 10.66.66.2 → 10.66.66.1:17980
- firewall VNC rule: loopback-only 15901

## Remaining human step

The owner must authenticate to Muse interactively from the existing phone WireGuard peer. Credentials, cookies and account tokens are not handled by automation and remain in the persistent /var/lib/meta-muse/profile browser profile.

No DIAL ecosystem integration is claimed by this receipt.
