"""Review I5 P1, P2 — the Stagehand endpoint's DNS answer is pinned and never blocks the loop.

Probe review-i5/probes/placement_dns.py (fbe5502e):

* P1 — placement resolved the endpoint name at check time and httpx resolved it again at
  connect time, so a rebinding answer (overlay first, loopback next) passed the gate and was
  then connected to.
* P2 — the synchronous resolver ran inside the async gate: a hung resolver stalled the event
  loop ~2 s per evaluation (2.05 s longest stall) and left a thread behind each time
  (1 -> 7 threads after 6 evaluations).
"""

from __future__ import annotations

import asyncio
import datetime
import ssl
import threading
import time
import uuid

import httpx
import pytest

from van_gateway.automation import placement
from van_gateway.browser import adapters
from van_gateway.browser.adapters import StagehandAdapter, pinned_transport
from van_gateway.browser.lane_gates import load_stagehand_production_gate
from van_gateway.config import Settings, get_settings

HEALTHY = {"ok": True, "trust_zone": "van-browser-core", "runtime_version": "4.1.0",
           "runtime_version_source": "installed-package-metadata", "act_endpoint_enabled": False,
           "model_name": "anthropic/claude-sonnet-5", "model_key_present": True,
           "provider_key_in_browser_memory": False, "direct_agent_loop": False, "model_self_selection": False}


def _host() -> str:
    return f"bc-{uuid.uuid4().hex[:10]}.van.internal"


def _settings(tmp_path, host):
    pki = {}
    for n in ("browser_core_ca_file", "browser_core_client_cert_file", "browser_core_client_key_file"):
        (tmp_path / n).write_text("x")
        pki[n] = str(tmp_path / n)
    return Settings(browser_enabled=True, browser_stagehand_zone="van-browser-core",
                    browser_stagehand_base_url=f"https://{host}:9443/stagehand", **pki)


class _Rebinding:
    def __init__(self, host, answers):
        self.host, self.answers, self.calls = host, list(answers), 0

    def __call__(self, host, *args, **kwargs):
        assert host == self.host, host
        ip = self.answers[min(self.calls, len(self.answers) - 1)]
        self.calls += 1
        import socket

        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]


class _RecordingBackend:
    def __init__(self):
        self.connected: list[tuple[str, int]] = []

    async def connect_tcp(self, host, port, **kwargs):
        self.connected.append((host, port))
        raise httpx.ConnectError("recorded, not connected")

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


def _pinned_with(inner):
    transport = httpx.AsyncHTTPTransport()
    transport._pool._network_backend = adapters._PinnedNetworkBackend(inner)
    return transport


# ------------------------------------------------------------------------------- P1


async def test_the_connection_uses_the_address_the_gate_checked(tmp_path, monkeypatch):
    host = _host()
    dns = _Rebinding(host, ["10.77.0.6", "127.0.0.1"])  # overlay first, loopback next
    monkeypatch.setattr(placement.socket, "getaddrinfo", dns)
    assert placement.stagehand_production_enabled(_settings(tmp_path, host), worker_health=HEALTHY) == (
        True, "STAGEHAND_PLACEMENT_SATISFIED")
    inner = _RecordingBackend()
    async with httpx.AsyncClient(transport=_pinned_with(inner), base_url=f"https://{host}:9443") as client:
        with pytest.raises(httpx.ConnectError):
            await client.get("/health")
    assert inner.connected == [("10.77.0.6", 9443)]
    assert dns.calls == 1  # one resolution, shared by the gate and the connection


async def test_a_rebound_answer_after_the_ttl_is_refused_before_any_socket(tmp_path, monkeypatch):
    host = _host()
    dns = _Rebinding(host, ["10.77.0.6", "127.0.0.1"])
    monkeypatch.setattr(placement.socket, "getaddrinfo", dns)
    assert placement.stagehand_production_enabled(_settings(tmp_path, host), worker_health=HEALTHY)[0] is True
    monkeypatch.setattr(placement, "DNS_CACHE_TTL_S", 0.0)
    placement._getaddrinfo_resolver.clear()
    inner = _RecordingBackend()
    async with httpx.AsyncClient(transport=_pinned_with(inner), base_url=f"https://{host}:9443") as client:
        with pytest.raises(httpx.ConnectError, match="STAGEHAND_ENDPOINT_NOT_CROSS_ZONE_MTLS"):
            await client.get("/health")
    assert inner.connected == [] and dns.calls == 2


