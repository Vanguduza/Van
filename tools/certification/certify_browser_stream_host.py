#!/usr/bin/env python3
"""Rev 1.5 §§13, 23.1, 28 — live certification for the Browser Stream Host.

The Gateway declares `browser.interactive.session` with `readiness_source:
EXTERNAL_RUNTIME` and `health_probe: browser_stream_host`, so until this script has run
against a real host, an interactive browser session cannot be bound to a Mission and the
refusal says exactly that. This is the script that changes the answer.

Three canaries, each mapping to one thing the repository cannot test:

  mtls       §13.3 — the control agent completes a handshake with the private CA's client
                     certificate, and refuses one signed by anything else. The refusal is
                     the half that matters: a listener that accepts the system trust store
                     accepts any publicly-issued certificate carrying the right name
  observe    §13.2 — a read-only call over the wire protocol returns a real answer, and
                     the agent's narrowness holds: a raw CDP method is refused
  fence      §5.4  — a call naming a superseded control generation is refused, which is
                     the owner-takeover guarantee measured on the host rather than argued
                     about in a test double

Requires a live Browser Stream Host reachable over the private VCN. Without one the
script exits non-zero and records nothing, so the gate stays PENDING_LIVE — exactly as
`certify_browser_fabric.py` does for the Browser Fabric, and for the same reason: a digest
can only be recorded by measuring something.

Usage:
    python tools/certification/certify_browser_stream_host.py --canary mtls
"""

from __future__ import annotations

import argparse
import asyncio
import json
import socket
import ssl
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from services.browser_control_agent.agent import Call  # noqa: E402
from services.browser_control_agent.authority import Operation  # noqa: E402
from services.browser_control_agent.wire import (  # noqa: E402
    PROTOCOL_VERSION,
    WireError,
    decode_response,
    encode_call,
    frame,
    unframe,
)
from van_gateway.automation.external_runtime import (  # noqa: E402
    ExternalRuntimeRegistry,
    ReadinessEvidence,
)
from van_gateway.config import get_settings  # noqa: E402
from van_gateway.storage.db import Store  # noqa: E402

EVIDENCE_DIR = ROOT / "artifacts" / "runtime"

#: The capability name the Gateway's declaration probes for. Named once, here and in
#: `registries/capabilities.json`, because a certification that records evidence under a
#: name nothing reads is a certification that certifies nothing.
CAPABILITY = "browser_stream_host"


