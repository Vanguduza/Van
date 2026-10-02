# Meta Muse secure access

This package is intentionally limited to secure owner access to Meta Muse. It does not define Muse's wider role in the DIAL ecosystem.

## Live path

Samsung owner peer 10.66.66.2
→ existing WireGuard wg0
→ 10.66.66.1:17980 noVNC
→ localhost-only x11vnc
→ persistent meta-muse Chromium profile
→ existing Gluetun network namespace
→ Proton US/Canada egress
→ https://muse.ai/

There is no public Muse port. noVNC binds only to the Trading Core WireGuard address and the firewall admits only the existing owner peer 10.66.66.2. The VNC backend is IPv4 localhost-only.

Chromium runs as the dedicated meta-muse OS user. The privileged systemd wrapper exists only to enter the already-qualified Gluetun network namespace before dropping privileges. The persistent profile is /var/lib/meta-muse/profile with owner-only permissions.

## Owner access

1. Enable the existing VAN WireGuard tunnel on the owner phone.
2. Open http://10.66.66.1:17980/vnc.html
3. Authenticate to Muse interactively inside that browser.

Meta credentials, cookies and session tokens remain in the persistent browser profile and are not committed to Git or copied into DIAL configuration.

The DIAL ecosystem design phase starts only after authenticated Muse operation is proven live.