def _pki(tmp_path, server_name):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    now = datetime.datetime.now(datetime.timezone.utc)

    def cert(subject, issuer_name, key, issuer_key, *, ca=False, san=None):
        b = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)]))
             .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_name)]))
             .public_key(key.public_key()).serial_number(x509.random_serial_number())
             .not_valid_before(now - datetime.timedelta(minutes=1)).not_valid_after(now + datetime.timedelta(hours=1))
             .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
        if san:
            b = b.add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), critical=False)
        return b.sign(issuer_key, hashes.SHA256())

    def write(name, obj):
        path = tmp_path / name
        if isinstance(obj, x509.Certificate):
            path.write_bytes(obj.public_bytes(serialization.Encoding.PEM))
        else:
            path.write_bytes(obj.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
        return str(path)

    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca = cert("test-ca", "test-ca", ca_key, ca_key, ca=True)
    srv_key, cli_key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    return {
        "ca": write("ca.pem", ca),
        "srv_cert": write("srv.pem", cert(server_name, "test-ca", srv_key, ca_key, san=server_name)),
        "srv_key": write("srv.key", srv_key),
        "cli_cert": write("cli.pem", cert("van-gateway", "test-ca", cli_key, ca_key)),
        "cli_key": write("cli.key", cli_key),
    }


async def _tls_server(files):
    seen = {"sni": [], "host": [], "client_cert": []}
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH, cafile=files["ca"])
    ctx.load_cert_chain(files["srv_cert"], files["srv_key"])
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.sni_callback = lambda sock, name, _ctx: seen["sni"].append(name)

    async def handle(reader, writer):
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            seen["host"] += [line.split(b":", 1)[1].strip().decode() for line in head.split(b"\r\n")
                             if line.lower().startswith(b"host:")]
            seen["client_cert"].append(bool(writer.get_extra_info("peercert")))
            writer.write(b"HTTP/1.1 200 OK\r\ncontent-length: 2\r\nconnection: close\r\n\r\nok")
            await writer.drain()
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=ctx)
    return server, server.sockets[0].getsockname()[1], seen


@pytest.mark.parametrize("cert_name,ok", [("NAME", True), ("other.van.internal", False)])
async def test_mtls_is_verified_against_the_name_not_the_pinned_address(tmp_path, monkeypatch, cert_name, ok):
    host = _host()
    files = _pki(tmp_path, host if cert_name == "NAME" else cert_name)
    # The checked address here is loopback (the test server); placement itself would refuse it.
    monkeypatch.setattr(placement, "checked_connect_addresses", lambda name, resolver=None: ["127.0.0.1"])
    server, port, seen = await _tls_server(files)
    ctx = ssl.create_default_context(cafile=files["ca"])
    ctx.load_cert_chain(files["cli_cert"], files["cli_key"])
    try:
        async with httpx.AsyncClient(transport=pinned_transport(verify=ctx), base_url=f"https://{host}:{port}") as client:
            if ok:
                r = await client.get("/health")
                assert r.text == "ok"
                assert seen["sni"] == [host] and seen["host"] == [f"{host}:{port}"] and seen["client_cert"] == [True]
            else:
                with pytest.raises(httpx.ConnectError, match="CERTIFICATE_VERIFY_FAILED|certificate"):
                    await client.get("/health")
    finally:
        server.close()
        await server.wait_closed()