def _write_receipt(filename: str, payload: dict) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _client_context(pki: Path, client: str, *, ca_file: Path | None = None) -> ssl.SSLContext:
    """A client context that trusts the private control CA and nothing else.

    Symmetrical with `build_ssl_context` on the server side, and deliberately not calling
    `load_default_certs()`: this connection is to one host whose certificate was issued by
    a CA this script holds a copy of, and widening that to the public PKI would mean any
    certificate for the agent's hostname authenticated the host to us.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = False  # the agent's certificate carries a CN, not a SAN host
    context.load_verify_locations(cafile=str(ca_file or (pki / "ca.crt")))
    # `make-stream-pki.sh` issues these as `client-<common name>.crt`, and the common
    # name is what the agent authorises against. Passing it explicitly rather than
    # defaulting means a certification run says which identity it certified with: the two
    # the script issues have different scopes, and "the agent answered" is only meaningful
    # alongside "to whom".
    context.load_cert_chain(
        certfile=str(pki / f"client-{client}.crt"),
        keyfile=str(pki / f"client-{client}.key"),
    )
    return context


def _connect(host: str, port: int, context: ssl.SSLContext, timeout: float) -> ssl.SSLSocket:
    raw = socket.create_connection((host, port), timeout=timeout)
    return context.wrap_socket(raw, server_hostname=host)


def _speak(sock: ssl.SSLSocket, call: Call) -> tuple[bool, object]:
    """One request, one response, framed by `wire.py` rather than by this file."""
    request_id = uuid.uuid4().hex
    sock.sendall(frame(encode_call(call, request_id=request_id)))
    buffer = b""
    messages: list[str] = []
    while not messages:
        chunk = sock.recv(65536)
        if not chunk:
            raise ConnectionError("stream_host_closed_the_connection")
        buffer += chunk
        messages, buffer = unframe(buffer)
    echoed, ok, payload = decode_response(messages[0])
    if echoed != request_id:
        raise WireError("wire_request_id_does_not_match")
    return ok, payload


def _call(operation: Operation, args, **params) -> Call:
    return Call(
        operation=operation,
        session_id=args.session_id,
        target_id=args.target_id,
        lease_id=args.lease_id,
        lease_generation=args.lease_generation,
        task_id=args.task_id,
        params=params,
    )


async def canary_mtls(store: Store, args) -> int:
    """§13.3 — the private CA admits, and a foreign CA does not.

    Both halves or neither. A handshake that succeeds proves the listener is up; it does
    not prove the listener is *closed*, and a control agent that accepts any well-formed
    certificate is the bridge this whole topology exists to avoid.
    """
    pki = Path(args.pki)
    try:
        context = _client_context(pki, args.client)
        with _connect(args.host, args.port, context, args.timeout) as sock:
            peer = sock.getpeercert()
            cipher = sock.cipher()
    except (OSError, ssl.SSLError) as exc:
        print(f"FAIL stream host mTLS canary: private CA client was refused: {exc}")
        return 1
    if not peer:
        print("FAIL stream host mTLS canary: the host presented no certificate")
        return 1

    foreign_ca = pki / "foreign-ca.crt"
    foreign_cert = pki / "foreign-client.crt"
    if not (foreign_ca.exists() and foreign_cert.exists()):
        print(
            "FAIL stream host mTLS canary: no foreign certificate to test the refusal "
            f"with. Generate one and place it at {foreign_cert}; without it this canary "
            "proves only that the listener accepts, never that it refuses."
        )
        return 1
    foreign = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    foreign.minimum_version = ssl.TLSVersion.TLSv1_3
    foreign.check_hostname = False
    foreign.verify_mode = ssl.CERT_REQUIRED
    foreign.load_verify_locations(cafile=str(pki / "ca.crt"))
    foreign.load_cert_chain(
        certfile=str(foreign_cert), keyfile=str(pki / "foreign-client.key")
    )
    try:
        with _connect(args.host, args.port, foreign, args.timeout):
            pass
    except (OSError, ssl.SSLError):
        pass
    else:
        print(
            "FAIL stream host mTLS canary: a certificate signed by a foreign CA "
            "completed the handshake. The listener is trusting more than the control CA."
        )
        return 1

    receipt = _write_receipt(
        "van_browser_stream_host_mtls_attestation.json",
        {
            "capability": CAPABILITY, "check": "mutual_tls",
            "endpoint": f"{args.host}:{args.port}",
            "tls_version": cipher[1] if cipher else None,
            "peer_common_name": _common_name(peer),
            "foreign_ca_refused": True, "contains_secrets": False,
            "verified_at_unix": int(time.time()),
        },
    )
    print(f"PASS stream host mTLS canary; receipt {receipt.relative_to(ROOT)}")
    return 0


async def canary_observe(store: Store, args) -> int:
    """§13.2 — a read-only call answers, and the narrowness holds.

    Recording readiness evidence here and not in `mtls` is deliberate: a reachable TLS
    listener is not a working control agent, and `browser.interactive.session` is about
    whether VAN can actually drive a browser, not whether a port is open.
    """
    pki = Path(args.pki)
    try:
        context = _client_context(pki, args.client)
        with _connect(args.host, args.port, context, args.timeout) as sock:
            ok, payload = _speak(sock, _call(Operation.QUERY_ACCESSIBILITY, args))
            if not ok:
                print(f"FAIL stream host observe canary: refused: {payload}")
                return 1
            observed = payload

            # The forbidden shape, over the same connection. `raw_cdp` is not an
            # Operation, so a host that answers this at all has a passthrough the agent
            # is documented not to have — and the readiness evidence must not be written.
            raw = json.dumps(
                {
                    "protocol": PROTOCOL_VERSION, "request_id": uuid.uuid4().hex,
                    "operation": "raw_cdp", "session_id": args.session_id,
                    "target_id": args.target_id, "lease_id": args.lease_id,
                    "lease_generation": args.lease_generation, "task_id": args.task_id,
                    "params": {"method": "Runtime.evaluate", "expression": "1+1"},
                }
            )
            sock.sendall(frame(raw))
            reply = sock.recv(65536)
    except (OSError, ssl.SSLError, ConnectionError, WireError) as exc:
        print(f"FAIL stream host observe canary: {exc}")
        return 1

    if reply and b'"ok":true' in reply.replace(b" ", b""):
        print(
            "FAIL stream host observe canary: the agent answered a raw CDP call. "
            "§13.2 forbids the passthrough; nothing is recorded."
        )
        return 1

    pointer = f"gateway://browser-stream-host/certification/{uuid.uuid4().hex}"
    await ExternalRuntimeRegistry(store).record_evidence(
        ReadinessEvidence(
            capability=CAPABILITY, evidence_pointer=pointer,
            runtime_version=str(args.runtime_version),
        )
    )
    receipt = _write_receipt(
        "van_browser_stream_host_observe_attestation.json",
        {
            "capability": CAPABILITY, "check": "narrow_read_only_call",
            "endpoint": f"{args.host}:{args.port}",
            "operation": Operation.QUERY_ACCESSIBILITY.value,
            "answered": bool(observed), "raw_cdp_refused": True,
            "evidence_pointer": pointer, "runtime_version": str(args.runtime_version),
            "contains_secrets": False, "verified_at_unix": int(time.time()),
        },
    )
    print(f"PASS stream host observe canary; receipt {receipt.relative_to(ROOT)}")
    return 0


async def canary_fence(store: Store, args) -> int:
    """§5.4 — a superseded control generation is refused on the host.

    The Gateway's own tests prove it moves the generation. What they cannot prove is that
    the *host* honours it, and a host that does not is a host where "Take over" is a
    button that changes a number in a database while the agent keeps clicking.
    """
    pki = Path(args.pki)
    try:
        context = _client_context(pki, args.client)
        with _connect(args.host, args.port, context, args.timeout) as sock:
            stale = Call(
                operation=Operation.NAVIGATE,
                session_id=args.session_id, target_id=args.target_id,
                lease_id=args.lease_id,
                lease_generation=max(0, int(args.lease_generation) - 1),
                task_id=args.task_id,
                params={"url": "https://example.com/"},
            )
            ok, payload = _speak(sock, stale)
    except (OSError, ssl.SSLError, ConnectionError, WireError) as exc:
        print(f"FAIL stream host fence canary: {exc}")
        return 1

    if ok:
        print(
            "FAIL stream host fence canary: a call naming a superseded control "
            "generation was executed. Owner takeover does not hold on this host."
        )
        return 1

    receipt = _write_receipt(
        "van_browser_stream_host_fence_attestation.json",
        {
            "capability": CAPABILITY, "check": "superseded_generation_refused",
            "endpoint": f"{args.host}:{args.port}",
            "refusal": payload, "contains_secrets": False,
            "verified_at_unix": int(time.time()),
        },
    )
    print(f"PASS stream host fence canary; receipt {receipt.relative_to(ROOT)}")
    return 0


def _common_name(certificate: dict | None) -> str:
    if not certificate:
        return ""
    for field in certificate.get("subject", ()):
        for key, value in field:
            if key == "commonName":
                return value
    return ""


CANARIES = {
    "mtls": canary_mtls,
    "observe": canary_observe,
    "fence": canary_fence,
}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canary", choices=sorted(CANARIES), default="mtls")
    parser.add_argument("--host", required=True, help="the control agent's private VCN address")
    parser.add_argument("--port", type=int, default=9443)
    parser.add_argument("--pki", default="/opt/van-browser-stream/pki")
    parser.add_argument("--client", default="stagehand.trading-core.van.internal",
                        help="the client common name to certify with; must be one "
                             "make-stream-pki.sh issued and the agent admits")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--lease-id", required=True)
    parser.add_argument("--lease-generation", type=int, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--runtime-version", required=True,
                        help="the host's reported version; recorded in the evidence")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.browser_enabled:
        print("BLOCKED: VAN_BROWSER_ENABLED is false.")
        print("         Nothing is certified and no evidence is recorded.")
        return 2

    store = Store(settings.database_path)
    await store.migrate()
    return await CANARIES[args.canary](store, args)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
