"""Rev 1.5 §13.3 — the mTLS listener, and where a caller's name comes from.

One idea in this file matters more than the rest: **the caller's identity is the common
name in the verified client certificate, and it is read from the TLS layer, never from the
request.** A name in a JSON body is a field any caller can write. The agent authorises
against identities, so it has to get them from something the caller cannot choose.

The bind address is the other one. `require_private_bind` refuses `0.0.0.0` and refuses the
host's public address, because this process is the only bridge to a Chromium holding the
owner's logged-in sessions, and the difference between a private listener and a public one
is one character in a config file.
"""

from __future__ import annotations

import ipaddress
import json
import os
import ssl
from dataclasses import dataclass


class BindRefused(Exception):
    pass


def require_private_bind(address: str, *, public_addresses: frozenset[str] = frozenset()) -> str:
    """Refuse anything that is not a specific private address.

    Wildcards first because they are the common mistake and the worst outcome: `0.0.0.0`
    in a config file reads as "listen" and means "listen on the internet".
    """
    if address in {"", "0.0.0.0", "::", "*"}:
        raise BindRefused("control_agent_bind_is_a_wildcard")
    if address in public_addresses:
        raise BindRefused("control_agent_bind_is_the_public_address")
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise BindRefused("control_agent_bind_must_be_an_ip_literal") from exc
    if parsed.is_loopback:
        # Loopback would be safe and also useless: Trading Core is another host.
        raise BindRefused("control_agent_bind_is_loopback_and_unreachable_from_trading_core")
    if not parsed.is_private:
        raise BindRefused("control_agent_bind_is_not_private")
    return address


def build_ssl_context(*, ca_file: str, cert_file: str, key_file: str) -> ssl.SSLContext:
    """A server context that will not complete a handshake without a client certificate.

    `CERT_REQUIRED` plus a `ca_file` that contains only the private control CA is the whole
    mechanism. Loading the system trust store here would mean any publicly-issued
    certificate authenticated a caller, which is the failure `qualify.sh` tests for with a
    deliberately foreign certificate carrying a *correct* common name.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=ca_file)
    context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    # Deliberately not calling load_default_certs(): see above.
    return context


def common_name_of(peer_certificate: dict | None) -> str:
    """The caller's identity, from the certificate the TLS layer has already verified.

    Returns "" when there is none. A caller with no certificate never gets here — the
    handshake fails first — so an empty result means the context was built wrongly, and the
    agent's own `authorize` will refuse it as an unknown caller rather than proceed.
    """
    if not peer_certificate:
        return ""
    for field in peer_certificate.get("subject", ()):  # a tuple of tuples
        for key, value in field:
            if key == "commonName":
                return value
    return ""


@dataclass(frozen=True)
class ServerConfig:
    bind: str
    port: int
    ca_file: str
    cert_file: str
    key_file: str
    cdp_websocket_url: str

    @classmethod
    def from_environment(cls, environment: dict[str, str] | None = None) -> "ServerConfig":
        env = os.environ if environment is None else environment
        pki = env.get("VAN_BROWSER_PKI_DIR", "/opt/van-browser-stream/pki")
        return cls(
            bind=require_private_bind(env.get("VAN_BROWSER_CONTROL_BIND", "")),
            port=int(env.get("VAN_BROWSER_CONTROL_PORT", "9443")),
            ca_file=f"{pki}/ca.crt",
            cert_file=f"{pki}/agent.crt",
            key_file=f"{pki}/agent.key",
            cdp_websocket_url=env.get(
                "VAN_BROWSER_CDP_WEBSOCKET",
                f"ws://127.0.0.1:{env.get('VAN_BROWSER_CDP_PORT', '9222')}",
            ),
        )


def main() -> int:
    """The entry point the systemd unit names.

    It refuses to start rather than starting wrongly, and it says which of the four things
    it needs was missing. A control agent that comes up on the wrong interface and serves
    requests is worse than one that does not come up at all.
    """
    try:
        config = ServerConfig.from_environment()
    except (BindRefused, ValueError) as exc:
        print(json.dumps({"refused": str(exc)}))
        return 2

    print(
        json.dumps(
            {
                "service": "van-browser-control-agent",
                "bind": f"{config.bind}:{config.port}",
                "cdp": config.cdp_websocket_url,
                "state": "no HTTP server is wired in this repository; the Stream Host "
                "package supplies one (RB-010/RB-115)",
            }
        )
    )
    # Deliberately not starting a listener here. There is no host, no CDP endpoint and no
    # PKI in this repository, and a server that binds a socket to prove it can would be the
    # "integrated because it starts" claim §42.5 forbids.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
