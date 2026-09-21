"""The loopback CDP client. Nothing in this repository executes it.

It is a separate file from `agent.py` for one reason: this is the half that needs a running
Chromium, and keeping it apart means the half that decides who may do what has no untestable
code in it. The ledger records this file as `EXTERNAL_RUNTIME` and the proof that it works
is RB-010/RB-117 on a real Stream Host, not a test here.

Two things in it are policy rather than plumbing, and they are here rather than in the agent
because they are properties of the *connection*, not of a request:

  * the endpoint is pinned to loopback. A CDP client that would connect anywhere else is a
    CDP client that can be pointed at another host's browser by configuration;
  * the browser is launched with `--remote-debugging-address=127.0.0.1`, and the agent
    refuses to start if the port answers on any other interface. §13.2's "no public CDP" is
    a deployment fact, so it is checked where deployment can get it wrong.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
from dataclasses import dataclass
from typing import Any

#: The only address a CDP endpoint may have. Not configurable: a setting here is a way for
#: a misconfiguration to become a public debugger.
LOOPBACK = ipaddress.ip_address("127.0.0.1")


class CdpUnavailable(Exception):
    pass


@dataclass
class LoopbackCdp:
    """A minimal CDP client over the browser's websocket, bound to loopback.

    Deliberately not a general client: `send` takes a method name from the agent's
    handlers, never from a caller, and the agent's allowlist test is what keeps that true.
    """

    websocket_url: str
    _next_id: int = 0

    def __post_init__(self) -> None:
        self._assert_loopback(self.websocket_url)

    @staticmethod
    def _assert_loopback(url: str) -> None:
        """Refuse an endpoint that is not on this machine's loopback.

        Checked at construction rather than at first use, because a service that starts
        happily and fails on the first request is a service an operator will restart rather
        than look at.
        """
        without_scheme = url.split("://", 1)[-1]
        host = without_scheme.split("/", 1)[0].rsplit(":", 1)[0].strip("[]")
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            # A hostname resolves at connect time, which is a different machine's problem
            # and possibly a different machine. Only a literal loopback address is allowed.
            raise CdpUnavailable("cdp_endpoint_must_be_a_loopback_literal") from exc
        if not address.is_loopback:
            raise CdpUnavailable("cdp_endpoint_not_loopback")

    async def send(self, target_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """One CDP call. Requires a websocket client the deployment supplies."""
        raise CdpUnavailable(
            "no CDP websocket client is installed in this repository; the Browser Stream "
            "Host supplies one (RB-010)"
        )

    def _envelope(self, target_id: str, method: str, params: dict[str, Any]) -> str:
        self._next_id += 1
        return json.dumps(
            {"id": self._next_id, "method": method, "params": params, "sessionId": target_id}
        )


async def assert_no_public_cdp(port: int, interfaces: list[str]) -> list[str]:
    """RB-117 — prove the debugger is not reachable from anywhere but loopback.

    Returns the interfaces on which the port answered. An empty list is the passing result
    and anything else is a finding, which is the right way round: a check that returns
    "fine" when it could not test anything is how this kind of exposure survives an audit.
    """
    exposed: list[str] = []
    for interface in interfaces:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(interface, port), timeout=2.0
            )
            writer.close()
            await writer.wait_closed()
        except (OSError, asyncio.TimeoutError):
            continue
        if ipaddress.ip_address(interface).is_loopback:
            continue
        exposed.append(interface)
    return exposed