async def test_the_stagehand_adapter_uses_the_pinned_transport_with_its_mtls_identity(tmp_path, monkeypatch):
    files = _pki(tmp_path, "x.van.internal")
    monkeypatch.setenv("VAN_BROWSER_CORE_CA_FILE", files["ca"])
    monkeypatch.setenv("VAN_BROWSER_CORE_CLIENT_CERT_FILE", files["cli_cert"])
    monkeypatch.setenv("VAN_BROWSER_CORE_CLIENT_KEY_FILE", files["cli_key"])
    get_settings.cache_clear()
    try:
        adapter = StagehandAdapter(None, base_url="https://x.van.internal:9443/stagehand", enabled=True)
        kwargs = adapter.client_kwargs()
    finally:
        get_settings.cache_clear()
    assert isinstance(kwargs["transport"]._pool._network_backend, adapters._PinnedNetworkBackend)
    assert "verify" not in kwargs and "cert" not in kwargs


# ------------------------------------------------------------------------------- P2


async def test_a_hung_resolver_neither_stalls_the_loop_nor_grows_threads(tmp_path, monkeypatch):
    host = _host()
    release = threading.Event()
    calls = []

    def hung(name, *args, **kwargs):
        calls.append(name)
        release.wait(20)
        raise OSError("released")

    monkeypatch.setattr(placement.socket, "getaddrinfo", hung)
    gate = load_stagehand_production_gate(_settings(tmp_path, host), None)
    ticks: list[float] = []

    async def ticker():
        t0 = time.monotonic()
        while time.monotonic() - t0 < 3.0:
            ticks.append(time.monotonic())
            await asyncio.sleep(0.05)

    dns_threads = lambda: sum(t.name == "stagehand-placement-dns" for t in threading.enumerate())  # noqa: E731
    before = dns_threads()
    try:
        tk = asyncio.create_task(ticker())
        await asyncio.sleep(0.1)
        t0 = time.monotonic()
        verdicts = await asyncio.gather(*(gate() for _ in range(6)))
        took = time.monotonic() - t0
        await tk
        stall = max(b - a for a, b in zip(ticks, ticks[1:]))
        grew = dns_threads() - before
        t1 = time.monotonic()
        again = await gate()  # the shared lookup is overdue: this caller fails at once
        again_took = time.monotonic() - t1
        print(f"\nP2 after: 6 gate evaluations took {took:.2f}s; longest loop stall {stall:.2f}s; "
              f"resolver threads +{grew}; getaddrinfo calls {len(calls)}")
    finally:
        release.set()
    assert all(v == (False, "STAGEHAND_ENDPOINT_UNRESOLVABLE") for v in verdicts), verdicts
    assert stall < 0.5, stall
    assert grew <= placement.DNS_MAX_THREADS and len(calls) == 1
    assert took < placement.DNS_RESOLVE_TIMEOUT_S + 1.5
    assert again == (False, "STAGEHAND_ENDPOINT_UNRESOLVABLE") and again_took < 0.5, again_took


def test_answers_are_cached_for_the_ttl_and_failures_briefly(tmp_path, monkeypatch):
    host = _host()
    dns = _Rebinding(host, ["10.77.0.6"])
    monkeypatch.setattr(placement.socket, "getaddrinfo", dns)
    for _ in range(5):
        assert placement.DEFAULT_RESOLVER(host) == ["10.77.0.6"]
    assert dns.calls == 1
    bad = _host()
    failures = []

    def failing(name, *a, **k):
        failures.append(name)
        raise OSError("nxdomain")

    monkeypatch.setattr(placement.socket, "getaddrinfo", failing)
    for _ in range(3):
        with pytest.raises(OSError):
            placement.DEFAULT_RESOLVER(bad)
    assert failures == [bad]


def test_no_free_resolver_thread_fails_closed_at_once(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(placement.socket, "getaddrinfo", lambda *a, **k: release.wait(20) or [])
    monkeypatch.setattr(placement, "DNS_RESOLVE_TIMEOUT_S", 0.05)
    resolver = placement._BoundedCachingResolver()
    try:
        for _ in range(placement.DNS_MAX_THREADS):
            with pytest.raises(TimeoutError):
                resolver(_host())
        t0 = time.monotonic()
        with pytest.raises(TimeoutError, match="no resolver thread free"):
            resolver(_host())
        assert time.monotonic() - t0 < 0.05
    finally:
        release.set()
